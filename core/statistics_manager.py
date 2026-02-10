import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from astrbot.api import logger
from astrbot.api.star import StarTools

from ..models.models import (
    CHINA_PROVINCES,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from ..utils.formatters.weather import COLOR_LEVEL_EMOJI, SORTED_WEATHER_TYPES
from .event_deduplicator import EventDeduplicator


class StatisticsManager:
    """灾害预警统计管理器"""

    def __init__(self):
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_disaster_warning")
        self.stats_file = self.data_dir / "statistics.json"

        # 内存中的统计数据结构
        self.stats: dict[str, Any] = {
            "total_received": 0,  # 总接收次数（包括被过滤的）
            "total_events": 0,  # 独立事件数（去重后）
            "start_time": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "by_type": defaultdict(int),
            "by_source": defaultdict(int),
            "earthquake_stats": {
                "by_magnitude": defaultdict(int),  # 按震级区间统计
                "by_region": defaultdict(int),  # 按地区统计 (仅CENC正式)
                "max_magnitude": None,  # 记录最大震级事件：{value, event_id, place_name, time}
            },
            "weather_stats": {
                "by_level": defaultdict(int),  # 按预警级别统计：白、蓝、黄、橙、红
                "by_type": defaultdict(int),  # 按预警类型统计：暴雨、大风等
                "by_region": defaultdict(int),  # 按地区统计
            },
            "recent_pushes": [],  # 最近推送记录详情，用于展示
            "recent_event_ids": [],  # 最近处理的事件ID列表，用于重启后去重
            "hourly_counts": defaultdict(int),  # 小时级别统计，用于趋势图
            "daily_counts": defaultdict(int),  # 日级别统计，用于热力图
        }

        # 运行时去重集合
        self._recorded_event_ids = set()

        # 初始化去重器用于生成指纹 (使用默认配置)
        self.deduplicator = EventDeduplicator()

        # 加载历史数据
        self._load_stats()

    def record_push(self, event: DisasterEvent):
        """记录一次事件处理（无论是否推送）"""
        try:
            current_time = datetime.now(timezone.utc).isoformat()
            self.stats["last_updated"] = current_time

            # 兼容旧字段名或初始化新字段
            if "total_received" not in self.stats:
                self.stats["total_received"] = self.stats.get("total_pushes", 0)

            self.stats["total_received"] += 1

            source_id = event.source_id or event.source.value
            self.stats["by_source"][source_id] += 1

            # 记录独立事件数
            event_unique_id = self._get_unique_event_id(event)
            if event_unique_id not in self._recorded_event_ids:
                self.stats["total_events"] += 1
                self._recorded_event_ids.add(event_unique_id)
                # 更新持久化的ID列表
                self.stats["recent_event_ids"].append(event_unique_id)
                if len(self.stats["recent_event_ids"]) > 500:  # 保留最近500个ID
                    self.stats["recent_event_ids"] = self.stats["recent_event_ids"][
                        -500:
                    ]

                # 1. 基础分类统计 (仅统计独立事件)
                d_type = event.disaster_type.value
                self.stats["by_type"][d_type] += 1

                # 2. 详细统计 (仅统计独立事件)
                if isinstance(event.data, EarthquakeData):
                    self._record_earthquake_stats(event.data)
                elif isinstance(event.data, WeatherAlarmData):
                    self._record_weather_stats(event.data)
                
                # 3. 时间序列统计 (仅统计独立事件)
                self._record_time_series(event)

            # 3. 更新最近记录
            # 智能合并逻辑：针对同一数据源的同一地震事件（通过 event_id 标识），合并更新记录
            # 适用于所有地震类型（预警和情报），只要数据源支持多次更新
            is_merged = False

            if isinstance(event.data, EarthquakeData):
                # 获取真实的物理事件ID (优先使用 data.event_id，它是跨报文的唯一标识)
                real_event_id = event.data.event_id

                if real_event_id:
                    for i, record in enumerate(self.stats["recent_pushes"]):
                        # 严格检查：必须是同源 且 同一物理事件ID
                        # 注意：record.get("real_event_id") 是新字段，旧记录可能没有，回退检查 event_id
                        rec_source = record.get("source")
                        rec_real_id = record.get("real_event_id")
                        rec_legacy_id = record.get("event_id")

                        if rec_source == source_id:
                            # 匹配逻辑：优先匹配 real_event_id，其次尝试匹配 legacy_id
                            is_match = False
                            if rec_real_id and rec_real_id == real_event_id:
                                is_match = True
                            elif not rec_real_id and rec_legacy_id == real_event_id:
                                # 兼容旧记录：如果旧记录没有 real_event_id，但其 event_id 恰好等于当前的 real_event_id
                                is_match = True

                            # 匹配逻辑：优先匹配 real_event_id，其次尝试匹配 legacy_id
                            # 新增：尝试匹配 unique_id (指纹)，解决 CWA Report 等数据源 event_id 不稳定的问题
                            is_match = False
                            rec_unique_id = record.get("unique_id")

                            if rec_real_id and rec_real_id == real_event_id:
                                is_match = True
                            elif not rec_real_id and rec_legacy_id == real_event_id:
                                # 兼容旧记录：如果旧记录没有 real_event_id，但其 event_id 恰好等于当前的 real_event_id
                                is_match = True
                            elif rec_unique_id and rec_unique_id == event_unique_id:
                                # 指纹匹配：物理属性（时间地点震级）相同，视为同一事件
                                is_match = True

                            if is_match:
                                # 1. 保存旧记录到 history (防止历史信息丢失)
                                old_record = record.copy()
                                # 移除 history 字段避免嵌套递归
                                if "history" in old_record:
                                    del old_record["history"]

                                # 初始化或获取 history 列表
                                if "history" not in record:
                                    record["history"] = []

                                # 插入旧记录到 history 顶部
                                record["history"].insert(0, old_record)
                                # 限制 history 长度 (例如 50)
                                if len(record["history"]) > 50:
                                    record["history"] = record["history"][:50]

                                # 2. 更新当前记录
                                record["timestamp"] = current_time
                                record["event_id"] = event.id  # 更新为最新报文的ID
                                record["real_event_id"] = (
                                    real_event_id  # 确保设置 real_event_id
                                )
                                record["unique_id"] = event_unique_id  # 更新指纹
                                record["description"] = self._get_event_description(
                                    event
                                )
                                record["latitude"] = event.data.latitude
                                record["longitude"] = event.data.longitude
                                record["magnitude"] = event.data.magnitude
                                record["time"] = (
                                    event.data.shock_time.isoformat()
                                    if event.data.shock_time
                                    else None
                                )

                                # 记录更新次数
                                record["update_count"] = (
                                    record.get("update_count", 1) + 1
                                )

                                # 3. 将更新后的记录移动到列表顶部
                                updated_record = self.stats["recent_pushes"].pop(i)
                                self.stats["recent_pushes"].insert(0, updated_record)
                                is_merged = True
                                break

            if not is_merged:
                push_record = {
                    "timestamp": current_time,
                    "event_id": event.id,
                    "type": event.disaster_type.value,
                    "source": source_id,
                    "description": self._get_event_description(event),
                    "unique_id": event_unique_id,  # 记录唯一指纹
                    "update_count": 1,
                }

                # 为地震事件添加坐标和震级信息
                if isinstance(event.data, EarthquakeData):
                    push_record["latitude"] = event.data.latitude
                    push_record["longitude"] = event.data.longitude
                    push_record["magnitude"] = event.data.magnitude
                    push_record["time"] = (
                        event.data.shock_time.isoformat()
                        if event.data.shock_time
                        else None
                    )
                    push_record["real_event_id"] = event.data.event_id  # 记录物理事件ID
                elif isinstance(event.data, WeatherAlarmData):
                    push_record["time"] = (
                        event.data.issue_time.isoformat()
                        if event.data.issue_time
                        else None
                    )
                elif isinstance(event.data, TsunamiData):
                    push_record["time"] = (
                        event.data.issue_time.isoformat()
                        if event.data.issue_time
                        else None
                    )

                self.stats["recent_pushes"].insert(0, push_record)

            # 保持最近记录数量限制
            if len(self.stats["recent_pushes"]) > 100:
                self.stats["recent_pushes"] = self.stats["recent_pushes"][:100]

            # 自动保存
            self.save_stats()

        except Exception as e:
            logger.error(f"[灾害预警] 记录统计数据失败: {e}")

    def _get_unique_event_id(self, event: DisasterEvent) -> str:
        """获取用于去重的唯一事件ID - 基于地理位置和震级的模糊匹配"""
        if isinstance(event.data, EarthquakeData):
            # 使用 EventDeduplicator 的统一指纹生成逻辑
            return self.deduplicator.generate_event_fingerprint(event.data)

        return event.id

    def _record_earthquake_stats(self, data: EarthquakeData):
        """记录地震详细统计"""
        # 震级区间统计 (细化分段)
        mag = data.magnitude
        if mag is not None:
            if mag < 3.0:
                key = "< M3.0"
            elif 3.0 <= mag < 4.0:
                key = "M3.0 - M3.9"
            elif 4.0 <= mag < 5.0:
                key = "M4.0 - M4.9"
            elif 5.0 <= mag < 6.0:
                key = "M5.0 - M5.9"
            elif 6.0 <= mag < 7.0:
                key = "M6.0 - M6.9"
            elif 7.0 <= mag < 8.0:
                key = "M7.0 - M7.9"
            else:
                key = ">= M8.0"
            self.stats["earthquake_stats"]["by_magnitude"][key] += 1

            # 最大震级记录 (仅记录正式测定或特定可信源)
            # 过滤条件：必须是正式测定(info_type="正式测定") 或 可信度高的数据源(如CENC/USGS/JMA地震情报)
            is_reliable = False
            is_cenc_official = False

            # 1. 基础筛选：必须是地震情报类型 (排除EEW预警)
            if data.disaster_type == DisasterType.EARTHQUAKE:
                # 2. 进阶筛选：排除自动测定，只保留正式/审核后的数据
                # 如果没有info_type，为了保险起见默认不记录(防止混入测试或未知数据)
                if data.info_type:
                    info_lower = data.info_type.lower()

                    # CENC: 必须明确包含"正式"
                    if "正式" in data.info_type:
                        is_reliable = True
                        is_cenc_official = True

                    # USGS: 必须包含"reviewed"
                    elif "reviewed" in info_lower:
                        is_reliable = True

                    # JMA: 排除震度速报(ScalePrompt)，只保留包含详细震源信息的报告
                    # ScalePrompt (震度速报) 通常没有震级或不准，不计入统计
                    elif data.info_type in [
                        "Destination",
                        "ScaleAndDestination",
                        "DetailScale",
                    ]:
                        is_reliable = True

                    # JMA (中文描述兼容): "震源"通常对应震源情报，"各地"对应各地震度情报
                    # 排除单纯的"震度速报"
                    elif "震源" in data.info_type or "各地" in data.info_type:
                        is_reliable = True

            if is_reliable:
                current_max = self.stats["earthquake_stats"].get("max_magnitude")
                if current_max is None or mag > current_max.get("value", 0):
                    self.stats["earthquake_stats"]["max_magnitude"] = {
                        "value": mag,
                        "event_id": data.id,
                        "place_name": data.place_name,
                        "time": (
                            data.shock_time.isoformat()
                            if data.shock_time
                            else datetime.now(timezone.utc).isoformat()
                        ),
                        "source": data.source.value,  # 记录来源以便调试
                    }

            # CENC 正式测定地区统计
            if is_cenc_official:
                region = self._extract_region(data.place_name, strict=True)
                if region:
                    self.stats["earthquake_stats"]["by_region"][region] += 1

    def _record_weather_stats(self, data: WeatherAlarmData):
        """记录气象预警详细统计"""
        headline = data.headline or ""

        # 1. 预警级别统计
        level = "未知"
        for color, emoji in COLOR_LEVEL_EMOJI.items():
            if color in headline:
                # 存储带 Emoji 的键名，方便展示
                level = f"{emoji}{color}"
                break
        self.stats["weather_stats"]["by_level"][level] += 1

        # 2. 预警类型统计
        w_type = "其他"
        for name in SORTED_WEATHER_TYPES:
            if name in headline:
                w_type = name
                break
        self.stats["weather_stats"]["by_type"][w_type] += 1

        # 3. 地区统计 (尝试从 headline 提取)
        # 简单提取：取前两个字作为省份/地区，或者匹配已知省份
        region = self._extract_region(headline)
        self.stats["weather_stats"]["by_region"][region] += 1

    def _record_time_series(self, event: DisasterEvent):
        """记录时间序列统计"""
        from datetime import datetime, timezone
        
        # 使用事件时间或当前时间
        event_time = None
        if isinstance(event.data, EarthquakeData):
            event_time = event.data.shock_time
        elif isinstance(event.data, (WeatherAlarmData, TsunamiData)):
            event_time = event.data.issue_time
        
        if not event_time:
            event_time = datetime.now(timezone.utc)
        
        # 小时级别的key (用于24小时/7天趋势图)
        hour_key = event_time.strftime("%Y-%m-%d %H:00")
        self.stats["hourly_counts"][hour_key] += 1
        
        # 日级别的key (用于日历热力图)
        day_key = event_time.strftime("%Y-%m-%d")
        self.stats["daily_counts"][day_key] += 1
    
    def _extract_region(self, text: str, strict: bool = False) -> str | None:
        """从文本中提取地区（省份）信息"""
        if not text:
            return None if strict else "未知"

        # 优先匹配省份
        for p in CHINA_PROVINCES:
            if text.startswith(p):
                return p

        # 内蒙古/黑龙江特殊处理 (3个字)
        if text.startswith("内蒙古") or text.startswith("黑龙江"):
            # 上面的循环已经覆盖了（startswith），但为了保险起见检查一下
            pass

        if strict:
            return None

        # 如果不是省份开头，可能是具体的市或海域，尝试取前两个字
        # 比如 "南海海域", "东海海域"
        return text[:2]

    def _get_event_description(self, event: DisasterEvent) -> str:
        """生成简短的事件描述"""
        if isinstance(event.data, EarthquakeData):
            return f"M{event.data.magnitude} {event.data.place_name}"
        elif isinstance(event.data, TsunamiData):
            return f"{event.data.title} ({event.data.level})"
        elif isinstance(event.data, WeatherAlarmData):
            return f"{event.data.headline}"
        return "未知事件"

    def save_stats(self):
        """保存统计数据"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)

            # 将 defaultdict 转换为 dict 用于 JSON 序列化
            serializable_stats = self._prepare_for_serialization(self.stats)

            with open(self.stats_file, "w", encoding="utf-8") as f:
                json.dump(serializable_stats, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"[灾害预警] 保存统计文件失败: {e}")

    def _prepare_for_serialization(self, data: Any) -> Any:
        """递归将 defaultdict 转换为 dict"""
        if isinstance(data, defaultdict):
            return {k: self._prepare_for_serialization(v) for k, v in data.items()}
        elif isinstance(data, dict):
            return {k: self._prepare_for_serialization(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._prepare_for_serialization(i) for i in data]
        else:
            return data

    def reset_stats(self):
        """重置统计数据"""
        try:
            self.stats = {
                "total_received": 0,
                "total_events": 0,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "by_type": defaultdict(int),
                "by_source": defaultdict(int),
                "earthquake_stats": {
                    "by_magnitude": defaultdict(int),
                    "by_region": defaultdict(int),
                    "max_magnitude": None,
                },
                "weather_stats": {
                    "by_level": defaultdict(int),
                    "by_type": defaultdict(int),
                    "by_region": defaultdict(int),
                },
                "recent_pushes": [],
                "recent_event_ids": [],
                "hourly_counts": defaultdict(int),
                "daily_counts": defaultdict(int),
            }
            # 清空内存中的去重集合
            self._recorded_event_ids.clear()

            # 保存到文件
            self.save_stats()
            logger.info("[灾害预警] 统计数据已重置")

        except Exception as e:
            logger.error(f"[灾害预警] 重置统计数据失败: {e}")

    def _load_stats(self):
        """加载统计数据"""
        if not self.stats_file.exists():
            return

        try:
            with open(self.stats_file, encoding="utf-8") as f:
                saved_stats = json.load(f)

            # 恢复数据，保留默认值结构
            self._merge_stats(self.stats, saved_stats)

            # 恢复去重集合
            if "recent_event_ids" in self.stats:
                self._recorded_event_ids.update(self.stats["recent_event_ids"])

        except Exception as e:
            logger.error(f"[灾害预警] 加载统计数据失败: {e}")

    def _merge_stats(self, current: dict, saved: dict):
        """递归合并统计数据"""
        for k, v in saved.items():
            if k in current:
                if isinstance(current[k], defaultdict) and isinstance(v, dict):
                    # 恢复 defaultdict
                    for sub_k, sub_v in v.items():
                        current[k][sub_k] = sub_v
                elif isinstance(current[k], dict) and isinstance(v, dict):
                    self._merge_stats(current[k], v)
                else:
                    current[k] = v
            else:
                current[k] = v

    def get_summary(self) -> str:
        """获取统计摘要文本"""
        s = self.stats

        # 基础信息
        total = s.get("total_received", s.get("total_pushes", 0))
        text = [
            "📊 灾害预警统计报告",
            f"📅 统计开始时间: {s['start_time'][:19].replace('T', ' ')}",
            f"🔢 记录到的事件总数: {total}",
            f"🚨 去重后的事件总数: {s['total_events']}",
            "",
            "📈 分类统计:",
        ]

        # 类型统计
        type_map = {
            "earthquake": "地震",
            "earthquake_warning": "地震预警",
            "tsunami": "海啸",
            "weather_alarm": "气象",
        }
        for type_key, count in s["by_type"].items():
            type_name = type_map.get(type_key, type_key)
            text.append(f"{type_name}: {count}")

        # 地震详情
        text.extend(["", "🌍 地震震级分布:"])
        eq_stats = s["earthquake_stats"]["by_magnitude"]
        # 排序展示
        order = [
            "< M3.0",
            "M3.0 - M3.9",
            "M4.0 - M4.9",
            "M5.0 - M5.9",
            "M6.0 - M6.9",
            "M7.0 - M7.9",
            ">= M8.0",
        ]
        has_eq = False
        for key in order:
            count = eq_stats.get(key, 0)
            if count > 0:
                text.append(f"{key}: {count}")
                has_eq = True
        if not has_eq:
            text.append("(暂无数据)")

        # 地震地区分布 Top10
        eq_regions = s["earthquake_stats"].get("by_region", {})
        if eq_regions:
            sorted_eq_regions = sorted(
                eq_regions.items(), key=lambda x: x[1], reverse=True
            )
            if sorted_eq_regions:
                text.append("")
                text.append("📍 地震高发地区 (国内Top 10):")
                for r, c in sorted_eq_regions[:10]:
                    text.append(f"{r}: {c}")

        max_mag = s["earthquake_stats"].get("max_magnitude")
        if max_mag:
            source_val = max_mag.get("source")
            # 只有当source_val存在时才显示括号内容
            source_info = f" ({source_val})" if source_val else ""
            text.extend(
                [
                    "",
                    f"🔥 最大地震: M{max_mag['value']} {max_mag['place_name']}{source_info}",
                    "",
                ]
            )

        # 气象详情
        text.append("☁️ 气象预警分布:")
        text.append("")
        weather_level = s["weather_stats"]["by_level"]
        level_order = ["🔴红色", "🟠橙色", "🟡黄色", "🔵蓝色", "⚪白色", "未知"]
        has_weather = False

        # 统计类型分布
        weather_type = s["weather_stats"]["by_type"]
        sorted_types = sorted(weather_type.items(), key=lambda x: x[1], reverse=True)
        if sorted_types:
            text.append("类型Top10:")
            for t, c in sorted_types[:10]:
                text.append(f"{t}: {c}")

        # 统计地区分布 Top10
        weather_regions = s["weather_stats"].get("by_region", {})
        if weather_regions:
            sorted_w_regions = sorted(
                weather_regions.items(), key=lambda x: x[1], reverse=True
            )
            if sorted_w_regions:
                text.append("\n地区Top10:")
                for r, c in sorted_w_regions[:10]:
                    text.append(f"{r}: {c}")

        # 统计级别分布
        text.append("\n级别分布:")
        for level in level_order:
            count = weather_level.get(level, 0)
            if count > 0:
                text.append(f"{level}: {count}")
                has_weather = True

        if not has_weather and not sorted_types:
            text.append("(暂无数据)")

        # 数据源统计
        text.extend(["", "📡 数据源事件统计:"])
        # 按数量降序排列
        sorted_sources = sorted(
            s["by_source"].items(), key=lambda x: x[1], reverse=True
        )
        for source, count in sorted_sources[:10]:  # 显示前10个
            text.append(f"{source}: {count}")

        return "\n".join(text)
    
    def get_trend_data(self, hours: int = 24) -> list[dict[str, Any]]:
        """获取趋势数据（最近N小时）"""
        from datetime import datetime, timedelta, timezone
        
        result = []
        now = datetime.now(timezone.utc)
        tz_beijing = timezone(timedelta(hours=8))
        
        for i in range(hours):
            time_point = now - timedelta(hours=hours - i - 1)
            # 统计键名仍使用 UTC (保持与存储一致)
            hour_key_utc = time_point.strftime("%Y-%m-%d %H:00")
            
            # 展示时间转换为 UTC+8
            time_point_beijing = time_point.astimezone(tz_beijing)
            display_time = time_point_beijing.strftime("%m-%d %H:00")
            
            count = self.stats["hourly_counts"].get(hour_key_utc, 0)
            result.append({
                "time": display_time,
                "count": count
            })
        
        return result
    
    def get_heatmap_data(self, days: int = 180) -> list[dict[str, Any]]:
        """获取日历热力图数据（最近N天）"""
        from datetime import datetime, timedelta, timezone
        
        result = []
        now = datetime.now(timezone.utc)
        tz_beijing = timezone(timedelta(hours=8))
        
        for i in range(days):
            date_point = now - timedelta(days=days - i - 1)
            # 统计键名使用 UTC 日期 (保持与存储一致)
            day_key_utc = date_point.strftime("%Y-%m-%d")
            
            # 获取该点对应的北京时间日期
            date_point_beijing = date_point.astimezone(tz_beijing)
            display_date = date_point_beijing.strftime("%Y-%m-%d")
            
            count = self.stats["daily_counts"].get(day_key_utc, 0)
            result.append({
                "date": display_date,
                "count": count
            })
        
        return result
