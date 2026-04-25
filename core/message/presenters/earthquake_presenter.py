"""
地震展示器。

该模块负责把地震展示上下文转换为适合发送的文本内容，
覆盖中国、台湾、日本、全球地震等多类来源。
其中既包含通用格式化辅助函数，也包含各来源独立的展示器实现。
"""

from __future__ import annotations

from ....utils.converters import ScaleConverter
from ....utils.time_converter import TimeConverter
from ...domain.event_context import EarthquakeDisplayContext
from ...services.geo.intensity_service import IntensityCalculator
from .base_presenter import BasePresenter


def _format_coordinates(latitude: float, longitude: float) -> str:
    """把经纬度格式化为带方向标识的文本。"""
    lat_dir = "N" if latitude >= 0 else "S"
    lon_dir = "E" if longitude >= 0 else "W"
    return f"{abs(latitude):.2f}°{lat_dir}, {abs(longitude):.2f}°{lon_dir}"


def _get_intensity_emoji(value, is_eew: bool = True, is_shindo: bool = False) -> str:
    """根据烈度或震度值选择对应的颜色图标。"""
    if value is None:
        return ""

    # 预警场景与普通情报场景使用两套图形，便于视觉区分。
    circles = ["⚪", "🔵", "🟢", "🟡", "🟠", "🔴", "🟣"]
    squares = ["⬜", "🟦", "🟩", "🟨", "🟧", "🟥", "🟪"]
    emojis = circles if is_eew else squares

    try:
        val_str = str(value)
        num_val = None
        import re

        match = re.search(r"(\d+(\.\d+)?)", val_str)
        if match:
            num_val = float(match.group(1))

        idx = 0
        if is_shindo:
            # 日本、台湾震度体系既可能传入数值，也可能传入带符号的字符串，
            # 因此这里同时兼容数字阈值判断与字符串兜底识别。
            if num_val is not None:
                if num_val >= 9:
                    if num_val < 20:
                        idx = 0
                    elif num_val < 30:
                        idx = 1
                    elif num_val < 40:
                        idx = 2
                    elif num_val < 45:
                        idx = 3
                    elif num_val < 55:
                        idx = 4
                    elif num_val < 65:
                        idx = 5
                    else:
                        idx = 6
                else:
                    if num_val < 1.5:
                        idx = 0
                    elif num_val < 2.5:
                        idx = 1
                    elif num_val < 3.5:
                        idx = 2
                    elif num_val < 4.5:
                        idx = 3
                    elif num_val < 5.5:
                        idx = 4
                    elif num_val < 6.5:
                        idx = 5
                    else:
                        idx = 6
            elif "7" in val_str:
                idx = 6
            elif "6" in val_str:
                idx = 5
            elif "5" in val_str:
                idx = 4
            elif "4" in val_str:
                idx = 3
            elif "3" in val_str:
                idx = 2
            elif "2" in val_str:
                idx = 1
            else:
                idx = 0
        else:
            if num_val is not None:
                if num_val < 2.5:
                    idx = 0
                elif num_val < 4.5:
                    idx = 1
                elif num_val < 5.5:
                    idx = 2
                elif num_val < 6.5:
                    idx = 3
                elif num_val < 8.5:
                    idx = 4
                elif num_val < 10.5:
                    idx = 5
                else:
                    idx = 6
            else:
                idx = 0
        return emojis[idx]
    except Exception:
        return ""


def _format_depth(depth: float) -> str:
    """格式化震源深度文本。"""
    if depth == 0.0:
        return "极浅"
    return f"{depth} km"


def _resolve_options(
    display_context: EarthquakeDisplayContext,
    options: dict | None = None,
) -> dict:
    """合并上下文内置选项与调用时传入选项。"""
    merged = dict(display_context.options or {})
    if options:
        merged.update(options)
    return merged


