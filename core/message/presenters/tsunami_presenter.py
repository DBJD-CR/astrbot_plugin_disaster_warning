"""
海啸展示器。

该模块负责把海啸展示上下文转换为适合发送的文本内容，
同时覆盖通用海啸文本展示与日本气象厅海啸预报展示。
"""

from __future__ import annotations

from ....utils.time_converter import TimeConverter
from ...domain.event_context import TsunamiDisplayContext
from ...sources.source_catalog import get_source_entry
from .base_presenter import BasePresenter


class TsunamiAlertPresenter(BasePresenter):
    """通用海啸文本展示器。"""

    presenter_name = "tsunami_alert_presenter"

    @staticmethod
    def _format_coordinates(latitude: float, longitude: float) -> str:
        """把经纬度格式化为带方向标识的文本。"""
        lat_dir = "N" if latitude >= 0 else "S"
        lon_dir = "E" if longitude >= 0 else "W"
        return f"{abs(latitude):.2f}°{lat_dir}, {abs(longitude):.2f}°{lon_dir}"

    @classmethod
    def format_message(
        cls,
        display_context: TsunamiDisplayContext,
        options: dict | None = None,
    ) -> str:
        options = options or {}
        target_timezone = options.get("timezone")

        # 若调用方未指定时区，则按来源默认落到更符合使用习惯的展示时区。
        if not target_timezone and display_context.source_id:
            source_entry = get_source_entry(display_context.source_id)
            display_name = source_entry.display_name if source_entry is not None else ""
            if "日本" in display_name or "日本气象厅" in display_name:
                target_timezone = "UTC+9"
            else:
                target_timezone = "UTC+8"
        elif not target_timezone:
            target_timezone = "UTC+8"

        is_info = (
            display_context.message_type == "info" or display_context.level == "信息"
        )
        lines = ["🌊[海啸信息]" if is_info else "🌊[海啸预警]"]

        if display_context.title:
            lines.append(f"📋{display_context.title}")
        if display_context.level:
            lines.append(f"⚠️级别：{display_context.level}")
        if display_context.org_unit:
            lines.append(f"🏢发布：{display_context.org_unit}")
        if display_context.updated_at:
            lines.append(
                f"🕒最近更新时间：{TimeConverter.format_time(display_context.updated_at, target_timezone)}"
            )

        place_name = display_context.place_name or display_context.subtitle
        lat = display_context.latitude
        lon = display_context.longitude
        if place_name:
            if lat is not None and lon is not None:
                coords = cls._format_coordinates(lat, lon)
                lines.append(f"🌍震源：{place_name} ({coords})")
            else:
                lines.append(f"🌍震源：{place_name}")

        shock_parts = []
        if display_context.magnitude is not None:
            shock_parts.append(f"M {display_context.magnitude}")
        if display_context.depth is not None:
            shock_parts.append(f"深度{display_context.depth} km")
        if shock_parts:
            lines.append(f"🧭参数：{' / '.join(shock_parts)}")

        forecasts = display_context.forecasts
        if forecasts:
            lines.append(f"📈沿海预报：{len(forecasts)}个区域")
            # 信息类消息比预警类消息更偏概览，因此展示区域数略少。
            show_n = 2 if is_info else 3
            for forecast in forecasts[:show_n]:
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
            if len(forecasts) > show_n:
                lines.append(f"  ...其余{len(forecasts) - show_n}个区域")

        monitoring_stations = display_context.monitoring_stations
        if monitoring_stations:
            lines.append(f"📡监测实况：{len(monitoring_stations)}个站点")
            if not is_info:
                for station in monitoring_stations[:2]:
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

        if display_context.batch:
            lines.append(f"🧾批次：{display_context.batch}")
        if display_context.details_url:
            lines.append("🔗详情：")
            lines.append(display_context.details_url)

        map_name_mapping = {
            "earthquake": "震中图",
            "amplitude": "最大波幅图",
            "coastal": "沿岸预报图",
        }
        for map_key, map_url in display_context.map_urls.items():
            if isinstance(map_url, str) and map_url.strip():
                map_label = map_name_mapping.get(map_key, map_key)
                lines.append(f"🗺️{map_label}：")
                lines.append(map_url.strip())

        if display_context.code:
            lines.append(f"🔄事件编号：{display_context.code}")
        return "\n".join(lines)

    @classmethod
    def present(
        cls,
        display_context: TsunamiDisplayContext,
        options: dict | None = None,
    ) -> str:
        merged_options = dict(display_context.options or {})
        if options:
            merged_options.update(options)
        return cls.format_message(display_context, merged_options)


