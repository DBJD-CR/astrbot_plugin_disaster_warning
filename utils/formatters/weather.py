"""
气象预警消息格式化器
"""

from .base import BaseMessageFormatter
from ...models.models import WeatherAlarmData


class WeatherFormatter(BaseMessageFormatter):
    """气象预警格式化器"""

    @staticmethod
    def format_message(weather: WeatherAlarmData) -> str:
        """格式化气象预警消息"""
        lines = ["⛈️[气象预警]"]

        # 标题
        if weather.headline:
            lines.append(f"📋{weather.headline}")

        # 描述
        if weather.description:
            desc = weather.description
            if len(desc) > 384:
                desc = desc[:381] + "..."
            lines.append(f"📝{desc}")

        # 发布时间
        if weather.issue_time:
            lines.append(
                f"⏰生效时间：{WeatherFormatter.format_time(weather.issue_time)}"
            )

        return "\n".join(lines)