def _is_earthquake_view(data) -> bool:
    """判断输入对象是否具备地震展示所需的基础字段。"""
    return all(
        hasattr(data, attr)
        for attr in ["title", "latitude", "longitude", "magnitude", "depth"]
    )


def _resolve_report_num(data: EarthquakeDisplayContext) -> int:
    """获取合法的第几报值。"""
    if isinstance(data.report_num, int) and data.report_num > 0:
        return data.report_num
    return 1


def _resolve_shock_time(display_context: EarthquakeDisplayContext):
    """解析展示时使用的发震时间。"""
    return display_context.occurred_at


def _append_local_estimation(
    lines: list[str],
    display_context: EarthquakeDisplayContext,
) -> None:
    """把本地影响预估信息附加到文本尾部。"""
    local_est = display_context.local_estimation
    if not local_est:
        return

    dist = local_est.get("distance", 0.0)
    inte = local_est.get("intensity", 0.0)
    place = local_est.get("place_name", "本地")
    desc = IntensityCalculator.get_intensity_description(inte)

    lines.append("")
    lines.append(f"📍{place}预估：")
    lines.append(f"距离震中 {dist:.1f} km，预估最大烈度 {inte:.1f} ({desc})")


class CeaEewPresenter(BasePresenter):
    """中国地震预警网展示器。"""

    presenter_name = "cea_eew_presenter"

    @classmethod
    def format_message(
        cls, data: EarthquakeDisplayContext, options: dict | None = None
    ) -> str:
        if not _is_earthquake_view(data):
            return "🚨[地震预警] 数据类型错误"

        merged_options = dict(options or {})
        timezone = merged_options.get("timezone", "UTC+8")

        # 省级来源存在时，优先展示更具体的属地机构名称。
        source_name = "中国地震预警网"
        if data.province:
            source_name = f"{data.province}地震局"

        lines = [f"🚨[地震预警] {source_name}"]

        report_num = _resolve_report_num(data)
        is_final = data.is_final
        report_info = f"第 {report_num} 报"
        if is_final:
            report_info += "(最终报)"
        lines.append(f"📋{report_info}")

        shock_time = _resolve_shock_time(data)
        if shock_time:
            lines.append(
                f"⏰发震时间：{TimeConverter.format_time(shock_time, timezone)}"
            )

        if data.title and data.latitude is not None and data.longitude is not None:
            coords = _format_coordinates(data.latitude, data.longitude)
            lines.append(f"📍震中：{data.title} ({coords})")

        if data.magnitude is not None:
            lines.append(f"📊震级：M {data.magnitude:.1f}")

        if data.depth is not None:
            lines.append(f"🏔️深度：{_format_depth(data.depth)}")

        if data.intensity is not None:
            emoji = _get_intensity_emoji(data.intensity, is_eew=True, is_shindo=False)
            lines.append(f"💥预估最大烈度：{data.intensity} {emoji}")

        return "\n".join(lines)

    @classmethod
    def present(
        cls,
        display_context: EarthquakeDisplayContext,
        options: dict | None = None,
    ) -> str:
        rendered = cls.format_message(
            display_context, _resolve_options(display_context, options)
        )
        if not _is_earthquake_view(display_context):
            return rendered
        lines = rendered.split("\n") if rendered else []
        # 若正文尚未包含本地预估，则在尾部补充，避免重复展示。
        if not any("距离震中" in line for line in lines):
            _append_local_estimation(lines, display_context)
        return "\n".join(lines)


