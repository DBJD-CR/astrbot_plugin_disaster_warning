"""
海啸预警消息格式化器
"""

from ...models.data_source_config import get_data_source_config
from ...models.models import TsunamiData
from ..time_converter import TimeConverter
from .base import BaseMessageFormatter


class TsunamiFormatter(BaseMessageFormatter):
    """海啸预警格式化器"""

    @staticmethod
    def format_message(tsunami: TsunamiData, options: dict = None) -> str:
        """格式化海啸预警消息（区分信息/预警）"""
        options = options or {}
        target_timezone = options.get("timezone")

        # 时区推断
        if not target_timezone:
            config = get_data_source_config(tsunami.source.value)
            if config and (
                "日本" in config.display_name or "日本气象厅" in config.display_name
            ):
                target_timezone = "UTC+9"
            else:
                target_timezone = "UTC+8"

        message_type = getattr(tsunami, "message_type", "warning") or "warning"
        is_info = message_type == "info" or tsunami.level == "信息"

        lines = ["🌊[海啸信息]" if is_info else "🌊[海啸预警]"]

        # 标题与级别
        if tsunami.title:
            lines.append(f"📋{tsunami.title}")
        if tsunami.level:
            lines.append(f"⚠️级别：{tsunami.level}")

        # 发布与时间
        if tsunami.org_unit:
            lines.append(f"🏢发布：{tsunami.org_unit}")
        if tsunami.issue_time:
            lines.append(
                f"⏰发布时间：{TsunamiFormatter.format_time(tsunami.issue_time, target_timezone)}"
            )
        if getattr(tsunami, "update_time", None):
            lines.append(
                f"🕒更新时间：{TsunamiFormatter.format_time(tsunami.update_time, target_timezone)}"
            )

        # 震源事件概览
        place_name = getattr(tsunami, "place_name", None) or tsunami.subtitle
        lat = getattr(tsunami, "latitude", None)
        lon = getattr(tsunami, "longitude", None)

        if place_name:
            if lat is not None and lon is not None:
                coords = TsunamiFormatter.format_coordinates(lat, lon)
                lines.append(f"🌍震源：{place_name} ({coords})")
            else:
                lines.append(f"🌍震源：{place_name}")

        magnitude = getattr(tsunami, "magnitude", None)
        depth = getattr(tsunami, "depth", None)

        shock_parts = []
        if magnitude is not None:
            shock_parts.append(f"M {magnitude}")
        if depth is not None:
            shock_parts.append(f"深度{depth} km")
        if shock_parts:
            lines.append(f"🧭参数：{' / '.join(shock_parts)}")

        # 信息类：给摘要；预警类：给更详尽摘要
        if tsunami.forecasts:
            lines.append(f"📈沿海预报：{len(tsunami.forecasts)}个区域")
            show_n = 2 if is_info else 3
            for forecast in tsunami.forecasts[:show_n]:
                area_name = (
                    forecast.get("forecastArea")
                    or forecast.get("forecastPoint")
                    or forecast.get("name")
                    or ""
                )
                if not area_name:
                    continue
                area_info = f"  • {area_name}"

                grade = forecast.get("warningLevel") or forecast.get("grade")
                if grade:
                    area_info += f" [{grade}]"

                arrival_time = forecast.get("estimatedArrivalTime")
                if arrival_time:
                    area_info += f" 预计{arrival_time}到达"

                max_wave = forecast.get("maxWaveHeight")
                if max_wave:
                    area_info += f" 波高 {max_wave}cm"

                lines.append(area_info)

            if len(tsunami.forecasts) > show_n:
                lines.append(f"  ...其余{len(tsunami.forecasts) - show_n}个区域")

        if tsunami.monitoring_stations:
            lines.append(f"📡监测实况：{len(tsunami.monitoring_stations)}个站点")
            if not is_info:
                for station in tsunami.monitoring_stations[:2]:
                    station_name = (
                        station.get("stationName") or station.get("name") or "监测站"
                    )
                    location = station.get("location") or ""
                    wave = station.get("maxWaveHeight") or ""
                    station_line = f"  • {station_name}"
                    if location:
                        station_line += f"({location})"
                    if wave:
                        station_line += f" 最大波幅 {wave}cm"
                    lines.append(station_line)

        if getattr(tsunami, "batch", None):
            lines.append(f"🧾批次：{tsunami.batch}")

        details_url = getattr(tsunami, "details_url", None)
        if details_url:
            lines.append(f"🔗详情：{details_url}")

        map_urls = getattr(tsunami, "map_urls", {}) or {}
        map_name_mapping = {
            "earthquake": "震中图",
            "amplitude": "最大波幅图",
            "coastal": "沿岸预报图",
        }
        rendered_any_map = False
        for map_key, map_url in map_urls.items():
            if isinstance(map_url, str) and map_url.strip():
                rendered_any_map = True
                map_label = map_name_mapping.get(map_key, map_key)
                lines.append(f"🗺️{map_label}：{map_url}")

        # 兼容 map_urls 结构之外的异常情况：若是列表也尽量展示
        if not rendered_any_map and isinstance(map_urls, list):
            for idx, map_url in enumerate(map_urls, start=1):
                if isinstance(map_url, str) and map_url.strip():
                    rendered_any_map = True
                    lines.append(f"🗺️图件{idx}：{map_url}")

        if tsunami.code:
            lines.append(f"🔄事件编号：{tsunami.code}")

        return "\n".join(lines)


class JMATsunamiFormatter(BaseMessageFormatter):
    """日本气象厅海啸预报专用格式化器"""

    @staticmethod
    def format_message(tsunami: TsunamiData, options: dict = None) -> str:
        """格式化日本气象厅海啸预报消息 - 基于P2P实际字段"""
        options = options or {}
        timezone = options.get("timezone", "UTC+8")

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

        # 发布时间
        if tsunami.issue_time:
            # 如果时间没有时区信息，假定为JST(UTC+9)
            display_time = tsunami.issue_time
            if display_time.tzinfo is None:
                display_time = TimeConverter.parse_datetime(display_time).replace(
                    tzinfo=TimeConverter.TIMEZONES["JST"]
                )
            lines.append(
                f"⏰発表時刻：{JMATsunamiFormatter.format_time(display_time, timezone)}"
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
