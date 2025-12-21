"""
海啸预警处理器
包含中国海啸和 P2P 海啸相关处理器
"""

import json
from datetime import datetime
from typing import Any

from astrbot.api import logger

from .base import BaseDataHandler
from ...models.models import (
    DataSource,
    DisasterEvent,
    DisasterType,
    TsunamiData,
)


class TsunamiHandler(BaseDataHandler):
    """中国海啸预警处理器"""

    def __init__(self, message_logger=None):
        super().__init__("china_tsunami_fanstudio", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析中国海啸预警数据"""
        try:
            # 获取实际数据 - 兼容多种格式
            msg_data = data.get("Data", {}) or data.get("data", {}) or data
            if not msg_data:
                logger.debug(f"[灾害预警] {self.source_id} 消息中没有有效数据")
                return None

            # 记录数据获取情况用于调试
            if "Data" in data:
                logger.debug(f"[灾害预警] {self.source_id} 使用Data字段获取数据")
            elif "data" in data:
                logger.debug(f"[灾害预警] {self.source_id} 使用data字段获取数据")
            else:
                logger.debug(f"[灾害预警] {self.source_id} 使用整个消息作为数据")

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

            # 提取真实的时间信息 - 优先使用alarmDate作为发布时间
            time_info = tsunami_data.get("timeInfo", {})
            issue_time_str = (
                time_info.get("alarmDate")
                or time_info.get("issueTime")
                or time_info.get("publishTime")
                or time_info.get("updateDate")
                or ""
            )

            if issue_time_str:
                issue_time = self._parse_datetime(issue_time_str)
            else:
                # 后备方案：使用当前时间
                issue_time = datetime.now()

            # 验证关键字段，防止空信息推送
            title = tsunami_data.get("warningInfo", {}).get("title", "")
            level = tsunami_data.get("warningInfo", {}).get("level", "")

            if not title:
                # 只有在非心跳包情况下才记录警告，且避免重复警告
                if not self._is_heartbeat_message(msg_data):
                    warning_msg = f"[灾害预警] {self.source_id} 海啸预警缺少标题信息，跳过处理"
                    if self._should_log_warning("missing_tsunami_title", warning_msg):
                        logger.debug(warning_msg)
                return None

            tsunami = TsunamiData(
                id=tsunami_data.get("id", "") or str(int(datetime.now().timestamp())),
                code=tsunami_data.get("code", ""),
                source=DataSource.FAN_STUDIO_TSUNAMI,
                title=title,
                level=level,
                subtitle=tsunami_data.get("warningInfo", {}).get("caption", ""),
                org_unit=tsunami_data.get("publishInfo", {}).get("unitName", "中国自然资源部海啸预警中心"),
                issue_time=issue_time,
                monitoring_stations=tsunami_data.get("monitoringStations", []),
                estimated_arrival_time=tsunami_data.get("estimatedArrivalTime"),
                max_wave_height=tsunami_data.get("maxWaveHeight"),
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
