"""
地震消息格式化器
包含 CEA, CWA, JMA, CENC, USGS, GlobalQuake 等地震数据源的格式化逻辑
"""

import re
from datetime import datetime, timedelta, timezone

from ...core.support.intensity_calculator import IntensityCalculator
from ...models.models import DataSource, EarthquakeData
from ..time_converter import TimeConverter
from .base import BaseMessageFormatter

# 各数据源对应的默认时区（用于 naive datetime 的修复）
# key 使用 DataSource 枚举值，与 source.value 一致
_SOURCE_TIMEZONE_MAP = {
    # JMA / P2P 数据源使用 JST (UTC+9)
    DataSource.FAN_STUDIO_JMA.value: timezone(timedelta(hours=9)),
    DataSource.P2P_EEW.value: timezone(timedelta(hours=9)),
    DataSource.P2P_EARTHQUAKE.value: timezone(timedelta(hours=9)),
    DataSource.WOLFX_JMA_EEW.value: timezone(timedelta(hours=9)),
    DataSource.WOLFX_JMA_EQ.value: timezone(timedelta(hours=9)),
    # Global Quake 使用 UTC
    DataSource.GLOBAL_QUAKE.value: timezone.utc,
}
_SOURCE_TZ_CST = timezone(timedelta(hours=8))


def _fix_naive_datetime(dt: datetime, source: DataSource) -> datetime:
    """为 naive datetime 附加数据源对应的时区信息。

    各数据源的原始时间通常不带时区，但实际含义不同：
      - JMA / P2P 数据源使用 JST (UTC+9)
      - Global Quake 使用 UTC
      - 其他中国/台湾数据源使用 CST (UTC+8)
    """
    if dt is None or dt.tzinfo is not None:
        return dt

    source_val = source.value if hasattr(source, "value") else str(source)
    tz = _SOURCE_TIMEZONE_MAP.get(source_val, _SOURCE_TZ_CST)
    return dt.replace(tzinfo=tz)


def _build_base_render_context(earthquake: EarthquakeData, options: dict = None) -> dict:
    """构建基础卡片渲染上下文，各 formatter 的 get_render_context 可在此基础上扩展。

    返回的 dict 已包含所有通用字段，zoom_level / map_source / tile_url
    等页面级配置由 message_manager 在渲染前注入，无需在此处理。
    """
    options = options or {}
    timezone_str = options.get("timezone", "UTC+8")

    mag = earthquake.magnitude or 0
    if mag < 5:
        mag_class = "bg-low"
    elif mag < 7:
        mag_class = "bg-med"
    else:
        mag_class = "bg-high"

    shock_time = _fix_naive_datetime(earthquake.shock_time, earthquake.source)
    time_str = (
        BaseMessageFormatter.format_time(shock_time, timezone_str)
        if shock_time
        else "Unknown Time"
    )

    local_est = _extract_local_estimation(earthquake)
    footer_items = []
    if local_est:
        footer_items.append(
            {
                "label": f"{local_est['place_name']}预估",
                "value": f"距离震中 {local_est['distance']:.1f} km，预估最大烈度 {local_est['intensity']:.1f} ({local_est['description']})",
            }
        )

    return {
        "magnitude": f"{mag:.1f}",
        "mag_class": mag_class,
        "region": earthquake.place_name or "未知地点",
        "time_str": time_str,
        "depth": _format_depth(earthquake.depth)
        if earthquake.depth is not None
        else "N/A",
        "latitude": f"{earthquake.latitude:.4f}" if earthquake.latitude is not None else "0.0000",
        "longitude": f"{earthquake.longitude:.4f}" if earthquake.longitude is not None else "0.0000",
        "epicenter_str": BaseMessageFormatter.format_coordinates(
            earthquake.latitude, earthquake.longitude
        )
        if earthquake.latitude is not None and earthquake.longitude is not None
        else "N/A",
        "is_update": (getattr(earthquake, "updates", 1) > 1),
        "revision": getattr(earthquake, "updates", 1),
        "event_id": earthquake.event_id or earthquake.id or "N/A",
        "intensity": "",
        "intensity_label": "烈度",
        "source_name": "",
        "footer_items": footer_items,
        "local_estimation": local_est,
    }


def _extract_local_estimation(earthquake: EarthquakeData) -> dict | None:
    """从 raw_data 中提取本地烈度预估信息。"""
    if not (hasattr(earthquake, "raw_data") and isinstance(earthquake.raw_data, dict)):
        return None
    local_est = earthquake.raw_data.get("local_estimation")
    if not local_est:
        return None
    return {
        "distance": local_est.get("distance", 0.0),
        "intensity": local_est.get("intensity", 0.0),
        "place_name": local_est.get("place_name", "本地"),
        "description": IntensityCalculator.get_intensity_description(
            local_est.get("intensity", 0.0)
        ),
    }


def _format_depth(depth: float) -> str:
    """
    格式化深度显示

    Args:
        depth: 震源深度(km)

    Returns:
        格式化后的深度字符串
    """
    if depth == 0.0:
        return "极浅"
    return f"{depth} km"


# 预编译正则表达式
_INTENSITY_NUM_PATTERN = re.compile(r"(\d+(\.\d+)?)")


