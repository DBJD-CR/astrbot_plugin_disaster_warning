"""
海啸预警消息格式化器
"""

from datetime import timedelta, timezone

from .base import BaseMessageFormatter
from ...models.data_source_config import get_data_source_config
from ...models.models import TsunamiData


class TsunamiFormatter(BaseMessageFormatter):
    """海啸预警格式化器"""

    @staticmethod
    def format_message(tsunami: TsunamiData) -> str:
        """格式化海啸预警消息"""
        lines = ["🌊[海啸预警]"]

        # 标题和级别
        if tsunami.title:
            lines.append(f"📋{tsunami.title}")
        if tsunami.level:
            lines.append(f"⚠️级别：{tsunami.level}")

        # 发布单位
        if tsunami.org_unit:
            lines.append(f"🏢发布：{tsunami.org_unit}")

        # 发布时间
        if tsunami.issue_time:
            config = get_data_source_config(tsunami.source.value)
            # 判断时区：中国数据源使用UTC+8，日本数据源使用UTC+9
            if config and (
                "中国" in config.display_name
                or "中国海啸预警中心" in config.display_name
            ):
                timezone_str = "UTC+8"
            elif config and (
                "日本" in config.display_name or "日本气象厅" in config.display_name
            ):
                timezone_str = "UTC+9"
            else:
                timezone_str = "UTC+8"  # 默认使用中国时区
            lines.append(
                f"⏰发布时间：{TsunamiFormatter.format_time(tsunami.issue_time, timezone_str)}"
            )

        # 引发地震信息
        if tsunami.subtitle:
            lines.append(f"🌍震源：{tsunami.subtitle}")

        # 预报区域
        if tsunami.forecasts:
            # 显示前2个区域
            for i, forecast in enumerate(tsunami.forecasts[:2]):
                area_name = forecast.get("name", "")
                if area_name:
                    area_info = f"📍{area_name}"

                    # 警报级别
                    grade = forecast.get("grade", "")
                    if grade and grade != tsunami.level:
                        area_info += f" [{grade}]"

                    # 预计到达时间
                    arrival_time = forecast.get("estimatedArrivalTime", "")
                    if arrival_time:
                        area_info += f" 预计{arrival_time}到达"

                    # 预估波高
                    max_wave = forecast.get("maxWaveHeight", "")
                    if max_wave:
                        area_info += f" 波高{max_wave}cm"

                    lines.append(area_info)

            # 如果还有更多区域
            if len(tsunami.forecasts) > 2:
                lines.append(f"  ...等{len(tsunami.forecasts)}个预报区域")

        # 事件编码
        if tsunami.code:
            lines.append(f"🔄事件编号：{tsunami.code}")

        return "\n".join(lines)


class JMATsunamiFormatter(BaseMessageFormatter):
    """日本气象厅海啸预报专用格式化器"""

    @staticmethod
    def format_message(tsunami: TsunamiData) -> str:
        """格式化日本气象厅海啸预报消息 - 基于P2P实际字段"""
        lines = ["🌊[津波予報] 日本气象厅"]

        # 标题和级别 - 处理日文级别
        if tsunami.title:
            lines.append(f"📋{tsunami.title}")

        # 日文级别映射
        level_mapping = {
            "MajorWarning": "大津波警報",
            "Warning": "津波警報",
            "Watch": "津波注意報",
            "Unknown": "不明",
            "解除": "解除",
        }

        if tsunami.level:
            japanese_level = level_mapping.get(tsunami.level, tsunami.level)
            lines.append(f"⚠️級別：{japanese_level}")

        # 发布单位
        if tsunami.org_unit:
            lines.append(f"🏢発表：{tsunami.org_unit}")

        # 发布时间 - 将日本时间(UTC+9)转换为北京时间(UTC+8)显示
        if tsunami.issue_time:
            # 如果时间没有时区信息，假定为JST(UTC+9)
            display_time = tsunami.issue_time
            if display_time.tzinfo is None:
                display_time = display_time.replace(tzinfo=timezone(timedelta(hours=9)))
            lines.append(
                f"⏰発表時刻：{JMATsunamiFormatter.format_time(display_time, 'UTC+8')}"
            )

        # 预报区域 - 基于P2P实际字段结构
        if tsunami.forecasts:
            immediate_areas = []  # 直ちに来襦予想（立即预报区域）
            normal_areas = []  # 通常予報（常规预报区域）

            for forecast in tsunami.forecasts:
                area_name = forecast.get("name", "")
                if not area_name:
                    continue

                # 检查是否为立即来袭
                if forecast.get("immediate", False):
                    immediate_areas.append(area_name)
                else:
                    normal_areas.append(area_name)

            # 显示紧急区域
            if immediate_areas:
                lines.append("🚨预测将立即发生海啸的区域：")
                for area in immediate_areas[:3]:  # 显示前3个
                    lines.append(f"  • {area}")
                if len(immediate_areas) > 3:
                    lines.append(f"  ...其他{len(immediate_areas) - 3}区域")

            # 显示正常预报区域
            if normal_areas:
                lines.append("📍津波予報区域：")
                for area in normal_areas[:5]:  # 显示前5个
                    area_info = f"  • {area}"

                    # 查找对应的forecast对象
                    curr_forecast = next(
                        (f for f in tsunami.forecasts if f.get("name") == area), {}
                    )

                    # 添加预计到达时间
                    arrival_time = curr_forecast.get("estimatedArrivalTime")
                    condition = curr_forecast.get("condition")

                    time_info = []
                    if arrival_time:
                        time_info.append(f"{arrival_time}")
                    if condition:
                        time_info.append(f"{condition}")

                    if time_info:
                        area_info += f" ({' '.join(time_info)})"

                    # 添加波高信息
                    max_wave = curr_forecast.get("maxWaveHeight")
                    if max_wave:
                        area_info += f" 🌊{max_wave}"

                    lines.append(area_info)

                if len(normal_areas) > 5:
                    lines.append(f"  ...其他{len(normal_areas) - 5}区域")

        # 事件编码
        if tsunami.code:
            lines.append(f"🔄事件ID：{tsunami.code}")

        # 如果是解除报文，添加特殊说明
        if tsunami.level == "解除":
            lines.append("✅津波の心配はありません（无需担心海啸）")

        return "\n".join(lines)