class CwaEewPresenter(BasePresenter):
    """台湾中央气象署地震预警展示器。"""

    presenter_name = "cwa_eew_presenter"

    @classmethod
    def format_message(
        cls, data: EarthquakeDisplayContext, options: dict | None = None
    ) -> str:
        if not _is_earthquake_view(data):
            return "🚨[地震预警] 数据类型错误"

        merged_options = dict(options or {})
        timezone = merged_options.get("timezone", "UTC+8")
        lines = ["🚨[地震预警] 台湾中央气象署"]

        report_num = _resolve_report_num(data)
        is_final = data.is_final
        report_info = f"第 {report_num} 报"
        if is_final:
            report_info += "(最终报)"
        lines.append(f"📋{report_info}")

        shock_time = _resolve_shock_time(data)
        if shock_time:
            lines.append(
                f"⏰发震时间：{TimeConverter.format_time(shock_time, timezone)}"
            )

        if data.title and data.latitude is not None and data.longitude is not None:
            coords = _format_coordinates(data.latitude, data.longitude)
            lines.append(f"📍震中：{data.title} ({coords})")

        if data.magnitude is not None:
            lines.append(f"📊震级：M {data.magnitude:.1f}")

        if data.depth is not None:
            lines.append(f"🏔️深度：{_format_depth(data.depth)}")

        if data.scale is not None:
            scale_display = ScaleConverter.format_jma_cwa_scale_display(data.scale)
            emoji = _get_intensity_emoji(data.scale, is_eew=True, is_shindo=True)
            lines.append(f"💥预估最大震度：{scale_display} {emoji}")

        return "\n".join(lines)

    @classmethod
    def present(
        cls,
        display_context: EarthquakeDisplayContext,
        options: dict | None = None,
    ) -> str:
        rendered = cls.format_message(
            display_context, _resolve_options(display_context, options)
        )
        if not _is_earthquake_view(display_context):
            return rendered

        lines = rendered.split("\n") if rendered else []
        impact_area = display_context.impact_area
        if (
            isinstance(impact_area, str)
            and impact_area.strip()
            and not any("影响区域：" in line for line in lines)
        ):
            # 优先把影响区域贴到震度行后面，使核心信息尽量聚合在一起。
            inserted = False
            for idx, line in enumerate(lines):
                if line.startswith("💥预估最大震度："):
                    lines[idx] = f"{line}（影响区域：{impact_area.strip()}）"
                    inserted = True
                    break
            if not inserted:
                lines.append(f"⚠️影响区域：{impact_area.strip()}")

        if not any("距离震中" in line for line in lines):
            _append_local_estimation(lines, display_context)
        return "\n".join(lines)