def _get_intensity_emoji(value, is_eew=True, is_shindo=False) -> str:
    """
    获取烈度/震度对应的emoji

    Args:
        value: 烈度/震度值 (int, float, str)
        is_eew: 是否为预警 (True=圆形, False=方形)
        is_shindo: 是否为震度 (True=震度, False=烈度)
    """
    if value is None:
        return ""

    circles = ["⚪", "🔵", "🟢", "🟡", "🟠", "🔴", "🟣"]
    squares = ["⬜", "🟦", "🟩", "🟨", "🟧", "🟥", "🟪"]
    emojis = circles if is_eew else squares

    idx = 0
    try:
        val_str = str(value)
        num_val = None

        # 尝试提取数值 (支持 4.5, 5, "5.5" 等)
        # 使用预编译的正则提取第一个数字部分
        match = _INTENSITY_NUM_PATTERN.search(val_str)
        if match:
            num_val = float(match.group(1))

        if is_shindo:
            # === 震度逻辑 (JMA/CWA) ===
            # 1: 白 (idx 0)
            # 2: 蓝 (idx 1)
            # 3: 绿 (idx 2)
            # 4: 黄 (idx 3)
            # 5弱, 5强 (5-, 5+, 4.5-5.4): 橙 (idx 4)
            # 6弱, 6强 (6-, 6+, 5.5-6.4): 红 (idx 5)
            # 7 (>=6.5): 紫 (idx 6)
            # ===========================
            # 1. 优先处理数值（防止 "3.5" 被识别为 "5" 或 "3"）
            if num_val is not None:
                if num_val >= 9:
                    # JMA 内部数值 (10=1, ..., 45=5-, 50=5+, 55=6-, 60=6+, 70=7)
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
                    # 普通数值 / CWA Wolfx处理后的数值 (4.5=5弱, 5.0=5强, 5.5=6弱...)
                    if num_val < 1.5:
                        idx = 0
                    elif num_val < 2.5:
                        idx = 1
                    elif num_val < 3.5:
                        idx = 2
                    elif num_val < 4.5:
                        idx = 3
                    elif num_val < 5.5:
                        idx = 4  # 4.5(5弱), 5.0(5强) -> 橙色
                    elif num_val < 6.5:
                        idx = 5  # 5.5(6弱), 6.0(6强) -> 红色
                    else:
                        idx = 6  # >= 6.5 -> 紫色
            # 2. 字符串匹配（后备）
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
            elif "1" in val_str:
                idx = 0
            else:
                idx = 0

        else:
            # === 烈度逻辑 (CSIS/MMI) ===
            # 1-2: 白 (idx 0)
            # 3-4: 蓝 (idx 1)
            # 5: 绿 (idx 2)
            # 6: 黄 (idx 3)
            # 7-8: 橙 (idx 4)
            # 9-10: 红 (idx 5)
            # 11-12: 紫 (idx 6)

            if num_val is not None:
                if num_val < 2.5:
                    idx = 0  # 1-2 (实际上通常没有小数，为了稳健使用范围)
                elif num_val < 4.5:
                    idx = 1  # 3-4
                elif num_val < 5.5:
                    idx = 2  # 5
                elif num_val < 6.5:
                    idx = 3  # 6
                elif num_val < 8.5:
                    idx = 4  # 7-8
                elif num_val < 10.5:
                    idx = 5  # 9-10
                else:
                    idx = 6  # 11-12
            else:
                idx = 0

    except Exception:
        return ""

    return emojis[idx]


class CEAEEWFormatter(BaseMessageFormatter):
    """中国地震预警网格式化器"""

    @staticmethod
    def get_render_context(earthquake: EarthquakeData, options: dict = None) -> dict:
        ctx = _build_base_render_context(earthquake, options)
        source_name = "中国地震预警网"
        if earthquake.province:
            source_name = f"{earthquake.province}地震局"
        ctx["source_name"] = source_name

        if earthquake.intensity is not None:
            ctx["intensity"] = str(earthquake.intensity)
            ctx["intensity_label"] = "烈度"

        footer_items = ctx["footer_items"]
        report_num = getattr(earthquake, "updates", 1)
        is_final = getattr(earthquake, "is_final", False)
        report_info = f"第 {report_num} 报"
        if is_final:
            report_info += "(最终报)"
        footer_items.append({"label": "报数", "value": report_info})

        if earthquake.province:
            footer_items.append({"label": "影响区域", "value": earthquake.province})

        if earthquake.max_pga is not None:
            footer_items.append({"label": "最大加速度 (PGA)", "value": f"{earthquake.max_pga:.1f} gal"})

        ctx["footer_items"] = footer_items
        return ctx

    @staticmethod
    def format_message(earthquake: EarthquakeData, options: dict = None) -> str:
        """格式化中国地震预警网消息"""
        options = options or {}
        timezone = options.get("timezone", "UTC+8")

        # 检查是否有 province 字段来判断是否为省级预警
        source_name = "中国地震预警网"
        if earthquake.province:
            source_name = f"{earthquake.province}地震局"

        lines = [f"🚨[地震预警] {source_name}"]

        # 报数信息
        report_num = getattr(earthquake, "updates", 1)
        is_final = getattr(earthquake, "is_final", False)
        report_info = f"第 {report_num} 报"
        if is_final:
            report_info += "(最终报)"
        lines.append(f"📋{report_info}")

        # 时间
        if earthquake.shock_time:
            lines.append(
                f"⏰发震时间：{CEAEEWFormatter.format_time(earthquake.shock_time, timezone)}"
            )

        # 震中
        if (
            earthquake.place_name
            and earthquake.latitude is not None
            and earthquake.longitude is not None
        ):
            coords = CEAEEWFormatter.format_coordinates(
                earthquake.latitude, earthquake.longitude
            )
            lines.append(f"📍震中：{earthquake.place_name} ({coords})")

        # 震级
        if earthquake.magnitude is not None:
            lines.append(f"📊震级：M {earthquake.magnitude:.1f}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{_format_depth(earthquake.depth)}")

        # 预估最大烈度
        if earthquake.intensity is not None:
            emoji = _get_intensity_emoji(
                earthquake.intensity, is_eew=True, is_shindo=False
            )
            lines.append(f"💥预估最大烈度：{earthquake.intensity} {emoji}")

        # 本地烈度预估
        if hasattr(earthquake, "raw_data") and isinstance(earthquake.raw_data, dict):
            local_est = earthquake.raw_data.get("local_estimation")
            if local_est:
                dist = local_est.get("distance", 0.0)
                inte = local_est.get("intensity", 0.0)
                place = local_est.get("place_name", "本地")
                desc = IntensityCalculator.get_intensity_description(inte)

                lines.append("")
                lines.append(f"📍{place}预估：")
                lines.append(
                    f"距离震中 {dist:.1f} km，预估最大烈度 {inte:.1f} ({desc})"
                )

        return "\n".join(lines)