class JmaTsunamiPresenter(BasePresenter):
    """日本气象厅海啸预报文本展示器。"""

    presenter_name = "jma_tsunami_presenter"

    @classmethod
    def format_message(
        cls,
        display_context: TsunamiDisplayContext,
        options: dict | None = None,
    ) -> str:
        """格式化日本气象厅海啸预报消息。"""
        options = options or {}
        timezone = options.get("timezone", "UTC+8")

        lines = ["🌊[津波予報] 日本气象厅"]

        if display_context.title:
            lines.append(f"📋{display_context.title}")

        level_mapping = {
            "MajorWarning": "大津波警報",
            "Warning": "津波警報",
            "Watch": "津波注意報",
            "Unknown": "不明",
            "解除": "解除",
        }

        if display_context.level:
            japanese_level = level_mapping.get(
                display_context.level, display_context.level
            )
            lines.append(f"⚠️級別：{japanese_level}")

        if display_context.org_unit:
            lines.append(f"🏢発表：{display_context.org_unit}")

        if display_context.issued_at:
            display_time = display_context.issued_at
            if display_time.tzinfo is None:
                display_time = TimeConverter.parse_datetime(display_time).replace(
                    tzinfo=TimeConverter.TIMEZONES["JST"]
                )
            lines.append(
                f"⏰発表時刻：{TimeConverter.format_time(display_time, timezone)}"
            )

        forecasts = display_context.forecasts
        if forecasts:
            # 日本气象厅海啸预报会区分“预计立即到达”与普通区域，分别展示更利于阅读。
            immediate_areas: list[str] = []
            normal_areas: list[str] = []

            for forecast in forecasts:
                area_name = forecast.get("name", "")
                if not area_name:
                    continue
                if forecast.get("immediate", False):
                    immediate_areas.append(area_name)
                else:
                    normal_areas.append(area_name)

            if immediate_areas:
                lines.append("🚨预测将立即发生海啸的区域：")
                for area in immediate_areas[:3]:
                    lines.append(f"  • {area}")
                if len(immediate_areas) > 3:
                    lines.append(f"  ...其他{len(immediate_areas) - 3}区域")

            if normal_areas:
                lines.append("📍津波予報区域：")
                for area in normal_areas[:5]:
                    area_info = f"  • {area}"
                    curr_forecast = next(
                        (f for f in forecasts if f.get("name") == area), {}
                    )

                    arrival_time = curr_forecast.get("estimatedArrivalTime")
                    condition = curr_forecast.get("condition")
                    time_info = []
                    if arrival_time:
                        time_info.append(f"{arrival_time}")
                    if condition:
                        time_info.append(f"{condition}")
                    if time_info:
                        area_info += f" ({' '.join(time_info)})"

                    max_wave = curr_forecast.get("maxWaveHeight")
                    if max_wave:
                        area_info += f" 🌊{max_wave}"

                    lines.append(area_info)

                if len(normal_areas) > 5:
                    lines.append(f"  ...其他{len(normal_areas) - 5}区域")

        if display_context.code:
            lines.append(f"🔄事件ID：{display_context.code}")

        if display_context.level == "解除":
            lines.append("✅津波の心配はありません（无需担心海啸）")

        return "\n".join(lines)

    @classmethod
    def present(
        cls,
        display_context: TsunamiDisplayContext,
        options: dict | None = None,
    ) -> str:
        merged_options = dict(display_context.options or {})
        if options:
            merged_options.update(options)
        return cls.format_message(display_context, merged_options)