class JmaEewPresenter(BasePresenter):
    """日本气象厅紧急地震速报展示器。"""

    presenter_name = "jma_eew_presenter"

    @classmethod
    def format_message(
        cls, data: EarthquakeDisplayContext, options: dict | None = None
    ) -> str:
        if not _is_earthquake_view(data):
            return "🚨[紧急地震速报] 数据类型错误"

        merged_options = dict(options or {})
        timezone = merged_options.get("timezone", "UTC+8")
        if data.is_cancel:
            # 取消报单独走极简格式，避免保留无效的震中与震级信息。
            updates = _resolve_report_num(data)
            return (
                f"🚨[紧急地震速报] [取消] 日本气象厅\n"
                f"📋第 {updates} 报 (取消报)\n"
                "📝之前的紧急地震速报已取消"
            )

        warning_type = data.jma_issue_type or "予报"
        if not data.jma_issue_type and data.scale is not None and data.scale >= 4.5:
            warning_type = "警报"

        header_tags = []
        if data.is_training:
            header_tags.append("训练")
        if data.is_assumption:
            header_tags.append("PLUM法所得假定震源")
        # 训练报、假定震源等附加标签统一拼接在标题中，便于用户第一眼识别消息性质。
        tag_str = f" [{'/'.join(header_tags)}]" if header_tags else ""
        lines = [f"🚨[紧急地震速报] [{warning_type}]{tag_str} 日本气象厅"]

        report_num = _resolve_report_num(data)
        is_final = data.is_final
        report_info = f"第 {report_num} 报"
        if is_final:
            report_info += "(最终报)"
        lines.append(f"📋{report_info}")

        shock_time = _resolve_shock_time(data)
        if shock_time:
            display_time = shock_time
            if getattr(display_time, "tzinfo", None) is None:
                display_time = TimeConverter.parse_datetime(display_time).replace(
                    tzinfo=TimeConverter._get_timezone("Asia/Tokyo")
                )
            lines.append(
                f"⏰发震时间：{TimeConverter.format_time(display_time, timezone)}"
            )

        if data.title and data.latitude is not None and data.longitude is not None:
            coords = _format_coordinates(data.latitude, data.longitude)
            lines.append(f"📍震中：{data.title} ({coords})")

        if data.magnitude is not None:
            lines.append(f"📊震级：M {data.magnitude:.1f}")

        if data.depth is not None:
            lines.append(f"🏔️深度：{_format_depth(data.depth)}")

        if data.scale is not None:
            scale_display = ScaleConverter.format_jma_cwa_scale_display(data.scale)
            emoji = _get_intensity_emoji(data.scale, is_eew=True, is_shindo=True)
            lines.append(f"💥预估最大震度：{scale_display} {emoji}")
        elif data.intensity is not None:
            intensity_display = ScaleConverter.format_jma_cwa_scale_display(
                data.intensity
            )
            emoji = _get_intensity_emoji(data.intensity, is_eew=True, is_shindo=True)
            lines.append(f"💥预估最大震度：{intensity_display} {emoji}")

        return "\n".join(lines)

    @classmethod
    def present(
        cls,
        display_context: EarthquakeDisplayContext,
        options: dict | None = None,
    ) -> str:
        rendered = cls.format_message(
            display_context, _resolve_options(display_context, options)
        )
        if not _is_earthquake_view(display_context):
            return rendered

        lines = rendered.split("\n") if rendered else []

        jma_warning_areas = display_context.jma_warning_areas
        if (
            isinstance(jma_warning_areas, list)
            and jma_warning_areas
            and not any(line.startswith("⚠️警报区域：") for line in lines)
        ):
            lines.append("⚠️警报区域：")
            # 多区域场景按固定数量分行，避免单行过长影响阅读。
            chunk_size = 3
            for i in range(0, len(jma_warning_areas), chunk_size):
                chunk = [
                    str(item).strip()
                    for item in jma_warning_areas[i : i + chunk_size]
                    if str(item).strip()
                ]
                if chunk:
                    lines.append("  " + "、".join(chunk))

        jma_warn_area = display_context.jma_warn_area
        if (
            isinstance(jma_warn_area, str)
            and jma_warn_area.strip()
            and not any(line.startswith("⚠️警报区域：") for line in lines)
        ):
            lines.append(f"⚠️警报区域：{jma_warn_area.strip()}")

        jma_warning_area_ranges = display_context.jma_warning_area_ranges
        if isinstance(jma_warning_area_ranges, list):
            for shindo_range in jma_warning_area_ranges:
                if (
                    isinstance(shindo_range, str)
                    and shindo_range.strip()
                    and not any(
                        line.startswith("💥预估震度范围：")
                        and shindo_range.strip() in line
                        for line in lines
                    )
                ):
                    lines.append(f"💥预估震度范围：{shindo_range.strip()}")

        if not any("距离震中" in line for line in lines):
            _append_local_estimation(lines, display_context)
        return "\n".join(lines)