class CWAEEWFormatter(BaseMessageFormatter):
    """台湾中央气象署地震预警格式化器"""

    @staticmethod
    def get_render_context(earthquake: EarthquakeData, options: dict = None) -> dict:
        ctx = _build_base_render_context(earthquake, options)
        ctx["source_name"] = "台湾中央气象署"

        if earthquake.scale is not None:
            ctx["intensity"] = str(earthquake.scale)
            ctx["intensity_label"] = "震度"

        footer_items = ctx["footer_items"]
        report_num = getattr(earthquake, "updates", 1)
        is_final = getattr(earthquake, "is_final", False)
        report_info = f"第 {report_num} 报"
        if is_final:
            report_info += "(最终报)"
        footer_items.append({"label": "报数", "value": report_info})

        impact_area = None
        if isinstance(getattr(earthquake, "raw_data", None), dict):
            impact_area = earthquake.raw_data.get("wolfx_impact_area")
        if not impact_area:
            impact_area = earthquake.province
        if impact_area:
            footer_items.append({"label": "影响区域", "value": str(impact_area)})

        ctx["footer_items"] = footer_items
        return ctx

    @staticmethod
    def format_message(earthquake: EarthquakeData, options: dict = None) -> str:
        """格式化台湾中央气象署地震预警消息"""
        options = options or {}
        timezone = options.get("timezone", "UTC+8")

        lines = ["🚨[地震预警] 台湾中央气象署"]

        # 报数信息
        report_num = getattr(earthquake, "updates", 1)
        is_final = getattr(earthquake, "is_final", False)
        report_info = f"第 {report_num} 报"
        if is_final:
            report_info += "(最终报)"
        lines.append(f"📋{report_info}")

        # 时间
        if earthquake.shock_time:
            lines.append(
                f"⏰发震时间：{CWAEEWFormatter.format_time(earthquake.shock_time, timezone)}"
            )

        # 震中
        if (
            earthquake.place_name
            and earthquake.latitude is not None
            and earthquake.longitude is not None
        ):
            coords = CWAEEWFormatter.format_coordinates(
                earthquake.latitude, earthquake.longitude
            )
            lines.append(f"📍震中：{earthquake.place_name} ({coords})")

        # 震级
        if earthquake.magnitude is not None:
            lines.append(f"📊震级：M {earthquake.magnitude:.1f}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{_format_depth(earthquake.depth)}")

        # 预估最大震度
        if earthquake.scale is not None:
            emoji = _get_intensity_emoji(earthquake.scale, is_eew=True, is_shindo=True)
            scale_line = f"💥预估最大震度：{earthquake.scale} {emoji}"

            # CWA 融合策略：尝试将 Wolfx 影响区域追加到预估震度后
            wolfx_impact_area = None
            if isinstance(getattr(earthquake, "raw_data", None), dict):
                wolfx_impact_area = earthquake.raw_data.get("wolfx_impact_area")

            if isinstance(wolfx_impact_area, str) and wolfx_impact_area.strip():
                scale_line += f"（影响区域：{wolfx_impact_area.strip()}）"

            lines.append(scale_line)

        # 影响区域 (locationDesc)
        if earthquake.province:
            lines.append(f"⚠️影响区域：{earthquake.province}")

        # 本地烈度预估
        if hasattr(earthquake, "raw_data") and isinstance(earthquake.raw_data, dict):
            local_est = earthquake.raw_data.get("local_estimation")
            if local_est:
                dist = local_est.get("distance", 0.0)
                inte = local_est.get("intensity", 0.0)
                place = local_est.get("place_name", "本地")
                desc = IntensityCalculator.get_intensity_description(inte)

                lines.append("")
                lines.append(f"📍{place}预估：")
                lines.append(
                    f"距离震中 {dist:.1f} km，预估最大烈度 {inte:.1f} ({desc})"
                )

        return "\n".join(lines)


