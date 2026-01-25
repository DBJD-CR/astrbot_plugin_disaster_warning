"""
基础消息格式化器
"""

from datetime import datetime
from typing import Any

from ..time_converter import TimeConverter


class BaseMessageFormatter:
    """基础消息格式化器"""

    @staticmethod
    def format_coordinates(latitude: float, longitude: float) -> str:
        """格式化坐标显示"""
        lat_dir = "N" if latitude >= 0 else "S"
        lon_dir = "E" if longitude >= 0 else "W"
        return f"{abs(latitude):.2f}°{lat_dir}, {abs(longitude):.2f}°{lon_dir}"

    @staticmethod
    def format_time(dt: datetime, target_timezone: str = "UTC+8") -> str:
        """格式化时间显示 - 支持时区转换"""
        return TimeConverter.format_time(dt, target_timezone)

    @staticmethod
    def format_message(data: Any) -> str:
        """默认消息格式化"""
        lines = [f"🚨[{data.disaster_type.value}] 灾害预警 (基础格式)"]
        if hasattr(data, "id"):
            lines.append(f"📋ID: {data.id}")
        if hasattr(data, "shock_time") and data.shock_time:
            lines.append(f"⏰发震时间: {data.shock_time}")
        if hasattr(data, "place_name") and data.place_name:
            lines.append(f"📍地点: {data.place_name}")
        if hasattr(data, "raw_data") and data.raw_data:
            lines.append(f"📝数据: {data.raw_data}")
        return "\n".join(lines)