class CencEarthquakePresenter(BasePresenter):
    """中国地震台网地震测定展示器。"""

    presenter_name = "cenc_earthquake_presenter"

    @staticmethod
    def _format_coordinates(latitude: float, longitude: float) -> str:
        lat_dir = "N" if latitude >= 0 else "S"
        lon_dir = "E" if longitude >= 0 else "W"
        return f"{abs(latitude):.2f}°{lat_dir}, {abs(longitude):.2f}°{lon_dir}"

    @staticmethod
    def _format_depth(depth: float) -> str:
        if depth == 0.0:
            return "极浅"
        return f"{depth} km"

    @staticmethod
    def _determine_measurement_type(data: EarthquakeDisplayContext) -> str:
        """判断当前测定属于自动测定还是正式测定。"""
        info_type = data.jma_issue_type.strip() or str(
            data.metadata.get("info_type") or data.metadata.get("infoTypeName") or ""
        )
        info_type_lower = info_type.lower()
        if "正式测定" in info_type or "reviewed" in info_type_lower:
            return "正式测定"
        if "自动测定" in info_type or "automatic" in info_type_lower:
            return "自动测定"
        return "自动测定"

    @classmethod
    def format_message(
        cls, data: EarthquakeDisplayContext, options: dict | None = None
    ) -> str:
        if not _is_earthquake_view(data):
            return "🚨[地震情报] 数据类型错误"

        merged_options = dict(options or {})
        timezone = merged_options.get("timezone", "UTC+8")
        # 中国地震台网测定结果会区分自动测定与正式测定，直接体现在标题中。
        measurement_type = cls._determine_measurement_type(data)
        lines = [f"🚨[地震情报] 中国地震台网 [{measurement_type}]"]

        shock_time = _resolve_shock_time(data)
        if shock_time:
            lines.append(
                f"⏰发震时间：{TimeConverter.format_time(shock_time, timezone)}"
            )
        if data.title and data.latitude is not None and data.longitude is not None:
            coords = cls._format_coordinates(data.latitude, data.longitude)
            lines.append(f"📍震中：{data.title} ({coords})")
        if data.magnitude is not None:
            lines.append(f"📊震级：M {data.magnitude:.1f}")
        if data.depth is not None:
            lines.append(f"🏔️深度：{cls._format_depth(data.depth)}")
        if data.intensity is not None:
            lines.append(f"💥最大烈度：{data.intensity}")
        return "\n".join(lines)

    @classmethod
    def present(
        cls,
        display_context: EarthquakeDisplayContext,
        options: dict | None = None,
    ) -> str:
        return cls.format_message(
            display_context, _resolve_options(display_context, options)
        )


class UsgsEarthquakePresenter(BasePresenter):
    """美国地质调查局地震情报展示器。"""

    presenter_name = "usgs_earthquake_presenter"

    @staticmethod
    def _format_coordinates(latitude: float, longitude: float) -> str:
        lat_dir = "N" if latitude >= 0 else "S"
        lon_dir = "E" if longitude >= 0 else "W"
        return f"{abs(latitude):.2f}°{lat_dir}, {abs(longitude):.2f}°{lon_dir}"

    @staticmethod
    def _format_depth(depth: float) -> str:
        if depth == 0.0:
            return "极浅"
        return f"{depth} km"

    @staticmethod
    def _determine_measurement_type(data: EarthquakeDisplayContext) -> str:
        """根据附加信息判断测定类型。"""
        info_type = data.jma_issue_type.strip() or str(
            data.metadata.get("info_type") or data.metadata.get("infoTypeName") or ""
        )
        info_type_lower = info_type.lower()
        if info_type_lower == "reviewed":
            return "正式测定"
        if info_type_lower == "automatic":
            return "自动测定"
        return "自动测定"

    @classmethod
    def format_message(
        cls, data: EarthquakeDisplayContext, options: dict | None = None
    ) -> str:
        if not _is_earthquake_view(data):
            return "🚨[地震情报] 数据类型错误"

        merged_options = dict(options or {})
        timezone = merged_options.get("timezone", "UTC+8")
        # 美国地质调查局同样可能区分自动结果与复核结果。
        measurement_type = cls._determine_measurement_type(data)
        lines = [f"🚨[地震情报] 美国地质调查局(USGS) [{measurement_type}]"]

        shock_time = _resolve_shock_time(data)
        if shock_time:
            lines.append(
                f"⏰发震时间：{TimeConverter.format_time(shock_time, timezone)}"
            )
        if data.title and data.latitude is not None and data.longitude is not None:
            coords = cls._format_coordinates(data.latitude, data.longitude)
            lines.append(f"📍震中：{data.title} ({coords})")
        if data.magnitude is not None:
            lines.append(f"📊震级：M {data.magnitude:.1f}")
        if data.depth is not None:
            lines.append(f"🏔️深度：{cls._format_depth(data.depth)}")
        return "\n".join(lines)

    @classmethod
    def present(
        cls,
        display_context: EarthquakeDisplayContext,
        options: dict | None = None,
    ) -> str:
        return cls.format_message(
            display_context, _resolve_options(display_context, options)
        )