class CWAReportFormatter(BaseMessageFormatter):
    """台湾中央气象署地震报告格式化器"""

    @staticmethod
    def get_render_context(earthquake: EarthquakeData, options: dict = None) -> dict:
        ctx = _build_base_render_context(earthquake, options)
        ctx["source_name"] = "台湾中央气象署 (报告)"

        footer_items = ctx["footer_items"]
        if earthquake.image_uri:
            footer_items.append({"label": "报告图片", "value": earthquake.image_uri})
        if earthquake.shakemap_uri:
            footer_items.append({"label": "等震度图", "value": earthquake.shakemap_uri})

        ctx["footer_items"] = footer_items
        return ctx

    @staticmethod
    def format_message(earthquake: EarthquakeData, options: dict = None) -> str:
        """格式化台湾中央气象署地震报告消息"""
        options = options or {}
        timezone = options.get("timezone", "UTC+8")

        lines = ["🚨[地震报告] 台湾中央气象署"]

        # 时间
        if earthquake.shock_time:
            lines.append(
                f"⏰发震时间：{CWAReportFormatter.format_time(earthquake.shock_time, timezone)}"
            )

        # 震中
        if (
            earthquake.place_name
            and earthquake.latitude is not None
            and earthquake.longitude is not None
        ):
            coords = CWAReportFormatter.format_coordinates(
                earthquake.latitude, earthquake.longitude
            )
            lines.append(f"📍震中：{earthquake.place_name} ({coords})")

        # 震级
        if earthquake.magnitude is not None:
            lines.append(f"📊震级：M {earthquake.magnitude:.1f}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{_format_depth(earthquake.depth)}")

        # 图片链接 (如果有)
        if earthquake.image_uri:
            lines.append(f"🖼️报告图片：{earthquake.image_uri}")

        if earthquake.shakemap_uri:
            lines.append(f"🗺️等震度图：{earthquake.shakemap_uri}")

        return "\n".join(lines)


