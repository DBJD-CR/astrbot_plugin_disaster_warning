"""
海啸预警处理器
包含中国海啸和 P2P 海啸相关处理器
"""

import json
from datetime import datetime, timezone
from typing import Any

from astrbot.api import logger

from ...models.models import (
    DataSource,
    DisasterEvent,
    TsunamiData,
)
from .base import BaseDataHandler


class TsunamiHandler(BaseDataHandler):
    """中国海啸预警处理器"""

    def __init__(self, message_logger=None):
        super().__init__("china_tsunami_fanstudio", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析中国海啸预警数据"""
        try:
            # 获取实际数据
            msg_data = self._extract_data(data)
            if not msg_data:
                logger.debug(f"[灾害预警] {self.source_id} 消息中没有有效数据")
                return None

            # 心跳包检测 - 在详细处理前进行快速过滤
            if self._is_heartbeat_message(msg_data):
                return None

            # 海啸数据可能包含多个事件，只处理第一个
            events = []
            if isinstance(msg_data, dict):
                events = [msg_data]
            elif isinstance(msg_data, list):
                events = msg_data

            if not events:
                return None

            tsunami_data = events[0]

            warning_info = tsunami_data.get("warningInfo", {}) or {}
            time_info = tsunami_data.get("timeInfo", {}) or {}
            shock_info = tsunami_data.get("shockInfo", {}) or {}
            details = tsunami_data.get("details", {}) or {}

            # 提取时间信息（新格式优先）
            issue_time_str = (
                time_info.get("alarmDate")
                or time_info.get("issueTime")
                or time_info.get("publishTime")
                or time_info.get("updateDate")
                or ""
            )
            update_time_str = time_info.get("updateDate") or ""
            shock_time_str = shock_info.get("shockTime") or ""

            issue_time = (
                self._parse_datetime(issue_time_str)
                if issue_time_str
                else datetime.now(timezone.utc)
            )
            update_time = (
                self._parse_datetime(update_time_str) if update_time_str else None
            )
            shock_time = (
                self._parse_datetime(shock_time_str) if shock_time_str else None
            )

            # 标题/级别兼容提取（兼容旧格式）
            level = (
                warning_info.get("level") or tsunami_data.get("level") or ""
            ).strip()
            title = (
                warning_info.get("title") or tsunami_data.get("title") or ""
            ).strip()

            # 当缺失 title 时尝试构造（避免空信息丢弃）
            if not title and level:
                if level == "信息":
                    title = "海啸信息"
                elif level == "解除":
                    title = "海啸解除通告"
                else:
                    title = f"海啸{level}警报"

            if not title:
                warning_msg = f"[灾害预警] {self.source_id} 海啸消息缺少标题，跳过处理"
                if self._should_log_warning("missing_tsunami_title", warning_msg):
                    logger.debug(warning_msg)
                return None

            # 信息/预警类型识别
            normalized_level = level.replace("级", "") if level else ""
            message_type = "info"
            if normalized_level and normalized_level not in {"信息"}:
                message_type = "warning"
            if "警报" in title or "预警" in title:
                message_type = "warning"

            # 字段兼容：新格式 forecasts/waterLevelMonitoring，旧格式 monitoringStations
            forecasts = tsunami_data.get("forecasts", []) or []
            monitoring_stations = (
                tsunami_data.get("waterLevelMonitoring")
                or tsunami_data.get("monitoringStations")
                or []
            )

            maps = details.get("maps", {}) or {}
            subtitle = (
                warning_info.get("subtitle")
                or warning_info.get("caption")
                or shock_info.get("placeName")
                or tsunami_data.get("placeName")
                or ""
            )
            org_unit = (
                warning_info.get("orgUnit")
                or tsunami_data.get("publishInfo", {}).get("unitName")
                or "中国自然资源部海啸预警中心"
            )

            event_id = str(tsunami_data.get("id", "") or "").strip()
            if not event_id:
                stable_parts = [
                    str(tsunami_data.get("code", "") or "").strip(),
                    str(
                        details.get("batch") or tsunami_data.get("batch") or ""
                    ).strip(),
                    str(title or "").strip(),
                    str(issue_time_str or "").strip(),
                ]
                stable_parts = [part for part in stable_parts if part]
                if stable_parts:
                    event_id = "tsunami_" + "|".join(stable_parts)
                else:
                    # 极端兜底：避免使用“当前时间戳”导致每条都被视为新事件
                    event_id = "tsunami_unknown"
                logger.debug(
                    f"[灾害预警] {self.source_id} 海啸消息缺少稳定id，已使用回退事件ID: {event_id}"
                )

            tsunami = TsunamiData(
                id=event_id,
                code=tsunami_data.get("code", ""),
                source=DataSource.FAN_STUDIO_TSUNAMI,
                title=title,
                level=level,
                subtitle=subtitle,
                org_unit=org_unit,
                issue_time=issue_time,
                update_time=update_time,
                shock_time=shock_time,
                message_type=message_type,
                place_name=shock_info.get("placeName") or tsunami_data.get("placeName"),
                latitude=shock_info.get("latitude") or tsunami_data.get("latitude"),
                longitude=shock_info.get("longitude") or tsunami_data.get("longitude"),
                depth=shock_info.get("depth") or tsunami_data.get("depth"),
                magnitude=shock_info.get("magnitude") or tsunami_data.get("magnitude"),
                batch=details.get("batch") or tsunami_data.get("batch"),
                forecasts=forecasts,
                monitoring_stations=monitoring_stations,
                estimated_arrival_time=tsunami_data.get("estimatedArrivalTime"),
                max_wave_height=tsunami_data.get("maxWaveHeight"),
                details_url=details.get("htmlUrl") or tsunami_data.get("htmlUrl"),
                map_urls={
                    "earthquake": maps.get("earthquakeMapUrl", ""),
                    "amplitude": maps.get("amplitudeMapUrl", ""),
                    "coastal": maps.get("coastalMapUrl", ""),
                },
                raw_data=tsunami_data,
            )

            logger.info(
                f"[灾害预警] 海啸预警解析成功: {tsunami.title} ({tsunami.level}), "
                f"发布时间: {tsunami.issue_time}"
            )

            return DisasterEvent(
                id=tsunami.id,
                data=tsunami,
                source=tsunami.source,
                disaster_type=tsunami.disaster_type,
            )
        except Exception as e:
            logger.error(
                f"[灾害预警] {self.source_id} 解析海啸预警数据失败: {e}, 数据内容: {data}"
            )
            return None


class JMATsunamiP2PHandler(BaseDataHandler):
    """日本气象厅海啸预报处理器 - P2P"""

    def __init__(self, message_logger=None):
        super().__init__("jma_tsunami_p2p", message_logger)

    def parse_message(self, message: str) -> DisasterEvent | None:
        """解析P2P海啸消息"""
        # 不再重复记录原始消息，WebSocket管理器已记录详细信息
        try:
            data = json.loads(message)

            # 根据code判断消息类型
            code = data.get("code")

            if code == 552:  # 津波予報
                logger.debug(f"[灾害预警] {self.source_id} 收到津波予報(code:552)")
                return self._parse_tsunami_data(data)
            else:
                logger.debug(f"[灾害预警] {self.source_id} 非海啸数据，code: {code}")
                return None

        except json.JSONDecodeError as e:
            logger.error(f"[灾害预警] {self.source_id} JSON解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"[灾害预警] {self.source_id} 消息处理失败: {e}")
            return None

    def _parse_tsunami_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析P2P海啸数据"""
        try:
            issue = data.get("issue", {})
            areas = data.get("areas", [])

            # 如果是被取消的预警，也应该推送
            cancelled = data.get("cancelled", False)

            # 确定预警级别 (areas中最严重的等级)
            max_grade = "Unknown"
            if cancelled:
                max_grade = "解除"
                title = "津波予報（解除）"
            else:
                grades = ["None", "Unknown", "Watch", "Warning", "MajorWarning"]
                max_grade_idx = 0
                for area in areas:
                    grade = area.get("grade", "Unknown")
                    if grade in grades:
                        idx = grades.index(grade)
                        if idx > max_grade_idx:
                            max_grade_idx = idx
                            max_grade = grade

                title_map = {
                    "MajorWarning": "大津波警報",
                    "Warning": "津波警報",
                    "Watch": "津波注意報",
                    "Unknown": "津波予報",
                }
                title = title_map.get(max_grade, "津波予報")

            tsunami = TsunamiData(
                id=data.get("id", ""),
                code=str(data.get("code", 552)),
                source=DataSource.P2P_TSUNAMI,
                title=title,
                level=max_grade,
                org_unit="日本气象厅",
                issue_time=self._parse_datetime(issue.get("time", "")),
                forecasts=areas,
                raw_data=data,
            )

            logger.info(
                f"[灾害预警] JMA海啸预报解析成功: {tsunami.title}, 时间: {tsunami.issue_time}"
            )

            return DisasterEvent(
                id=tsunami.id,
                data=tsunami,
                source=tsunami.source,
                disaster_type=tsunami.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] {self.source_id} 解析海啸数据失败: {e}")
            return None