class JmaEarthquakeInfoPresenter(BasePresenter):
    """日本气象厅地震情报展示器。"""

    presenter_name = "jma_earthquake_info_presenter"

    @staticmethod
    def _determine_info_type(data: EarthquakeDisplayContext) -> str:
        """推断日本气象厅地震情报的展示类别。"""
        info_type = data.jma_issue_type or ""
        type_mapping = {
            "ScalePrompt": "震度速报",
            "Destination": "震源相关情报",
            "ScaleAndDestination": "震度・震源相关情报",
            "DetailScale": "各地震度相关情报",
            "Foreign": "远地地震相关情报",
            "Other": "其他情报",
        }

        if info_type in type_mapping:
            return type_mapping[info_type]
        if info_type and any("\u4e00" <= char <= "\u9fff" for char in info_type):
            return info_type
        # 当震中与震级尚未明确时，更倾向视为震度速报场景。
        if (data.title == "未知地点" or not data.title) and (
            data.magnitude is None or data.magnitude == -1.0
        ):
            return "震度速报"
        if data.scale is None:
            return "震源相关情报"
        return "震源・震度情报"

    @classmethod
    def format_message(
        cls, data: EarthquakeDisplayContext, options: dict | None = None
    ) -> str:
        if not _is_earthquake_view(data):
            return "🚨[地震情报] 数据类型错误"

        merged_options = dict(options or {})
        timezone = merged_options.get("timezone", "UTC+8")
        info_type = cls._determine_info_type(data)

        revision_text = (
            data.revision.strip()
            if hasattr(data, "revision") and isinstance(data.revision, str)
            else ""
        )
        if revision_text.lower() == "none":
            revision_text = ""

        # 更正、订正等修订标记直接跟在标题后，便于识别本条是否为后续修正情报。
        correct_tag = f" [{revision_text}]" if revision_text else ""

        lines = [f"🚨[{info_type}]{correct_tag} 日本气象厅"]

        shock_time = _resolve_shock_time(data)
        if shock_time:
            display_time = shock_time
            if getattr(display_time, "tzinfo", None) is None:
                display_time = TimeConverter.parse_datetime(display_time).replace(
                    tzinfo=TimeConverter._get_timezone("Asia/Tokyo")
                )
            lines.append(
                f"⏰发震时间：{TimeConverter.format_time(display_time, timezone)}"
            )

        if data.title and data.latitude is not None and data.longitude is not None:
            coords = _format_coordinates(data.latitude, data.longitude)
            lines.append(f"📍震中：{data.title} ({coords})")
        elif info_type == "震度速报":
            lines.append("📍震中：调查中")

        if data.magnitude is not None and data.magnitude != -1.0:
            lines.append(f"📊震级：M {data.magnitude:.1f}")
        elif info_type == "震度速报":
            lines.append("📊震级：调查中")

        if data.depth is not None and data.depth != -1.0:
            lines.append(f"🏔️深度：{_format_depth(data.depth)}")
        elif info_type != "震度速报":
            lines.append("🏔️深度：调查中")

        if data.scale is not None:
            scale_display = ScaleConverter.format_jma_cwa_scale_display(data.scale)
            emoji = _get_intensity_emoji(data.scale, is_eew=False, is_shindo=True)
            lines.append(f"💥最大震度：{scale_display} {emoji}")

        domestic_tsunami = data.domestic_tsunami
        if domestic_tsunami:
            # 日本情报里的海啸字段直接影响风险理解，因此一并翻译成可读文本。
            tsunami_mapping = {
                "None": "无需担心海啸",
                "Unknown": "不明",
                "Checking": "调查中",
                "NonEffective": "预计会有若干海面变动，无须担心受害",
                "Watch": "正在/已经发布津波注意报",
                "Warning": "正在/已经发布津波警报/大津波警报",
            }
            tsunami_info = tsunami_mapping.get(domestic_tsunami, domestic_tsunami)
            lines.append(f"🌊津波：{tsunami_info}")

        return "\n".join(lines)

    @classmethod
    def present(
        cls,
        display_context: EarthquakeDisplayContext,
        options: dict | None = None,
    ) -> str:
        merged_options = _resolve_options(display_context, options)
        rendered = cls.format_message(display_context, merged_options)
        if not _is_earthquake_view(display_context):
            return rendered

        lines = rendered.split("\n") if rendered else []
        jma_points = display_context.jma_points
        if (
            isinstance(jma_points, list)
            and jma_points
            and not any(
                line.startswith("📡各地震度详情：") or line.startswith("📡震度 ")
                for line in lines
            )
        ):
            scale_groups: dict[object, list[str]] = {}
            for point in jma_points:
                if not isinstance(point, dict):
                    continue
                scale = point.get("scale", 0)
                addr = str(point.get("addr", "") or "").strip()
                if not addr:
                    continue
                scale_groups.setdefault(scale, []).append(addr)

            if scale_groups:
                if merged_options.get("detailed_jma_intensity", False):
                    # 详细模式下按震度从高到低逐级展开展示。
                    sorted_scales = sorted(scale_groups.keys(), reverse=True)
                    lines.append("📡各地震度详情：")
                    for scale_key in sorted_scales:
                        scale_disp = ScaleConverter.format_jma_cwa_scale_display(
                            scale_key
                        )
                        emoji = _get_intensity_emoji(
                            scale_key, is_eew=False, is_shindo=True
                        )
                        locs = scale_groups[scale_key]
                        max_show = 20
                        loc_str = "、".join(locs[:max_show])
                        if len(locs) > max_show:
                            loc_str += f" 等{len(locs)}处"
                        lines.append(f"  {emoji}[震度{scale_disp}] {loc_str}")
                else:
                    # 简略模式仅展示最大震度对应的代表观测点，控制文本长度。
                    max_scale_key = max(scale_groups.keys())
                    scale_disp = ScaleConverter.format_jma_cwa_scale_display(
                        max_scale_key
                    )
                    emoji = _get_intensity_emoji(
                        max_scale_key, is_eew=False, is_shindo=True
                    )
                    locs = scale_groups[max_scale_key][:5]
                    suffix = "等" if len(scale_groups[max_scale_key]) > 5 else ""
                    lines.append(
                        f"📡震度 {scale_disp} {emoji} 观测点：{'、'.join(locs)}{suffix}"
                    )

        jma_comment = display_context.jma_comment
        if (
            isinstance(jma_comment, str)
            and jma_comment.strip()
            and not any(line.startswith("📝备注：") for line in lines)
        ):
            lines.append(f"📝备注：{jma_comment.strip()}")

        return "\n".join(lines)