class JMAEEWFormatter(BaseMessageFormatter):
    """日本气象厅紧急地震速报格式化器"""

    @staticmethod
    def get_render_context(earthquake: EarthquakeData, options: dict = None) -> dict:
        ctx = _build_base_render_context(earthquake, options)

        # 源名称：追加训练/PLUM标识
        header_tags = []
        if getattr(earthquake, "is_training", False):
            header_tags.append("训练")
        if getattr(earthquake, "is_assumption", False):
            header_tags.append("PLUM法假定震源")
        tag_str = f" [{'/'.join(header_tags)}]" if header_tags else ""
        ctx["source_name"] = f"日本气象厅 (紧急地震速报){tag_str}"

        if earthquake.intensity is not None:
            ctx["intensity"] = str(earthquake.intensity)
        elif earthquake.scale is not None:
            ctx["intensity"] = str(earthquake.scale)
        ctx["intensity_label"] = "震度"

        footer_items = ctx["footer_items"]
        report_num = getattr(earthquake, "updates", 1)
        is_final = getattr(earthquake, "is_final", False)
        report_info = f"第 {report_num} 报"
        if is_final:
            report_info += "(最终报)"
        footer_items.append({"label": "报数", "value": report_info})

        if earthquake.is_cancel:
            footer_items.append({"label": "状态", "value": "已取消"})
        else:
            warning_type = earthquake.info_type or ""
            if not warning_type:
                warning_type = "警报" if (earthquake.scale is not None and earthquake.scale >= 4.5) else "予报"
            footer_items.append({"label": "种类", "value": warning_type})

        if earthquake.domestic_tsunami:
            tsunami_mapping = {
                "None": "无需担心海啸",
                "Unknown": "不明",
                "Checking": "调查中",
                "NonEffective": "预计若干海面变动",
                "Watch": "津波注意报发布中",
                "Warning": "津波警报/大津波警报发布中",
            }
            footer_items.append({"label": "津波", "value": tsunami_mapping.get(earthquake.domestic_tsunami, earthquake.domestic_tsunami)})

        # 警报区域
        raw_data = getattr(earthquake, "raw_data", {})
        if isinstance(raw_data, dict):
            warn_area_wolfx = raw_data.get("WarnArea", {})
            if isinstance(warn_area_wolfx, dict) and warn_area_wolfx.get("Chiiki"):
                area_text = warn_area_wolfx.get("Chiiki")
                shindo1 = warn_area_wolfx.get("Shindo1")
                shindo2 = warn_area_wolfx.get("Shindo2")
                if shindo1:
                    shindo_range = f"{shindo1}"
                    if shindo2 and shindo2 != shindo1:
                        shindo_range += f"～{shindo2}"
                    area_text += f" (震度{shindo_range})"
                footer_items.append({"label": "警报区域", "value": area_text})
            else:
                areas = raw_data.get("areas", [])
                warn_areas = []
                for area in areas:
                    if area.get("scaleFrom", 0) >= 45:
                        name = area.get("name", "")
                        kind = area.get("kindCode", "")
                        status = "已到达" if kind == "11" else "未到达"
                        warn_areas.append(f"{name}({status})")
                if warn_areas:
                    footer_items.append(
                        {"label": "警报区域", "value": "、".join(warn_areas[:6]) + ("等" if len(warn_areas) > 6 else "")}
                    )

        ctx["footer_items"] = footer_items
        return ctx

    @staticmethod
    def format_message(earthquake: EarthquakeData, options: dict = None) -> str:
        """格式化日本气象厅紧急地震速报消息"""
        options = options or {}
        timezone = options.get("timezone", "UTC+8")

        # 检查是否取消
        if earthquake.is_cancel:
            return f"🚨[紧急地震速报] [取消] 日本气象厅\n📋第 {earthquake.updates} 报 (取消报)\n📝之前的紧急地震速报已取消"

        # 判断是予报还是警报
        warning_type = "予报"  # 默认

        # 优先使用info_type (Fan Studio / Wolfx)
        if earthquake.info_type:
            warning_type = earthquake.info_type
        # 回退到基于震度的推断 (P2P)
        elif earthquake.scale is not None and earthquake.scale >= 4.5:
            warning_type = "警报"

        # 处理特殊标识：PLUM/训练
        header_tags = []
        if getattr(earthquake, "is_training", False):
            header_tags.append("训练")
        if getattr(earthquake, "is_assumption", False):
            header_tags.append("PLUM法所得假定震源")

        tag_str = f" [{'/'.join(header_tags)}]" if header_tags else ""
        lines = [f"🚨[紧急地震速报] [{warning_type}]{tag_str} 日本气象厅"]

        # 报数信息
        report_num = getattr(earthquake, "updates", 1)
        is_final = getattr(earthquake, "is_final", False)
        report_info = f"第 {report_num} 报"
        if is_final:
            report_info += "(最终报)"
        lines.append(f"📋{report_info}")

        # 时间
        if earthquake.shock_time:
            # 日本气象厅原始时间通常是 UTC+9
            # 如果是 naive datetime，我们在这里显式视为 JST
            display_time = earthquake.shock_time
            if display_time.tzinfo is None:
                # 假设 input 为 JST (UTC+9)
                display_time = TimeConverter.parse_datetime(display_time).replace(
                    tzinfo=TimeConverter._get_timezone("Asia/Tokyo")
                )

            lines.append(
                f"⏰发震时间：{JMAEEWFormatter.format_time(display_time, timezone)}"
            )

        # 震中
        if (
            earthquake.place_name
            and earthquake.latitude is not None
            and earthquake.longitude is not None
        ):
            coords = JMAEEWFormatter.format_coordinates(
                earthquake.latitude, earthquake.longitude
            )
            lines.append(f"📍震中：{earthquake.place_name} ({coords})")

        # 震级
        if earthquake.magnitude is not None:
            lines.append(f"📊震级：M {earthquake.magnitude:.1f}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{_format_depth(earthquake.depth)}")

        # 预估最大震度
        # Fan Studio 使用 intensity (epiIntensity)，P2P 使用 scale
        if earthquake.scale is not None:
            emoji = _get_intensity_emoji(earthquake.scale, is_eew=True, is_shindo=True)
            lines.append(f"💥预估最大震度：{earthquake.scale} {emoji}")
        elif earthquake.intensity is not None:
            # Fan Studio 数据中的 epiIntensity 已经是震度字符串 (e.g. "4", "5+")
            emoji = _get_intensity_emoji(
                earthquake.intensity, is_eew=True, is_shindo=True
            )
            lines.append(f"💥预估最大震度：{earthquake.intensity} {emoji}")

        # 警报区域详情 (仅针对警报且有区域数据)
        raw_data = getattr(earthquake, "raw_data", {})
        if warning_type == "警报" and isinstance(raw_data, dict):
            areas = raw_data.get("areas", [])
            if areas:
                warn_areas = []
                for area in areas:
                    # kindCode: 10=未到达, 11=已到达
                    # scaleFrom >= 45 (震度5弱)
                    if area.get("scaleFrom", 0) >= 45:
                        name = area.get("name", "")
                        kind = area.get("kindCode", "")
                        status = "已到达" if kind == "11" else "未到达"
                        warn_areas.append(f"{name}({status})")

                if warn_areas:
                    lines.append("⚠️警报区域：")
                    # 每行显示3个区域
                    chunk_size = 3
                    for i in range(0, len(warn_areas), chunk_size):
                        lines.append("  " + "、".join(warn_areas[i : i + chunk_size]))

            # Wolfx 特有的警报区域处理
            warn_area_wolfx = raw_data.get("WarnArea", {})
            if isinstance(warn_area_wolfx, dict) and warn_area_wolfx.get("Chiiki"):
                lines.append(f"⚠️警报区域：{warn_area_wolfx.get('Chiiki')}")
                # 显示预估震度范围
                shindo1 = warn_area_wolfx.get("Shindo1")
                shindo2 = warn_area_wolfx.get("Shindo2")
                if shindo1:
                    shindo_range = f"{shindo1}"
                    if shindo2 and shindo2 != shindo1:
                        shindo_range += f" ～ {shindo2}"
                    lines.append(f"💥预估震度范围：{shindo_range}")

        # 本地烈度预估
        if hasattr(earthquake, "raw_data") and isinstance(earthquake.raw_data, dict):
            local_est = earthquake.raw_data.get("local_estimation")
            if local_est:
                dist = local_est.get("distance", 0.0)
                inte = local_est.get("intensity", 0.0)
                place = local_est.get("place_name", "本地")
                desc = IntensityCalculator.get_intensity_description(inte)

                lines.append("")
                lines.append(f"📍{place}预估：")
                lines.append(
                    f"距离震中 {dist:.1f} km，预估最大烈度 {inte:.1f} ({desc})"
                )

        return "\n".join(lines)


