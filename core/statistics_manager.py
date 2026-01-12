import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from astrbot.api import logger
from astrbot.api.star import StarTools

from ..models.models import (
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
            "start_time": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "by_type": defaultdict(int),
            "by_source": defaultdict(int),
            "earthquake_stats": {
                "by_magnitude": defaultdict(int),  # 按震级区间统计
                "max_magnitude": None,  # 记录最大震级事件：{value, event_id, place_name, time}
            },
            "weather_stats": {
                "by_level": defaultdict(int),  # 按预警级别统计：白、蓝、黄、橙、红
                "by_type": defaultdict(int),  # 按预警类型统计：暴雨、大风等
            },
            "recent_pushes": [],  # 最近推送记录详情，用于展示
            "recent_event_ids": [],  # 最近处理的事件ID列表，用于重启后去重
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
            current_time = datetime.now().isoformat()
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

            # 3. 更新最近记录
            push_record = {
                "timestamp": current_time,
                "event_id": event.id,
                "type": event.disaster_type.value,
                "source": source_id,
                "description": self._get_event_description(event),
            }
            
            # 为地震事件添加坐标和震级信息（用于3D地球可视化）
            if isinstance(event.data, EarthquakeData):
                push_record["latitude"] = event.data.latitude
                push_record["longitude"] = event.data.longitude
                push_record["magnitude"] = event.data.magnitude
                push_record["time"] = event.data.shock_time.isoformat() if event.data.shock_time else None
            
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

            # 1. 基础筛选：必须是地震情报类型 (排除EEW预警)
            if data.disaster_type == DisasterType.EARTHQUAKE:
                # 2. 进阶筛选：排除自动测定，只保留正式/审核后的数据
                # 如果没有info_type，为了保险起见默认不记录(防止混入测试或未知数据)
                if data.info_type:
                    info_lower = data.info_type.lower()

                    # CENC: 必须明确包含"正式"
                    if "正式" in data.info_type:
                        is_reliable = True

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
                            else datetime.now().isoformat()
                        ),
                        "source": data.source.value,  # 记录来源以便调试
                    }

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
                "start_time": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "by_type": defaultdict(int),
                "by_source": defaultdict(int),
                "earthquake_stats": {
                    "by_magnitude": defaultdict(int),
                    "max_magnitude": None,
                },
                "weather_stats": {
                    "by_level": defaultdict(int),
                    "by_type": defaultdict(int),
                },
                "recent_pushes": [],
                "recent_event_ids": [],
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