class GlobalQuakeTextPresenter(BasePresenter):
    """Global Quake 文本展示器。"""

    presenter_name = "global_quake_text_presenter"

    @classmethod
    def format_message(
        cls, data: EarthquakeDisplayContext, options: dict | None = None
    ) -> str:
        if not _is_earthquake_view(data):
            return "🚨[地震预警] 数据类型错误"

        merged_options = dict(options or {})
        timezone = merged_options.get("timezone", "UTC+8")
        lines = ["🚨[地震预警] Global Quake"]

        report_num = _resolve_report_num(data)
        lines.append(f"📋第 {report_num} 报")

        shock_time = _resolve_shock_time(data)
        if shock_time:
            lines.append(
                f"⏰发震时间：{TimeConverter.format_time(shock_time, timezone)}"
            )

        if data.title and data.latitude is not None and data.longitude is not None:
            coords = _format_coordinates(data.latitude, data.longitude)
            lines.append(f"📍震中：{data.title} ({coords})")

        if data.magnitude is not None:
            lines.append(f"📊震级：M {data.magnitude:.1f}")

        if data.depth is not None:
            lines.append(f"🏔️深度：{_format_depth(data.depth)}")

        if data.intensity is not None:
            emoji = _get_intensity_emoji(data.intensity, is_eew=True, is_shindo=False)
            lines.append(f"💥预估最大烈度：{data.intensity} {emoji}")

        if data.max_pga is not None:
            lines.append(f"📈最大加速度：{data.max_pga:.1f} gal")

        stations = data.stations
        if isinstance(stations, dict):
            # Global Quake 常会附带触发测站统计，用于体现当前解算基础。
            total = stations.get("total", 0)
            used = stations.get("used", 0)
            lines.append(f"📡触发测站：{used}/{total}")

        return "\n".join(lines)

    @classmethod
    def present(
        cls,
        display_context: EarthquakeDisplayContext,
        options: dict | None = None,
    ) -> str:
        return cls.format_message(
            display_context, _resolve_options(display_context, options)
        )