class CENCEarthquakeFormatter(BaseMessageFormatter):
    """中国地震台网地震测定格式化器"""

    @staticmethod
    def get_render_context(earthquake: EarthquakeData, options: dict = None) -> dict:
        ctx = _build_base_render_context(earthquake, options)
        measurement_type = CENCEarthquakeFormatter.determine_measurement_type(earthquake)
        ctx["source_name"] = f"中国地震台网 [{measurement_type}]"

        if earthquake.intensity is not None:
            ctx["intensity"] = str(earthquake.intensity)
            ctx["intensity_label"] = "烈度"

        footer_items = ctx["footer_items"]
        if earthquake.info_type:
            footer_items.append({"label": "测定类型", "value": earthquake.info_type})
        ctx["footer_items"] = footer_items
        return ctx

    @staticmethod
    def determine_measurement_type(earthquake: EarthquakeData) -> str:
        """判断测定类型（自动/正式）"""
        # 优先使用info_type字段
        if earthquake.info_type:
            info_type_lower = str(earthquake.info_type).lower()
            if "正式测定" in info_type_lower or "reviewed" in info_type_lower:
                return "正式测定"
            elif "自动测定" in info_type_lower or "automatic" in info_type_lower:
                return "自动测定"

        # 基于时间判断
        if earthquake.shock_time:
            time_diff = (datetime.now() - earthquake.shock_time).total_seconds() / 60
            if time_diff > 10:
                return "正式测定"
            else:
                return "自动测定"

        return "自动测定"

    @staticmethod
    def format_message(earthquake: EarthquakeData, options: dict = None) -> str:
        """格式化中国地震台网地震测定消息"""
        options = options or {}
        timezone = options.get("timezone", "UTC+8")

        measurement_type = CENCEarthquakeFormatter.determine_measurement_type(
            earthquake
        )
        lines = [f"🚨[地震情报] 中国地震台网 [{measurement_type}]"]

        # 时间
        if earthquake.shock_time:
            lines.append(
                f"⏰发震时间：{CENCEarthquakeFormatter.format_time(earthquake.shock_time, timezone)}"
            )

        # 震中
        if (
            earthquake.place_name
            and earthquake.latitude is not None
            and earthquake.longitude is not None
        ):
            coords = CENCEarthquakeFormatter.format_coordinates(
                earthquake.latitude, earthquake.longitude
            )
            lines.append(f"📍震中：{earthquake.place_name} ({coords})")

        # 震级
        if earthquake.magnitude is not None:
            lines.append(f"📊震级：M {earthquake.magnitude:.1f}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{_format_depth(earthquake.depth)}")

        # 最大烈度
        if earthquake.intensity is not None:
            emoji = _get_intensity_emoji(
                earthquake.intensity, is_eew=False, is_shindo=False
            )
            lines.append(f"💥最大烈度：{earthquake.intensity} {emoji}")

        return "\n".join(lines)


