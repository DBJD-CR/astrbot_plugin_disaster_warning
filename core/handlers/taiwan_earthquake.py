"""
台湾地震报告处理器
包含 CWA (中央气象署) 地震报告相关处理器 (含图片)
"""

from typing import Any

from astrbot.api import logger

from ...models.models import (
    DataSource,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
)
from .base import BaseDataHandler


class CWAReportHandler(BaseDataHandler):
    """台湾中央气象署地震报告处理器 (含图) - FAN Studio"""

    def __init__(self, message_logger=None):
        super().__init__("cwa_fanstudio_report", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析台湾中央气象署地震报告数据"""
        try:
            # 获取实际数据 - 兼容多种格式
            msg_data = data.get("Data", {}) or data.get("data", {}) or data
            if not msg_data:
                logger.warning(f"[灾害预警] {self.source_id} 消息中没有有效数据")
                return None

            # CWA 报告通常不带 createTime (不同于EEW)，但会有 shockTime
            if "shockTime" not in msg_data or "imageURI" not in msg_data:
                logger.debug(f"[灾害预警] {self.source_id} 非CWA地震报告数据，跳过")
                return None

            # 增强数值解析健壮性
            try:
                lat = float(msg_data.get("latitude") or 0)
                lon = float(msg_data.get("longitude") or 0)
            except (ValueError, TypeError):
                lat = 0.0
                lon = 0.0

            earthquake = EarthquakeData(
                id=str(msg_data.get("id", "")),
                event_id=str(msg_data.get("id", "")),  # 报告ID通常就是事件ID
                source=DataSource.FAN_STUDIO_CWA_REPORT,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=self._parse_datetime(msg_data.get("shockTime", "")),
                latitude=lat,
                longitude=lon,
                depth=msg_data.get("depth"),
                magnitude=msg_data.get("magnitude"),
                place_name=msg_data.get("placeName", ""),
                # 报告特有字段
                image_uri=msg_data.get("imageURI"),
                shakemap_uri=msg_data.get("shakemapURI"),
                raw_data=msg_data,
            )

            logger.info(
                f"[灾害预警] CWA地震报告解析成功: {earthquake.place_name} (M {earthquake.magnitude}), 时间: {earthquake.shock_time}"
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] {self.source_id} 解析数据失败: {e}")
            return None