class CwaReportPresenter(BasePresenter):
    """台湾中央气象署地震报告展示器。"""

    presenter_name = "cwa_report_presenter"

    @staticmethod
    def _format_depth(depth: float) -> str:
        if depth == 0.0:
            return "极浅"
        return f"{depth} km"

    @classmethod
    def format_message(
        cls, data: EarthquakeDisplayContext, options: dict | None = None
    ) -> str:
        if not _is_earthquake_view(data):
            return "🚨[地震报告] 数据类型错误"

        merged_options = dict(options or {})
        timezone = merged_options.get("timezone", "UTC+8")
        # 报告类消息会额外带上报告图片和等震度图地址。
        image_uri = merged_options.get("image_uri")
        shakemap_uri = merged_options.get("shakemap_uri")
        lines = ["🚨[地震报告] 台湾中央气象署"]

        shock_time = _resolve_shock_time(data)
        if shock_time:
            lines.append(
                f"⏰发震时间：{TimeConverter.format_time(shock_time, timezone)}"
            )
        if data.title and data.latitude is not None and data.longitude is not None:
            coords = _format_coordinates(data.latitude, data.longitude)
            lines.append(f"📍震中：{data.title} ({coords})")
        if data.magnitude is not None:
            lines.append(f"📊震级：M {data.magnitude:.1f}")
        if data.depth is not None:
            lines.append(f"🏔️深度：{cls._format_depth(data.depth)}")
        if isinstance(image_uri, str) and image_uri.strip():
            lines.append("🖼️报告图片：")
            lines.append(image_uri.strip())
        if isinstance(shakemap_uri, str) and shakemap_uri.strip():
            lines.append("🗺️等震度图：")
            lines.append(shakemap_uri.strip())
        return "\n".join(lines)

    @classmethod
    def present(
        cls,
        display_context: EarthquakeDisplayContext,
        options: dict | None = None,
    ) -> str:
        merged_options = _resolve_options(display_context, options)
        # 若调用方未显式覆盖图片地址，则优先使用展示上下文自带的链接。
        merged_options.setdefault("image_uri", display_context.image_uri)
        merged_options.setdefault("shakemap_uri", display_context.shakemap_uri)
        return cls.format_message(display_context, merged_options)