class JMAEarthquakeFormatter(BaseMessageFormatter):
    """日本气象厅地震情报格式化器"""

    @staticmethod
    def get_render_context(earthquake: EarthquakeData, options: dict = None) -> dict:
        ctx = _build_base_render_context(earthquake, options)
        info_type = JMAEarthquakeFormatter.determine_info_type(earthquake)
        ctx["source_name"] = f"日本气象厅 ({info_type})"

        if earthquake.scale is not None:
            ctx["intensity"] = str(earthquake.scale)
            ctx["intensity_label"] = "震度"

        footer_items = ctx["footer_items"]
        correct_tag = ""
        if hasattr(earthquake, "revision") and earthquake.revision and isinstance(earthquake.revision, str):
            correct_tag = f" [{earthquake.revision}]"
        if correct_tag:
            footer_items.append({"label": "订正", "value": correct_tag.strip(" []")})

        if earthquake.domestic_tsunami:
            tsunami_mapping = {
                "None": "无需担心海啸",
                "Unknown": "不明",
                "Checking": "调查中",
                "NonEffective": "预计若干海面变动",
                "Watch": "津波注意报发布中",
                "Warning": "津波警报/大津波警报发布中",
            }
            footer_items.append({"label": "津波", "value": tsunami_mapping.get(earthquake.domestic_tsunami, earthquake.domestic_tsunami)})

        # 震度观测点 (最大震度区域摘要)
        raw_data = getattr(earthquake, "raw_data", {})
        if isinstance(raw_data, dict):
            points = raw_data.get("points", [])
            if points:
                scale_groups = {}
                for point in points:
                    scale = point.get("scale", 0)
                    addr = point.get("addr", "")
                    if scale not in scale_groups:
                        scale_groups[scale] = []
                    scale_groups[scale].append(addr)

                if scale_groups:
                    max_scale_key = max(scale_groups.keys())
                    scale_disp = str(max_scale_key / 10).replace(".0", "")
                    if max_scale_key == 45:
                        scale_disp = "5弱"
                    elif max_scale_key == 50:
                        scale_disp = "5强"
                    elif max_scale_key == 55:
                        scale_disp = "6弱"
                    elif max_scale_key == 60:
                        scale_disp = "6强"
                    locs = scale_groups[max_scale_key][:5]
                    points_text = f"震度{scale_disp}: {'、'.join(locs)}{'等' if len(scale_groups[max_scale_key]) > 5 else ''}"
                    footer_items.append({"label": "观测点", "value": points_text})

            comments = raw_data.get("comments", {})
            free_form = comments.get("freeFormComment", "")
            if free_form:
                footer_items.append({"label": "备注", "value": free_form})

        ctx["footer_items"] = footer_items
        return ctx

    @staticmethod
    def determine_info_type(earthquake: EarthquakeData) -> str:
        """判断情报类型"""
        info_type = earthquake.info_type or ""

        # P2P 数据源的英文类型映射
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

        # 如果 info_type 已经是中文描述（来自 Wolfx 或已填充的描述），直接返回
        if info_type and any("\u4e00" <= char <= "\u9fff" for char in info_type):
            return info_type

        # 兜底：基于数据内容的判断（例如当 info_type 为空时）
        if (earthquake.place_name == "未知地点" or not earthquake.place_name) and (
            earthquake.magnitude is None or earthquake.magnitude == -1.0
        ):
            return "震度速报"

        if earthquake.scale is None:
            return "震源相关情报"

        return "震源・震度情报"

    @staticmethod
    def format_message(earthquake: EarthquakeData, options: dict = None) -> str:
        """格式化日本气象厅地震情报消息"""
        options = options or {}
        timezone = options.get("timezone", "UTC+8")

        info_type = JMAEarthquakeFormatter.determine_info_type(earthquake)

        # 处理订正信息
        correct_tag = ""
        if (
            hasattr(earthquake, "revision")
            and earthquake.revision
            and isinstance(earthquake.revision, str)
        ):
            correct_tag = f" [{earthquake.revision}]"

        lines = [f"🚨[{info_type}]{correct_tag} 日本气象厅"]

        # 时间
        if earthquake.shock_time:
            # 如果时间没有时区信息，假定为JST(UTC+9)
            display_time = earthquake.shock_time
            if display_time.tzinfo is None:
                display_time = TimeConverter.parse_datetime(display_time).replace(
                    tzinfo=TimeConverter._get_timezone("Asia/Tokyo")
                )

            lines.append(
                f"⏰发震时间：{JMAEarthquakeFormatter.format_time(display_time, timezone)}"
            )

        # 震中
        if (
            earthquake.place_name
            and earthquake.latitude is not None
            and earthquake.longitude is not None
        ):
            coords = JMAEarthquakeFormatter.format_coordinates(
                earthquake.latitude, earthquake.longitude
            )
            lines.append(f"📍震中：{earthquake.place_name} ({coords})")
        elif info_type == "震度速报":
            lines.append("📍震中：调查中")

        # 震级
        if earthquake.magnitude is not None and earthquake.magnitude != -1.0:
            lines.append(f"📊震级：M {earthquake.magnitude:.1f}")
        elif info_type == "震度速报":
            lines.append("📊震级：调查中")

        # 深度
        if earthquake.depth is not None and earthquake.depth != -1.0:
            lines.append(f"🏔️深度：{_format_depth(earthquake.depth)}")
        elif info_type == "震度速报":
            lines.append("🏔️深度：调查中")

        # 最大震度
        if earthquake.scale is not None:
            emoji = _get_intensity_emoji(earthquake.scale, is_eew=False, is_shindo=True)
            lines.append(f"💥最大震度：{earthquake.scale} {emoji}")

        # 津波信息
        if earthquake.domestic_tsunami:
            tsunami_mapping = {
                "None": "无需担心海啸",
                "Unknown": "不明",
                "Checking": "调查中",
                "NonEffective": "预计会有若干海面变动，无须担心受害",
                "Watch": "正在/已经发布津波注意报",
                "Warning": "正在/已经发布津波警报/大津波警报",
            }
            tsunami_info = tsunami_mapping.get(
                earthquake.domestic_tsunami, earthquake.domestic_tsunami
            )
            lines.append(f"🌊津波：{tsunami_info}")

        # 区域震度（如果有）
        raw_data = getattr(earthquake, "raw_data", {})
        if isinstance(raw_data, dict):
            # 震度观测点 (points)
            points = raw_data.get("points", [])
            if points:
                # 按震度分组
                scale_groups = {}
                for point in points:
                    scale = point.get("scale", 0)
                    addr = point.get("addr", "")
                    if scale not in scale_groups:
                        scale_groups[scale] = []
                    scale_groups[scale].append(addr)

                # 震度显示辅助函数
                def get_scale_disp(scale_val):
                    disp = str(scale_val / 10).replace(".0", "")
                    if scale_val == 45:
                        return "5弱"
                    elif scale_val == 50:
                        return "5强"
                    elif scale_val == 55:
                        return "6弱"
                    elif scale_val == 60:
                        return "6强"
                    return disp

                if options.get("detailed_jma_intensity", False):
                    # 详细模式：显示所有震度级别（从大到小）
                    sorted_scales = sorted(scale_groups.keys(), reverse=True)
                    lines.append("📡各地震度详情：")

                    for scale_key in sorted_scales:
                        scale_disp = get_scale_disp(scale_key)
                        emoji = _get_intensity_emoji(
                            scale_key, is_eew=False, is_shindo=True
                        )
                        locs = scale_groups[scale_key]

                        # 如果地点太多，分行显示或截断（避免消息过长）
                        # 详细模式下，我们尝试显示更多，但为了QQ消息限制，还是限制一下每级显示数量
                        # 例如每级最多显示20个
                        max_show = 20
                        locs_to_show = locs[:max_show]

                        loc_str = "、".join(locs_to_show)
                        if len(locs) > max_show:
                            loc_str += f" 等{len(locs)}处"

                        lines.append(f"  {emoji}[震度{scale_disp}] {loc_str}")
                else:
                    # 默认模式：只显示最大震度区域
                    max_scale_key = max(scale_groups.keys()) if scale_groups else None
                    if max_scale_key:
                        scale_disp = get_scale_disp(max_scale_key)
                        emoji = _get_intensity_emoji(
                            max_scale_key, is_eew=False, is_shindo=True
                        )
                        locs = scale_groups[max_scale_key][:5]
                        lines.append(
                            f"📡震度 {scale_disp} {emoji} 观测点：{'、'.join(locs)}{'等' if len(scale_groups[max_scale_key]) > 5 else ''}"
                        )

            # 备注信息 (comments)
            comments = raw_data.get("comments", {})
            free_form = comments.get("freeFormComment", "")
            if free_form:
                lines.append(f"📝备注：{free_form}")

        return "\n".join(lines)


