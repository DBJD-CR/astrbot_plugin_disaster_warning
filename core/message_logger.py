"""
原始消息记录器
适配数据源架构，提供更好的日志格式和过滤功能
"""

import asyncio
import hashlib
import json
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.star import StarTools

from ..utils.version import get_plugin_version


class MessageLogger:
    """原始消息格式记录器"""

    def __init__(self, config: dict[str, Any], plugin_name: str):
        self.config = config
        self.plugin_name = plugin_name

        # 加载P2P区域代码映射（基于真实的epsp-area.csv文件）
        self.p2p_area_mapping = self._load_p2p_area_mapping()

        # 基础配置
        self.enabled = config.get("debug_config", {}).get(
            "enable_raw_message_logging", False
        )
        self.log_file_name = config.get("debug_config", {}).get(
            "raw_message_log_path", "raw_messages.log"
        )
        self.max_size_mb = config.get("debug_config", {}).get("log_max_size_mb", 50)
        self.max_files = config.get("debug_config", {}).get("log_max_files", 5)

        # 过滤配置
        self.filter_heartbeat = config.get("debug_config", {}).get(
            "filter_heartbeat_messages", True
        )
        self.filter_types = config.get("debug_config", {}).get(
            "filtered_message_types", ["heartbeat", "ping", "pong"]
        )
        self.filter_p2p_areas = config.get("debug_config", {}).get(
            "filter_p2p_areas_messages", True
        )
        self.filter_duplicate_events = config.get("debug_config", {}).get(
            "filter_duplicate_events", True
        )
        self.filter_connection_status = config.get("debug_config", {}).get(
            "filter_connection_status", True
        )
        self.wolfx_list_log_max_items = config.get("debug_config", {}).get(
            "wolfx_list_log_max_items", 5
        )
        self.startup_silence_duration = config.get("debug_config", {}).get(
            "startup_silence_duration", 0
        )

        # 记录启动时间
        self.start_time = datetime.now(timezone.utc)

        # 用于去重的缓存
        # 使用字典代替集合以支持有序删除 (FIFO/LRU)，防止无限增长
        self.recent_event_hashes: dict[str, float] = {}
        self.recent_raw_logs: list[str] = []  # 新增：用于原始日志文本去重
        self.max_cache_size = 1000
        self.max_raw_log_cache = 30  # 只缓存最近30条原始日志用于去重

        # 文件写入锁 (用于多线程/异步执行器环境)
        self._file_lock = threading.Lock()

        # 日志过滤统计
        self.filter_stats = {
            "heartbeat_filtered": 0,
            "p2p_areas_filtered": 0,
            "duplicate_events_filtered": 0,
            "connection_status_filtered": 0,
            "total_filtered": 0,
        }

        # 设置日志文件路径 - 使用AstrBot的StarTools获取正确的数据目录
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_disaster_warning")
        self.log_file_path = self.data_dir / self.log_file_name
        self.stats_file = self.data_dir / "logger_stats.json"

        # 确保日志目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 加载统计数据
        self._load_stats()

        # 初始化时读取插件版本，避免每次写日志都进行文件IO
        self.plugin_version = get_plugin_version()

        logger.info("[灾害预警] 消息记录器初始化完成")
        if self.filter_heartbeat:
            logger.debug("[灾害预警] 消息过滤配置已启用:")
            logger.debug(f"[灾害预警] - 基础类型过滤: {self.filter_types}")
            logger.debug(f"[灾害预警] - P2P节点状态过滤: {self.filter_p2p_areas}")
            logger.debug(f"[灾害预警] - 重复事件过滤: {self.filter_duplicate_events}")
            logger.debug(f"[灾害预警] - 连接状态过滤: {self.filter_connection_status}")

    def _should_filter_message(self, raw_data: Any, source_id: str = "") -> str:
        """判断是否应该过滤该消息，返回过滤原因，空字符串表示不过滤"""
        if not self.enabled or not self.filter_heartbeat:
            return ""

        try:
            # 处理不同类型的原始数据
            if isinstance(raw_data, str) and raw_data.strip():
                # 尝试解析JSON数据
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    # 如果JSON解析失败，记录调试信息但不过滤
                    logger.debug(
                        f"[灾害预警] 消息记录器 - JSON解析失败，消息前100字符: {raw_data[:100]}..."
                    )
                    return ""

                # 获取消息类型用于调试
                msg_type = data.get("type", "")
                logger.debug(
                    f"[灾害预警] 消息记录器 - 检查消息过滤，来源: {source_id}, 类型: {msg_type}, 数据长度: {len(raw_data)}"
                )

                # 检查消息类型
                if msg_type and msg_type.lower() in self.filter_types:
                    self.filter_stats["heartbeat_filtered"] += 1
                    logger.debug(f"[灾害预警] 消息记录器 - 消息类型过滤: {msg_type}")
                    return f"消息类型过滤: {msg_type}"

                # 检查P2P areas消息（节点状态信息）
                if self.filter_p2p_areas and self._is_p2p_areas_message(data):
                    self.filter_stats["p2p_areas_filtered"] += 1
                    return "P2P节点状态消息"

                # 检查重复事件 - 添加详细调试信息
                if self.filter_duplicate_events:
                    event_hash = self._generate_event_hash(data, source_id)
                    is_duplicate = self._is_duplicate_event(data, source_id)
                    if is_duplicate:
                        self.filter_stats["duplicate_events_filtered"] += 1
                        logger.debug(
                            f"[灾害预警] 消息记录器 - 重复事件过滤，哈希: {event_hash}, 原因: 事件哈希已存在"
                        )
                        return f"重复事件 (哈希: {event_hash})"
                    elif event_hash:
                        logger.debug(
                            f"[灾害预警] 消息记录器 - 事件哈希生成: {event_hash}, 允许记录"
                        )

                # 检查连接状态消息
                if self.filter_connection_status and self._is_connection_status_message(
                    data
                ):
                    self.filter_stats["connection_status_filtered"] += 1
                    logger.debug("[灾害预警] 消息记录器 - 连接状态消息过滤")
                    return "连接状态消息"

                # 检查WebSocket消息内容（嵌套JSON）
                if "raw_data" in data and isinstance(data["raw_data"], str):
                    try:
                        inner_data = json.loads(data["raw_data"])
                        inner_type = inner_data.get("type", "").lower()
                        if inner_type in self.filter_types:
                            self.filter_stats["heartbeat_filtered"] += 1
                            return f"内层消息类型过滤: {inner_type}"

                        # 检查内层数据的P2P areas消息
                        if self.filter_p2p_areas and self._is_p2p_areas_message(
                            inner_data
                        ):
                            self.filter_stats["p2p_areas_filtered"] += 1
                            return "内层P2P节点状态消息"

                        # 检查内层数据的重复事件
                        if self.filter_duplicate_events and self._is_duplicate_event(
                            inner_data, source_id
                        ):
                            self.filter_stats["duplicate_events_filtered"] += 1
                            return "内层重复事件"
                    except (json.JSONDecodeError, AttributeError):
                        pass

            elif isinstance(raw_data, dict):
                # 如果raw_data已经是字典
                msg_type = raw_data.get("type", "")
                logger.debug(
                    f"[灾害预警] 消息记录器 - 检查字典类型消息，来源: {source_id}, 类型: {msg_type}"
                )

                if msg_type and msg_type.lower() in self.filter_types:
                    self.filter_stats["heartbeat_filtered"] += 1
                    logger.debug(f"[灾害预警] 消息记录器 - 消息类型过滤: {msg_type}")
                    return f"消息类型过滤: {msg_type}"

                # 检查P2P areas消息
                if self.filter_p2p_areas and self._is_p2p_areas_message(raw_data):
                    self.filter_stats["p2p_areas_filtered"] += 1
                    return "P2P节点状态消息"

                # 检查重复事件 - 添加详细调试信息
                if self.filter_duplicate_events:
                    event_hash = self._generate_event_hash(raw_data, source_id)
                    is_duplicate = self._is_duplicate_event(raw_data, source_id)
                    if is_duplicate:
                        self.filter_stats["duplicate_events_filtered"] += 1
                        logger.debug(
                            f"[灾害预警] 消息记录器 - 重复事件过滤，哈希: {event_hash}"
                        )
                        return f"重复事件 (哈希: {event_hash})"

                # 检查连接状态消息
                if self.filter_connection_status and self._is_connection_status_message(
                    raw_data
                ):
                    self.filter_stats["connection_status_filtered"] += 1
                    return "连接状态消息"

        except (json.JSONDecodeError, KeyError, TypeError):
            # 如果解析失败，不过滤
            pass

        return ""

    def _is_p2p_areas_message(self, data: dict[str, Any]) -> bool:
        """判断是否为P2P areas消息（节点状态信息）"""
        if "areas" in data and isinstance(data["areas"], list):
            areas = data["areas"]
            if areas and all(
                isinstance(area, dict) and "peer" in area for area in areas[:3]
            ):
                return True
        return False

    def _is_duplicate_event(self, data: dict[str, Any], source_id: str) -> bool:
        """判断是否为重复事件"""
        try:
            event_hash = self._generate_event_hash(data, source_id)
            if event_hash in self.recent_event_hashes:
                return True

            # 添加到缓存
            # 使用字典保持插入顺序，实现 FIFO 清理 (问题 1)
            self.recent_event_hashes[event_hash] = datetime.now().timestamp()

            if len(self.recent_event_hashes) > self.max_cache_size:
                # 移除最旧的条目 (字典的第一个键即为最旧)
                oldest = next(iter(self.recent_event_hashes))
                self.recent_event_hashes.pop(oldest)

            return False

        except Exception as e:
            logger.debug(f"[灾害预警] 去重检查异常: {e}")
            return False

    def _extract_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        """提取实际数据载荷 - 兼容多层嵌套结构"""
        if not isinstance(data, dict):
            return {}

        # 1. 优先检查 FAN Studio 风格的 Data/data
        if "Data" in data and isinstance(data["Data"], dict):
            return data["Data"]
        elif "data" in data and isinstance(data["data"], dict):
            return data["data"]

        # 2. 检查 P2P Quake 风格 (直接在根节点，但有 code/issue)
        if "code" in data and "issue" in data:
            return data

        # 3. 检查 Wolfx 风格 (扁平结构)
        if "type" in data and ("EventID" in data or "ID" in data):
            return data

        # 4. 默认返回原数据
        return data

    def _generate_event_hash(self, data: dict[str, Any], source_id: str) -> str:
        """生成事件哈希用于去重 - 智能识别事件类型"""
        # 提取实际载荷
        payload = self._extract_payload(data)

        # 基于事件的关键字段生成哈希
        hash_parts = [f"source:{source_id}"]

        # 首先进行事件类型智能识别
        event_type = self._detect_event_type(data, payload)
        hash_parts.append(f"etype:{event_type}")

        # 不同类型的事件使用不同的去重策略
        if event_type == "weather":
            return self._generate_weather_hash(payload, hash_parts)
        elif event_type == "earthquake":
            return self._generate_earthquake_hash(payload, hash_parts)
        elif event_type == "tsunami":
            return self._generate_tsunami_hash(payload, hash_parts)
        else:
            return self._generate_generic_hash(payload, hash_parts)

    def _detect_event_type(self, data: dict[str, Any], payload: dict[str, Any]) -> str:
        """智能检测事件类型"""
        # 检查消息类型字段 (优先检查外层，再检查内层)
        msg_type = str(data.get("type", "")).lower()
        if not msg_type:
            msg_type = str(payload.get("type", "")).lower()

        # 使用msg_type进行事件类型判断
        if msg_type in ["weather", "alarm", "warning"]:
            return "weather"
        # 移除 eqlist，让其回退到 generic 使用 MD5 哈希，确保列表更新能被检测到
        elif msg_type in ["earthquake", "seismic", "jma_eew", "cenc_eew", "cwa_eew"]:
            return "earthquake"
        elif msg_type in ["tsunami"]:
            return "tsunami"

        # 检查数据内容特征
        data_str = str(data).lower() + str(payload).lower()

        # 气象预警特征
        if any(
            k in data_str for k in ["weather", "alarm", "预警", "warning", "headline"]
        ):
            if not any(
                k in data_str for k in ["地震", "earthquake", "magnitude", "震级"]
            ):
                return "weather"

        # 地震事件特征
        if any(
            k in data_str
            for k in ["earthquake", "地震", "magnitude", "震级", "hypocenter", "震源"]
        ):
            return "earthquake"

        # 海啸预警特征
        if any(k in data_str for k in ["tsunami", "海啸", "津波"]):
            return "tsunami"

        # P2P地震信息 (检查 payload)
        if "code" in payload and isinstance(payload.get("code"), int):
            code = payload["code"]
            if code in [551, 556]:
                return "earthquake"
            if code in [552]:
                return "tsunami"

        return "generic"

    def _generate_weather_hash(self, data: dict[str, Any], hash_parts: list) -> str:
        """生成气象预警哈希"""
        # 1. 尝试获取唯一ID
        event_id = data.get("id") or data.get("alertId") or data.get("identifier")
        if event_id:
            hash_parts.append(f"wid:{event_id}")
            return "|".join(hash_parts)

        # 2. 组合关键字段作为ID
        # 标题/Headline
        headline = data.get("headline") or data.get("title") or ""
        if headline:
            hash_parts.append(f"wh:{headline[:30]}")

        # 地区/Area
        area = data.get("areaDesc") or data.get("sender") or ""
        if area:
            hash_parts.append(f"wa:{area}")

        # 时间/Time (精确到分钟)
        time_info = (
            data.get("effective")
            or data.get("issue_time")
            or data.get("time")
            or data.get("sendTime")
        )
        if time_info:
            hash_parts.append(f"wt:{str(time_info)[:16]}")

        return "|".join(hash_parts)

    def _generate_earthquake_hash(self, data: dict[str, Any], hash_parts: list) -> str:
        """生成地震事件哈希"""
        # 1. 尝试获取事件ID
        event_id = (
            data.get("id")
            or data.get("eventId")
            or data.get("EventID")
            or data.get("md5")
        )
        if event_id:
            hash_parts.append(f"eq_id:{event_id}")

            # 针对EEW，必须附加报数信息
            report_num = (
                data.get("updates")
                or data.get("ReportNum")
                or data.get("serial")
                or data.get("issue", {}).get("serial")
            )
            if report_num:
                hash_parts.append(f"rn:{report_num}")

            # 附加最终报标志
            if data.get("isFinal") or data.get("is_final"):
                hash_parts.append("final")

            # 附加信息类型（自动/正式），确保状态变更时生成新哈希
            info_type = data.get("infoTypeName") or data.get("type")
            if info_type:
                hash_parts.append(f"it:{info_type}")

            # 针对无报数机制的数据源（如USGS），加入更新时间或震级以区分修正
            if not report_num:
                # 尝试获取更新时间
                updated = data.get("updated") or data.get("updateTime")
                if updated:
                    hash_parts.append(f"up:{str(updated)}")

                # 尝试获取震级（保留1位小数），确保震级修正能被记录
                mag = data.get("magnitude") or data.get("Magnitude")
                if mag:
                    hash_parts.append(f"m:{mag}")

            return "|".join(hash_parts)

        # 2. 如果没有ID，使用特征组合
        # 时间 (精确到分钟)
        time_info = data.get("shockTime") or data.get("time") or data.get("OriginTime")
        if time_info:
            hash_parts.append(f"et:{str(time_info)[:16]}")

        # 震级
        mag = data.get("magnitude") or data.get("Magnitude")
        if mag:
            hash_parts.append(f"em:{mag}")

        # 位置 (保留1位小数)
        lat = data.get("latitude") or data.get("Latitude")
        lon = data.get("longitude") or data.get("Longitude")
        if lat and lon:
            try:
                hash_parts.append(f"el:{float(lat):.1f},{float(lon):.1f}")
            except (ValueError, TypeError):
                pass

        return "|".join(hash_parts)

    def _generate_tsunami_hash(self, data: dict[str, Any], hash_parts: list) -> str:
        """生成海啸预警哈希"""
        # 1. 尝试获取ID
        event_id = data.get("id") or data.get("code")
        if event_id:
            hash_parts.append(f"tid:{event_id}")

            # 附加更新时间或报数
            time_info = data.get("issue_time") or data.get("time")
            if time_info:
                hash_parts.append(f"tt:{str(time_info)[:16]}")

            return "|".join(hash_parts)

        # 2. 特征组合
        title = data.get("title") or ""
        if title:
            hash_parts.append(f"tt:{title}")

        time_info = data.get("issue_time") or data.get("time") or data.get("effective")
        if time_info:
            hash_parts.append(f"tm:{str(time_info)[:16]}")

        return "|".join(hash_parts)

    def _generate_generic_hash(self, data: dict[str, Any], hash_parts: list) -> str:
        """生成通用哈希"""
        # 尝试所有可能的ID字段
        for key in ["id", "ID", "eventId", "EventID", "code", "md5"]:
            if val := data.get(key):
                hash_parts.append(f"gid:{val}")
                return "|".join(hash_parts)

        # 如果没有ID，使用内容哈希（取前50个字符）
        content_hash = hashlib.md5(str(data).encode()).hexdigest()[:8]
        hash_parts.append(f"gh:{content_hash}")

        return "|".join(hash_parts)

    def _parse_datetime_for_hash(self, time_str: str) -> datetime | None:
        """解析时间字符串用于哈希生成"""
        if not time_str:
            return None

        # 尝试多种格式
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(time_str.strip(), fmt)
            except ValueError:
                continue

        return None

    def _is_connection_status_message(self, data: dict[str, Any]) -> bool:
        """判断是否为连接状态消息"""
        # 检查是否为连接建立、断开等状态消息
        msg_type = data.get("type", "").lower()
        if msg_type in ["connect", "disconnect", "connection", "status"]:
            return True

        # 检查是否包含连接相关的关键词
        connection_keywords = [
            "connected",
            "disconnected",
            "connection",
            "status",
            "online",
            "offline",
        ]
        message_str = str(data).lower()
        if any(keyword in message_str for keyword in connection_keywords):
            # 进一步检查，确保不是实际的灾害事件
            disaster_keywords = [
                "earthquake",
                "地震",
                "震级",
                "magnitude",
                "tsunami",
                "海啸",
                "weather",
                "气象",
            ]
            if not any(keyword in message_str for keyword in disaster_keywords):
                return True

        return False

    def _format_readable_log(self, log_entry: dict[str, Any]) -> str:
        """格式化可读性强的日志内容"""
        try:
            # 基础信息格式化
            dt = datetime.fromisoformat(log_entry["timestamp"])
            # 如果是 UTC 时间（带时区），转换为本地时间显示，方便阅读
            if dt.tzinfo is not None:
                dt = dt.astimezone()

            timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            source = log_entry["source"]
            message_type = log_entry["message_type"]

            # 构建可读性强的日志头部
            log_content = f"\n{'=' * 35}\n"
            log_content += f"🕐 日志写入时间: {timestamp}\n"
            log_content += f"📡 来源: {source}\n"
            log_content += f"📋 类型: {message_type}\n"

            # 添加连接信息（如果有）
            connection_info = log_entry.get("connection_info", {})
            if connection_info:
                log_content += "🔗 连接: "
                if "url" in connection_info:
                    log_content += f"URL: {connection_info['url']}"
                elif "server" in connection_info and "port" in connection_info:
                    log_content += (
                        f"服务器: {connection_info['server']}:{connection_info['port']}"
                    )
                log_content += "\n"

            # 格式化原始数据
            raw_data = log_entry["raw_data"]
            log_content += "\n📊 原始数据:\n"

            # 根据数据类型进行不同的格式化
            if isinstance(raw_data, str):
                # 尝试解析JSON字符串
                try:
                    parsed_data = json.loads(raw_data)
                    log_content += self._format_json_data(parsed_data, indent=2)
                except json.JSONDecodeError:
                    # 如果不是JSON，直接显示
                    log_content += f"  {raw_data}\n"
            elif isinstance(raw_data, dict):
                # 已经是字典格式
                log_content += self._format_json_data(raw_data, indent=2)
            else:
                # 其他格式
                log_content += f"  {str(raw_data)}\n"

            # 添加插件信息
            log_content += (
                f"\n🔧 插件版本: {log_entry.get('plugin_version', 'unknown')}\n"
            )
            log_content += f"{'=' * 35}\n"

            return log_content

        except Exception as e:
            # 如果格式化失败，回退到简单的JSON格式
            logger.warning(f"[灾害预警] 日志格式化失败，使用回退格式: {e}")
            return json.dumps(log_entry, ensure_ascii=False, indent=2) + "\n\n"

    def _format_json_data(self, data: dict[str, Any], indent: int = 0) -> str:
        """递归格式化JSON数据，增加可读性"""
        result = ""
        indent_str = "  " * indent

        for key, value in data.items():
            # 键名翻译和格式化
            key_display = self._get_display_key(key)

            if isinstance(value, dict):
                result += f"{indent_str}📋 {key_display}:\n"
                result += self._format_json_data(value, indent + 1)
            elif isinstance(value, list):
                if len(value) > 0:
                    result += f"{indent_str}📋 {key_display} ({len(value)}项):\n"
                    for i, item in enumerate(value[:5]):  # 只显示前5项
                        if isinstance(item, dict):
                            result += f"{indent_str}  [{i + 1}]:\n"
                            result += self._format_json_data(item, indent + 2)
                        else:
                            result += f"{indent_str}  [{i + 1}]: {item}\n"
                    if len(value) > 5:
                        result += f"{indent_str}  ... 还有 {len(value) - 5} 项\n"
                else:
                    result += f"{indent_str}📋 {key_display}: []\n"
            else:
                # 格式化具体值
                value_display = self._format_value(key, value)
                result += f"{indent_str}📋 {key_display}: {value_display}\n"

        return result

    def _get_display_key(self, key: str) -> str:
        """获取格式化的键名显示 - 整理分类，去除重复"""
        key_mappings = {
            # 🌍 基础信息字段 (所有数据源通用)
            "id": "ID",
            "ID": "ID",
            "_id": "数据库ID",
            "type": "消息类型",
            "title": "标题",
            "key": "编号",
            "code": "消息代码",
            "source": "数据来源",
            "status": "状态",
            "action": "操作",
            "timestamp": "时间戳",
            "time": "发生时间",
            "createTime": "创建时间",
            "updateTime": "更新时间",
            "created_at": "创建时间",
            "updated_at": "更新时间",
            "started_at": "开始时间",
            "expire": "过期时间",
            # 🏔️ 地震核心信息
            "earthquake": "地震信息",
            "magnitude": "震级",
            "Magunitude": "震级",  # Wolfx拼写
            "depth": "深度(km)",
            "Depth": "深度(km)",  # 大写版本
            "latitude": "纬度",
            "Latitude": "纬度",  # 大写版本
            "longitude": "经度",
            "Longitude": "经度",  # 大写版本
            "placeName": "地名",
            "name": "地点名称",
            "shockTime": "发震时间",
            "OriginTime": "发震时间",  # JMA格式
            "place": "震中",
            "region": "震中",  # Global Quake格式
            "hypocenter": "震源信息",
            "Hypocenter": "震源地名",  # JMA格式
            # 📍 震度/烈度信息
            "maxScale": "最大震度(原始)",
            "MaxIntensity": "最大烈度/震度",  # JMA/Wolfx格式
            "maxIntensity": "最大烈度",  # Wolfx格式
            "epiIntensity": "预估烈度",  # FAN Studio格式
            "intensity": "烈度",
            "shindo": "震度",  # JMA格式
            "scale": "震度值",  # P2P格式
            # 🌊 海啸相关信息
            "domesticTsunami": "日本境内海啸",
            "foreignTsunami": "海外海啸",
            "tsunami": "海啸信息",
            "info": "海啸信息",  # Wolfx格式
            # 📋 事件标识信息
            "eventId": "事件ID",
            "EventID": "事件ID",  # JMA格式
            "event_id": "事件ID",  # 下划线版本
            "EventId": "事件编码",  # FAN Studio格式
            "Serial": "报序号",  # JMA格式
            "updates": "更新次数",
            "ReportNum": "发报数",  # Wolfx格式
            # ⏰ 时间相关
            "AnnouncedTime": "发布时间",  # JMA格式
            "ReportTime": "发报时间",  # Wolfx格式
            "time_full": "发报时间(完整)",
            "originTimeMs": "发震时间(MS)",
            "originTimeIso": "发震时间(ISO)",
            "lastUpdateMs": "最后更新(MS)",
            "effective": "生效时间",  # FAN Studio格式
            "issue_time": "发布时间",
            "arrivalTime": "到达时间",  # 海啸
            # 🎯 状态标志
            "isFinal": "最终报",
            "final": "最终报",  # FAN Studio格式
            "isCancel": "取消报",
            "cancel": "取消报",  # FAN Studio格式
            "is_final": "最终报",
            "is_cancel": "取消报",
            "cancelled": "取消标志",  # P2P格式
            "fixedDepth": "固定深度",
            "is_training": "训练模式",
            "isTraining": "训练报",  # Wolfx格式
            "isSea": "海域地震",  # Wolfx格式
            "isAssumption": "推定震源",  # Wolfx格式
            "isWarn": "警报标志",  # Wolfx格式
            "immediate": "紧急标志",  # 海啸
            # 📰 内容描述
            "headline": "预警标题",  # FAN Studio格式
            "description": "详细描述",  # FAN Studio格式
            "infoTypeName": "信息类型",  # FAN Studio格式
            "correct": "订正信息",
            "issue": "发布信息",
            # 🗺️ 地理区域
            "province": "省份",  # FAN Studio格式
            "pref": "都道府县",  # P2P格式
            "addr": "观测点地址",  # P2P格式
            "location": "震源地",  # Wolfx格式
            "area": "区域代码",  # P2P格式
            "isArea": "区域标志",  # P2P格式
            # 🔗 链接和参考
            "url": "官方链接",
            "OriginalText": "原电文",  # Wolfx格式
            # 📊 精度和可信度
            "Accuracy.Epicenter": "震中精度",  # Wolfx格式
            "Accuracy.Depth": "深度精度",  # Wolfx格式
            "Accuracy.Magnitude": "震级精度",  # Wolfx格式
            "confidence": "可信度",  # P2P格式
            # 🌊 海啸详细信息
            "warningInfo": "警报核心信息",
            "timeInfo": "时间信息",
            "details": "详细信息",
            "forecasts": "沿海预报",
            "waterLevelMonitoring": "水位监测",
            "estimatedArrivalTime": "预计到达时间",
            "maxWaveHeight": "最大波高",
            "warningLevel": "警报级别",
            "stationName": "监测站名称",
            "firstHeight": "初波信息",  # 海啸
            "maxHeight": "最大波高",  # 海啸
            "condition": "状态描述",  # 海啸
            "grade": "预警级别",  # 海啸
            # 📍 观测点信息 (P2P)
            "points": "震度观测点",
            "comments": "附加评论",
            "freeFormComment": "自由附加文",
            "areas": "预警区域",  # 海啸和P2P
            # ⚠️ 变更和警报信息
            "MaxIntChange.String": "震度变更说明",  # Wolfx格式
            "MaxIntChange.Reason": "震度变更原因",  # Wolfx格式
            "CodeType": "发报说明",  # Wolfx格式
            "Title": "发报报头",  # Wolfx格式
            # 🔧 技术字段
            "hop": "跳数(hop)",
            "uid": "用户ID",
            "ver": "版本号",
            "user-agent": "客户端标识",
            "count": "计数",
            "area_confidences": "区域置信度",
            "autoFlag": "自动标志",  # FAN Studio格式
            "earthtype": "地震类型",  # FAN Studio格式
            "md5": "校验码",
            "revisionId": "修订版本号",
            "maxPGA": "最大地表加速度",
            "cluster": "集群信息",
            "level": "级别",
            "quality": "质量指标",
            "errOrigin": "时间误差",
            "errDepth": "深度误差",
            "errNS": "南北向误差",
            "errEW": "东西向误差",
            "pct": "置信度百分比",
            "stations": "参与定位的台站数",
            "stationCount": "台站统计",
            "total": "总可用台站数",
            "selected": "被选中参与计算的台站数",
            "used": "实际用于定位的台站数",
            "matching": "匹配度高的台站数",
            "depthConfidence": "深度置信度",
            "minDepth": "最小深度",
            "maxDepth": "最大深度",
            # 🔌 连接信息 (保留原有)
            "connection_type": "连接类型",
            "server": "服务器",
            "port": "端口",
            "status_code": "状态码",
        }

        return key_mappings.get(key, key)

    def _format_value(self, key: str, value: Any) -> str:
        """格式化具体值"""
        if value is None:
            return "无数据"
        elif value == "":
            return "空字符串"
        elif isinstance(value, (int, float)):
            # 特殊数值格式化
            if key == "maxScale" and isinstance(value, int):
                scale_map = {
                    10: "震度1",
                    20: "震度2",
                    30: "震度3",
                    40: "震度4",
                    45: "震度5弱",
                    50: "震度5強",
                    55: "震度6弱",
                    60: "震度6強",
                    70: "震度7",
                }
                return f"{value} ({scale_map.get(value, '未知')})"
            elif key in ["magnitude", "Magnitude", "Magunitude"] and isinstance(
                value, (int, float)
            ):
                return f"M{value:.2f}" if isinstance(value, float) else f"M{value}"
            elif key in ["depth", "Depth"] and isinstance(value, (int, float)):
                return f"{value:.2f}km" if isinstance(value, float) else f"{value}km"
            elif key in [
                "latitude",
                "Latitude",
                "longitude",
                "Longitude",
            ] and isinstance(value, (int, float)):
                return f"{value:.5f}"
            elif key in [
                "maxPGA",
                "errOrigin",
                "errDepth",
                "errNS",
                "errEW",
                "pct",
                "minDepth",
                "maxDepth",
            ] and isinstance(value, float):
                return f"{value:.3f}"
            elif key == "area" and isinstance(value, int):
                # P2P地震感知信息的区域代码 - 使用真实的CSV数据
                region_name = self.p2p_area_mapping.get(value, f"区域代码{value}")
                return f"{value} ({region_name})"
            elif key == "level" and isinstance(value, int):
                level_map = {
                    0: "0: 弱 (4+台站近距离触发)",
                    1: "1: 中 (7+台站>64计数 或 4+台站>1,000计数)",
                    2: "2: 强 (7+台站>1,000计数 或 3+台站>10,000计数)",
                    3: "3: 极强 (5+台站>10,000计数 或 3+台站>50,000计数)",
                    4: "4: 毁灭 (4+台站>50,000计数)",
                }
                return f"{value} ({level_map.get(value, '未知级别')})"
            else:
                return str(value)
        elif isinstance(value, bool):
            return "是" if value else "否"
        elif isinstance(value, str):
            # 字符串长度控制
            if len(value) > 50:
                return f"{value[:47]}..."
            return value
        else:
            return str(value)

    def _load_p2p_area_mapping(self) -> dict[int, str]:
        """加载P2P区域代码映射（基于真实的epsp-area.csv文件）"""
        area_mapping = {}

        try:
            # 读取真实的区域代码文件
            csv_path = Path(__file__).parent.parent / "resources/epsp-area.csv"
            if csv_path.exists():
                with open(csv_path, encoding="utf-8") as f:
                    # 跳过标题行
                    next(f)

                    for line in f:
                        parts = line.strip().split(",")
                        if len(parts) >= 5:
                            try:
                                # 获取数值型区域代码和地域名称
                                area_code = int(parts[1])  # 地域コード(数値型)
                                region_name = parts[4]  # 地域

                                if area_code and region_name:
                                    area_mapping[area_code] = region_name
                            except (ValueError, IndexError):
                                continue

                logger.debug(
                    f"[灾害预警] 成功加载 {len(area_mapping)} 个P2P区域代码映射"
                )
            else:
                logger.warning("[灾害预警] 未找到epsp-area.csv文件，请检查资源完整性")

        except Exception as e:
            logger.error(f"[灾害预警] 加载P2P区域代码映射失败: {e}")
            logger.error("[灾害预警] 请检查epsp-area.csv文件是否存在且格式正确")

        return area_mapping

    def _extract_content_without_timestamp(self, log_content: str) -> str:
        """提取日志内容中排除时间戳的部分，用于重复检测"""
        lines = log_content.split("\n")
        content_without_timestamp = []

        for line in lines:
            # 排除时间戳行
            if line.strip().startswith("🕐 日志写入时间:"):
                continue
            content_without_timestamp.append(line)

        return "\n".join(content_without_timestamp)

    def _is_exact_duplicate_in_log(self, new_log_content: str) -> bool:
        """检查最近的日志中是否存在完全重复的内容（基于内存缓存）"""
        try:
            # 提取新内容中排除时间戳的部分
            new_content_clean = self._extract_content_without_timestamp(new_log_content)

            # 检查内存缓存
            if new_content_clean in self.recent_raw_logs:
                logger.debug("[灾害预警] 发现内容完全重复的日志（内存缓存），跳过写入")
                return True

            # 更新缓存
            self.recent_raw_logs.append(new_content_clean)
            if len(self.recent_raw_logs) > self.max_raw_log_cache:
                self.recent_raw_logs.pop(0)

            return False

        except Exception as e:
            logger.warning(f"[灾害预警] 检查重复内容时出错: {e}")
            # 如果检查失败，允许写入（不阻止）
            return False

    def log_raw_message(
        self,
        source: str,
        message_type: str,
        raw_data: Any,
        connection_info: dict | None = None,
    ):
        """记录原始消息"""
        # 检查启动静默期
        if self.startup_silence_duration > 0:
            elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
            if elapsed < self.startup_silence_duration:
                # 静默期内不记录日志，也不更新统计
                return

        if not self.enabled:
            # 仅在调试模式下输出，避免刷屏
            # logger.debug(f"[灾害预警] 消息记录器未启用，跳过记录: {source}")
            return

        try:
            # 特殊处理 Wolfx 的地震列表数据 (eqlist)
            # 避免记录巨大的 JSON 列表，转为记录摘要
            parsed_data = None

            if isinstance(raw_data, dict):
                parsed_data = raw_data
            elif isinstance(raw_data, str) and len(raw_data) > 10:
                # 简单预检查以提高性能，避免对每条消息都做 json.loads
                if '"type"' in raw_data[:200] or "'type'" in raw_data[:200]:
                    try:
                        parsed_data = json.loads(raw_data)
                    except (json.JSONDecodeError, TypeError):
                        pass

            if parsed_data and isinstance(parsed_data, dict):
                msg_type = parsed_data.get("type", "")
                # 兼容 Wolfx 的标准类型和可能的前缀变体
                if msg_type in [
                    "jma_eqlist",
                    "cenc_eqlist",
                    "wolfx_jma_eqlist",
                    "wolfx_cenc_eqlist",
                ]:
                    self.log_earthquake_list_summary(
                        source=source,
                        earthquake_list=parsed_data,
                        url=connection_info.get("url") if connection_info else None,
                    )
                    return

            # 检查是否应该过滤该消息
            filter_reason = self._should_filter_message(raw_data, source)
            if filter_reason:
                # 根据过滤原因决定日志级别
                # 心跳包、类型过滤、P2P节点状态、重复事件列表等高频消息使用DEBUG级别
                # 连接状态等使用INFO级别/最近连接状态也变高频了，故也改为DEBUG级别
                is_high_frequency = any(
                    keyword in filter_reason
                    for keyword in ["消息类型过滤", "P2P节点状态", "心跳", "重复事件"]
                )

                if is_high_frequency:
                    logger.debug(
                        f"[灾害预警] 过滤消息 - 来源: {source}, 类型: {message_type}, 原因: {filter_reason}"
                    )
                else:
                    logger.debug(
                        f"[灾害预警] 过滤日志消息 - 来源: {source}, 类型: {message_type}, 原因: {filter_reason}"
                    )

                self.filter_stats["total_filtered"] += 1
                self._save_stats_if_needed()  # 定期保存统计
                return

            # 获取当前时间
            current_time = datetime.now(timezone.utc)

            # 准备日志条目数据
            log_entry = {
                "timestamp": current_time.isoformat(),
                "source": source,
                "message_type": message_type,
                "raw_data": raw_data,
                "connection_info": connection_info or {},
                "plugin_version": self.plugin_version,
            }

            # 尝试可读性格式化
            try:
                log_content = self._format_readable_log(log_entry)
            except Exception as format_error:
                # 如果新格式失败，回退到安全的JSON格式
                logger.warning(
                    f"[灾害预警] 可读格式失败，回退到JSON格式: {format_error}"
                )
                log_content = (
                    json.dumps(log_entry, ensure_ascii=False, indent=2) + "\n\n"
                )

            # 检查是否存在100%完全重复的内容（排除时间戳后）
            if self._is_exact_duplicate_in_log(log_content):
                logger.debug(
                    f"[灾害预警] 跳过写入内容完全重复的日志 - 来源: {source}, 类型: {message_type}"
                )
                return

            # 确保目录存在
            self.log_file_path.parent.mkdir(parents=True, exist_ok=True)

            # 异步写入日志文件
            try:
                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, self._write_log_to_file_sync, log_content)
            except RuntimeError:
                # 如果没有运行中的事件循环（如同步上下文），则同步写入
                self._write_log_to_file_sync(log_content)

        except Exception as e:
            logger.error(f"[灾害预警] 记录原始消息失败: {e}")
            logger.error(
                f"[灾害预警] 失败的消息 - 来源: {source}, 类型: {message_type}"
            )
            # 记录异常堆栈
            logger.error(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")

    def _write_log_to_file_sync(self, content: str):
        """同步写入日志文件（在线程池中运行）"""
        with self._file_lock:
            try:
                with open(self.log_file_path, "a", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()  # 确保立即写入磁盘

                # 检查文件大小，必要时进行轮转
                # 注意：轮转检查也包含文件操作，放在这里一起执行
                self._check_log_rotation()
            except OSError as io_err:
                # 磁盘满或权限不足等严重错误
                logger.error(f"[灾害预警] 写入日志文件失败 (可能磁盘已满): {io_err}")
                # 临时禁用日志记录
                self.enabled = False

    def log_websocket_message(
        self, connection_name: str, message: str, url: str | None = None
    ):
        """记录WebSocket消息"""
        self.log_raw_message(
            source=f"websocket_{connection_name}",
            message_type="websocket_message",
            raw_data=message,
            connection_info={"url": url, "connection_type": "websocket"}
            if url
            else {"connection_type": "websocket"},
        )

    def log_http_response(
        self, url: str, response_data: Any, status_code: int | None = None
    ):
        """记录HTTP响应"""
        self.log_raw_message(
            source="http_response",
            message_type="http_response",
            raw_data=response_data,
            connection_info={
                "url": url,
                "status_code": status_code,
                "connection_type": "http",
            },
        )

    def log_earthquake_list_summary(
        self,
        source: str,
        earthquake_list: dict[str, Any],
        url: str | None = None,
        max_items: int | None = None,
    ):
        """
        记录地震列表数据的摘要（不记录完整列表，避免日志膨胀）
        适用于 HTTP 和 WebSocket 的列表数据

        Args:
            source: 数据源标识
            earthquake_list: 完整的地震列表数据
            url: 请求的 URL (HTTP) 或 None (WebSocket)
            max_items: 只记录前多少条事件，默认为配置值
        """
        if not self.enabled:
            return

        # 针对 Wolfx 数据源的特殊逻辑：HTTP获取的数据完全不写入日志
        if source == "http_response" or "http" in source.lower():
            return
        if url and (url.startswith("http://") or url.startswith("https://")):
            return

        # 使用配置值作为默认值
        if max_items is None:
            max_items = self.wolfx_list_log_max_items

        try:
            # 构建摘要数据
            summary_data = {
                "summary": True,
                "message": f"地震列表摘要 (仅显示前 {max_items} 条)",
            }

            # 提取事件数量统计
            total_count = 0
            sample_events = []

            # Wolfx 列表格式: {"No1": {...}, "No2": {...}, ...}
            # 按照 No 键的数字排序
            if isinstance(earthquake_list, dict):
                # 过滤出 No 开头的键
                no_keys = [k for k in earthquake_list.keys() if k.startswith("No")]
                total_count = len(no_keys)

                # 按数字排序（No1, No2, ...）
                sorted_keys = sorted(
                    no_keys, key=lambda x: int(x[2:]) if x[2:].isdigit() else 999
                )

                # 只取前 max_items 条
                for key in sorted_keys[:max_items]:
                    event = earthquake_list.get(key, {})
                    if isinstance(event, dict):
                        # 记录完整字段，但只记录前几个条目以节省空间
                        # 将 key 放在最前面方便识别（Python 3.7+ 字典保持插入顺序）
                        event_data = {"key": key}
                        event_data.update(event)
                        sample_events.append(event_data)

            summary_data["total_events"] = total_count
            summary_data["sample_events"] = sample_events

            if total_count > max_items:
                summary_data["note"] = f"还有 {total_count - max_items} 条事件未显示"

            # 记录摘要
            connection_info = {
                "summary_mode": True,
            }
            if url:
                connection_info.update(
                    {
                        "url": url,
                        "method": "GET",
                        "connection_type": "http",
                    }
                )
            else:
                connection_info.update(
                    {
                        "connection_type": "websocket",
                    }
                )

            self.log_raw_message(
                source=source,
                message_type="earthquake_list_summary",
                raw_data=summary_data,
                connection_info=connection_info,
            )

        except Exception as e:
            logger.warning(f"[灾害预警] 地震列表摘要记录失败: {e}")
            # 失败时回退到简单的统计记录
            try:
                fallback_data = {
                    "error": "摘要生成失败",
                    "total_keys": len(earthquake_list)
                    if isinstance(earthquake_list, dict)
                    else 0,
                }
                self.log_raw_message(
                    source=source,
                    message_type="earthquake_list_summary",
                    raw_data=fallback_data,
                    connection_info={"url": url} if url else {},
                )
            except Exception:
                pass

    def _check_log_rotation(self):
        """检查日志文件大小并进行轮转"""
        try:
            if not self.log_file_path.exists():
                return

            # 获取文件大小（MB）
            file_size_mb = self.log_file_path.stat().st_size / (1024 * 1024)

            if file_size_mb > self.max_size_mb:
                self._rotate_logs()

        except Exception as e:
            logger.error(f"[灾害预警] 日志轮转检查失败: {e}")

    def _rotate_logs(self):
        """轮转日志文件，使用文件锁保护轮转操作"""
        # 简单的文件锁机制：创建一个 .lock 文件
        lock_file = self.log_file_path.with_suffix(".lock")
        if lock_file.exists():
            # 检查锁文件是否过期 (例如超过 10 秒)
            try:
                if time.time() - lock_file.stat().st_mtime > 10:
                    lock_file.unlink()
                else:
                    logger.debug("[灾害预警] 日志轮转正在进行中，跳过")
                    return
            except Exception:
                return

        try:
            # 创建锁文件
            lock_file.touch()

            # 关闭当前日志文件
            for i in range(self.max_files - 1, 0, -1):
                old_file = self.log_file_path.with_suffix(f".log.{i}")
                new_file = self.log_file_path.with_suffix(f".log.{i + 1}")

                if old_file.exists():
                    if new_file.exists():
                        try:
                            new_file.unlink()  # 删除最旧的文件
                        except OSError:
                            pass  # 忽略删除失败
                    try:
                        old_file.rename(new_file)
                    except OSError:
                        pass  # 忽略重命名失败

            # 重命名当前日志文件
            if self.log_file_path.exists():
                backup_file = self.log_file_path.with_suffix(".log.1")
                if backup_file.exists():
                    try:
                        backup_file.unlink()
                    except OSError:
                        pass
                try:
                    self.log_file_path.rename(backup_file)
                    logger.info(f"[灾害预警] 日志文件已轮转，备份文件: {backup_file}")
                except OSError as e:
                    logger.error(f"[灾害预警] 重命名主日志文件失败: {e}")

        except Exception as e:
            logger.error(f"[灾害预警] 日志轮转失败: {e}")
        finally:
            # 释放锁
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except Exception:
                    pass

    def get_log_summary(self) -> dict[str, Any]:
        """获取日志统计信息（支持新可读性格式）"""
        try:
            if not self.log_file_path.exists():
                return {"enabled": self.enabled, "log_exists": False}

            # 统计日志条目
            entry_count = 0
            sources = set()
            date_range = {"start": None, "end": None}
            file_size_mb = self.log_file_path.stat().st_size / (1024 * 1024)

            # 检查是否有轮转的旧日志文件并计算总大小
            for i in range(1, self.max_files + 1):
                old_file = self.log_file_path.with_suffix(f".log.{i}")
                if old_file.exists():
                    file_size_mb += old_file.stat().st_size / (1024 * 1024)

            # 读取文件内容
            with open(self.log_file_path, encoding="utf-8") as f:
                content = f.read()

            # 按分隔符分割条目
            entries = content.split(f"\n{'=' * 35}\n")

            for entry in entries:
                entry = entry.strip()
                if not entry or not entry.startswith("🕐 日志写入时间:"):
                    continue

                entry_count += 1

                try:
                    # 提取基本信息
                    lines = entry.split("\n")
                    for line in lines:
                        line = line.strip()
                        if line.startswith("🕐 日志写入时间:"):
                            timestamp_str = line.replace("🕐 日志写入时间:", "").strip()
                            try:
                                dt = datetime.strptime(
                                    timestamp_str, "%Y-%m-%d %H:%M:%S"
                                )
                                if date_range[
                                    "start"
                                ] is None or dt < datetime.strptime(
                                    date_range["start"], "%Y-%m-%d %H:%M:%S"
                                ):
                                    date_range["start"] = timestamp_str
                                if date_range["end"] is None or dt > datetime.strptime(
                                    date_range["end"], "%Y-%m-%d %H:%M:%S"
                                ):
                                    date_range["end"] = timestamp_str
                            except ValueError:
                                pass
                        elif line.startswith("📡 来源:"):
                            source = line.replace("📡 来源:", "").strip()
                            sources.add(source)
                except Exception as e:
                    logger.debug(f"[灾害预警] 解析日志条目失败: {e}")
                    continue

            return {
                "enabled": self.enabled,
                "log_exists": True,
                "log_file": str(self.log_file_path),
                "total_entries": entry_count,
                "data_sources": list(sources),
                "date_range": date_range,
                "file_size_mb": file_size_mb,
                "filter_stats": self.filter_stats.copy(),
                "format_version": "3.0",  # 新格式版本
            }

        except Exception as e:
            logger.error(f"[灾害预警] 获取日志统计失败: {e}")
            return {"enabled": self.enabled, "log_exists": False, "error": str(e)}

    def clear_logs(self):
        """清除所有日志文件"""
        try:
            # 删除主日志文件
            if self.log_file_path.exists():
                self.log_file_path.unlink()

            # 删除轮转的旧日志文件
            for i in range(1, self.max_files + 1):
                old_file = self.log_file_path.with_suffix(f".log.{i}")
                if old_file.exists():
                    old_file.unlink()

            # 清空去重缓存
            self.recent_event_hashes.clear()

            # 重置统计
            for key in self.filter_stats:
                self.filter_stats[key] = 0

            self.save_stats()  # 保存重置后的统计

            logger.info("[灾害预警] 所有日志文件已清除，去重缓存已清空")

        except Exception as e:
            logger.error(f"[灾害预警] 清除日志失败: {e}")

    def save_stats(self):
        """保存统计数据到文件"""
        try:
            data = {
                "filter_stats": self.filter_stats,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(self.stats_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"[灾害预警] 保存日志统计数据失败: {e}")

    def _load_stats(self):
        """加载统计数据"""
        try:
            if self.stats_file.exists():
                with open(self.stats_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self.filter_stats = data.get("filter_stats", self.filter_stats)
        except Exception as e:
            logger.error(f"[灾害预警] 加载日志统计数据失败: {e}")

    def _save_stats_if_needed(self):
        """按需保存统计（减少IO频率，例如每10次过滤保存一次）"""
        if self.filter_stats["total_filtered"] % 10 == 0:
            self.save_stats()


# 向后兼容的函数
def get_message_logger(config: dict[str, Any], plugin_name: str) -> MessageLogger:
    """获取消息记录器实例"""
    return MessageLogger(config, plugin_name)