class USGSEarthquakeFormatter(BaseMessageFormatter):
    """美国地质调查局地震情报格式化器"""

    @staticmethod
    def get_render_context(earthquake: EarthquakeData, options: dict = None) -> dict:
        ctx = _build_base_render_context(earthquake, options)
        measurement_type = USGSEarthquakeFormatter.determine_measurement_type(earthquake)
        ctx["source_name"] = f"USGS [{measurement_type}]"

        footer_items = ctx["footer_items"]
        if earthquake.info_type:
            footer_items.append({"label": "测定类型", "value": earthquake.info_type})
        ctx["footer_items"] = footer_items
        return ctx

    @staticmethod
    def determine_measurement_type(earthquake: EarthquakeData) -> str:
        """判断测定类型（自动/正式）"""
        # 优先使用info_type字段
        if earthquake.info_type:
            info_type_lower = earthquake.info_type.lower()
            if info_type_lower == "reviewed":
                return "正式测定"
            elif info_type_lower == "automatic":
                return "自动测定"

        # 基于时间判断
        if earthquake.shock_time:
            time_diff = (datetime.now() - earthquake.shock_time).total_seconds() / 60
            if time_diff > 10:
                return "正式测定"
            else:
                return "自动测定"

        return "自动测定"

    @staticmethod
    def format_message(earthquake: EarthquakeData, options: dict = None) -> str:
        """格式化USGS地震情报消息"""
        options = options or {}
        timezone = options.get("timezone", "UTC+8")

        measurement_type = USGSEarthquakeFormatter.determine_measurement_type(
            earthquake
        )
        lines = [f"🚨[地震情报] 美国地质调查局(USGS) [{measurement_type}]"]

        # 时间
        if earthquake.shock_time:
            lines.append(
                f"⏰发震时间：{USGSEarthquakeFormatter.format_time(earthquake.shock_time, timezone)}"
            )

        # 震中
        if (
            earthquake.place_name
            and earthquake.latitude is not None
            and earthquake.longitude is not None
        ):
            coords = USGSEarthquakeFormatter.format_coordinates(
                earthquake.latitude, earthquake.longitude
            )
            # USGS地名已在handler中翻译成中文
            lines.append(f"📍震中：{earthquake.place_name} ({coords})")

        # 震级
        if earthquake.magnitude is not None:
            lines.append(f"📊震级：M {earthquake.magnitude:.1f}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{_format_depth(earthquake.depth)}")

        return "\n".join(lines)


class GlobalQuakeFormatter(BaseMessageFormatter):
    """Global Quake地震情报格式化器"""

    @staticmethod
    def get_render_context(earthquake: EarthquakeData, options: dict = None) -> dict:
        options = options or {}
        ctx = _build_base_render_context(earthquake, options)
        ctx["source_name"] = "Global Quake"

        if earthquake.intensity is not None:
            ctx["intensity"] = str(earthquake.intensity)
            ctx["intensity_label"] = "烈度"

        footer_items = ctx["footer_items"]

        if earthquake.max_pga is not None:
            footer_items.append(
                {"label": "最大加速度 (PGA)", "value": f"{earthquake.max_pga:.1f} gal"}
            )

        stations_used = 0
        stations_total = 0
        if earthquake.stations:
            stations_used = earthquake.stations.get("used", 0)
            stations_total = earthquake.stations.get("total", 0)
        footer_items.append(
            {"label": "触发测站 (Used/Total)", "value": f"{stations_used} / {stations_total}"}
        )

        quality_pct = "N/A"
        location_error = "N/A"

        if earthquake.raw_data:
            data_inner = earthquake.raw_data.get("data", {})

            quality = data_inner.get("quality", {})
            if isinstance(quality, dict):
                pct = quality.get("pct")
                if pct is not None:
                    quality_pct = f"{pct}%"

                err_origin = quality.get("errOrigin") or quality.get("err_origin")
                if err_origin is not None:
                    location_error = f"{err_origin:.1f} km"

            elif isinstance(data_inner.get("locationError"), (int, float)):
                location_error = f"{data_inner.get('locationError'):.1f} km"

        footer_items.append({"label": "定位误差 (Loc Err)", "value": location_error})
        footer_items.append({"label": "数据拟合 (Quality)", "value": quality_pct})

        ctx["footer_items"] = footer_items
        return ctx

    @staticmethod
    def format_message(earthquake: EarthquakeData, options: dict = None) -> str:
        """格式化Global Quake地震情报消息"""
        options = options or {}
        timezone = options.get("timezone", "UTC+8")

        lines = ["🚨[地震预警] Global Quake"]

        # 报数信息
        report_num = getattr(earthquake, "updates", 1)
        lines.append(f"📋第 {report_num} 报")

        # 时间
        if earthquake.shock_time:
            lines.append(
                f"⏰发震时间：{GlobalQuakeFormatter.format_time(earthquake.shock_time, timezone)}"
            )

        # 震中
        if (
            earthquake.place_name
            and earthquake.latitude is not None
            and earthquake.longitude is not None
        ):
            coords = GlobalQuakeFormatter.format_coordinates(
                earthquake.latitude, earthquake.longitude
            )
            lines.append(f"📍震中：{earthquake.place_name} ({coords})")

        # 震级
        if earthquake.magnitude is not None:
            lines.append(f"📊震级：M {earthquake.magnitude:.1f}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{_format_depth(earthquake.depth)}")

        # 预估最大烈度
        if earthquake.intensity is not None:
            emoji = _get_intensity_emoji(
                earthquake.intensity, is_eew=True, is_shindo=False
            )
            lines.append(f"💥预估最大烈度：{earthquake.intensity} {emoji}")

        # 最大加速度
        if earthquake.max_pga is not None:
            lines.append(f"📈最大加速度：{earthquake.max_pga:.1f} gal")

        # 测站信息
        if earthquake.stations:
            total = earthquake.stations.get("total", 0)
            used = earthquake.stations.get("used", 0)
            lines.append(f"📡触发测站：{used}/{total}")

        return "\n".join(lines)
