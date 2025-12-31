"""
地震消息格式化器
包含 CEA, CWA, JMA, CENC, USGS, GlobalQuake 等地震数据源的格式化逻辑
"""

from datetime import datetime, timedelta, timezone

from ...core.intensity_calculator import IntensityCalculator
from ...models.models import EarthquakeData
from .base import BaseMessageFormatter


class CEAEEWFormatter(BaseMessageFormatter):
    """中国地震预警网格式化器"""

    @staticmethod
    def format_message(earthquake: EarthquakeData) -> str:
        """格式化中国地震预警网消息"""
        lines = ["🚨[地震预警] 中国地震预警网"]

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
                f"⏰发震时间：{CEAEEWFormatter.format_time(earthquake.shock_time)}"
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
            lines.append(f"🏔️深度：{earthquake.depth} km")

        # 预估最大烈度
        if earthquake.intensity is not None:
            lines.append(f"💥预估最大烈度：{earthquake.intensity}")

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
    def format_message(earthquake: EarthquakeData) -> str:
        """格式化台湾中央气象署地震预警消息"""
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
                f"⏰发震时间：{CWAEEWFormatter.format_time(earthquake.shock_time)}"
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
            lines.append(f"🏔️深度：{earthquake.depth} km")

        # 预估最大震度
        if earthquake.scale is not None:
            lines.append(f"💥预估最大震度：{earthquake.scale}")

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


class JMAEEWFormatter(BaseMessageFormatter):
    """日本气象厅紧急地震速报格式化器"""

    @staticmethod
    def format_message(earthquake: EarthquakeData) -> str:
        """格式化日本气象厅紧急地震速报消息"""
        # 检查是否取消
        if earthquake.is_cancel:
            return f"🚨[紧急地震速报] [取消] 日本气象厅\n📋第 {earthquake.updates} 报 (取消报)\n📝之前的紧急地震速报已取消"

        # 判断是予报还是警报
        warning_type = "予报"  # 默认

        # 优先使用info_type (Fan Studio)
        if earthquake.info_type:
            warning_type = earthquake.info_type
        # 回退到基于震度的推断 (P2P)
        elif earthquake.scale is not None and earthquake.scale >= 4.5:
            warning_type = "警报"

        lines = [f"🚨[紧急地震速报] [{warning_type}] 日本气象厅"]

        # 报数信息
        report_num = getattr(earthquake, "updates", 1)
        is_final = getattr(earthquake, "is_final", False)
        report_info = f"第 {report_num} 报"
        if is_final:
            report_info += "(最终报)"
        lines.append(f"📋{report_info}")

        # 时间 - 将日本时间(UTC+9)转换为北京时间(UTC+8)显示
        if earthquake.shock_time:
            # 如果时间没有时区信息，假定为JST(UTC+9)
            display_time = earthquake.shock_time
            if display_time.tzinfo is None:
                display_time = display_time.replace(tzinfo=timezone(timedelta(hours=9)))
            lines.append(
                f"⏰发震时间：{JMAEEWFormatter.format_time(display_time, 'UTC+8')}"
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
            lines.append(f"🏔️深度：{earthquake.depth} km")

        # 预估最大震度
        # Fan Studio 使用 intensity (epiIntensity)，P2P 使用 scale
        if earthquake.scale is not None:
            lines.append(f"💥预估最大震度：{earthquake.scale}")
        elif earthquake.intensity is not None:
            # Fan Studio 数据中的 epiIntensity 已经是震度字符串 (e.g. "4", "5+")
            lines.append(f"💥预估最大震度：{earthquake.intensity}")

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
    def determine_measurement_type(earthquake: EarthquakeData) -> str:
        """判断测定类型（自动/正式）"""
        # 优先使用info_type字段
        if earthquake.info_type:
            if "正式测定" in earthquake.info_type:
                return "正式测定"
            elif "自动测定" in earthquake.info_type:
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
    def format_message(earthquake: EarthquakeData) -> str:
        """格式化中国地震台网地震测定消息"""
        measurement_type = CENCEarthquakeFormatter.determine_measurement_type(
            earthquake
        )
        lines = [f"🚨[地震情报] 中国地震台网 [{measurement_type}]"]

        # 时间
        if earthquake.shock_time:
            lines.append(
                f"⏰发震时间：{CENCEarthquakeFormatter.format_time(earthquake.shock_time)}"
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
            lines.append(f"🏔️深度：{earthquake.depth} km")

        # 最大烈度
        if earthquake.intensity is not None:
            lines.append(f"💥最大烈度：{earthquake.intensity}")

        return "\n".join(lines)


class JMAEarthquakeFormatter(BaseMessageFormatter):
    """日本气象厅地震情报格式化器"""

    @staticmethod
    def determine_info_type(earthquake: EarthquakeData) -> str:
        """判断情报类型"""
        # 优先使用issue.type判断
        raw_data = getattr(earthquake, "raw_data", {})
        if isinstance(raw_data, dict):
            issue = raw_data.get("issue", {})
            issue_type = issue.get("type")

            type_mapping = {
                "ScalePrompt": "震度速报",
                "Destination": "震源相关情报",
                "ScaleAndDestination": "震度・震源相关情报",
                "DetailScale": "各地震度相关情报",
                "Foreign": "远地地震相关情报",
                "Other": "其他情报",
            }

            if issue_type in type_mapping:
                return type_mapping[issue_type]

        # 回退到基于数据内容的判断
        # 如果是未知地点，震级深度为-1.0，只有震度信息 -> 震度速报
        if (
            (earthquake.place_name == "未知地点" or not earthquake.place_name)
            and (earthquake.magnitude == -1.0 or earthquake.magnitude is None)
            and (earthquake.depth == -1.0 or earthquake.depth is None)
            and earthquake.scale is not None
        ):
            return "震度速报"

        # 如果更新了震中、震级、深度，但没有震度信息 -> 震源相关情报
        if (
            earthquake.magnitude is not None
            and earthquake.magnitude != -1.0
            and earthquake.depth is not None
            and earthquake.depth != -1.0
            and earthquake.place_name
            and earthquake.place_name != "未知地点"
            and earthquake.scale is None
        ):
            return "震源相关情报"

        # 其他情况 -> 震源・震度情报
        return "震源・震度情报"

    @staticmethod
    def format_message(earthquake: EarthquakeData, options: dict = None) -> str:
        """格式化日本气象厅地震情报消息"""
        if options is None:
            options = {}

        info_type = JMAEarthquakeFormatter.determine_info_type(earthquake)
        lines = [f"🚨[{info_type}] 日本气象厅"]

        # 时间 - 将日本时间(UTC+9)转换为北京时间(UTC+8)显示
        if earthquake.shock_time:
            # 如果时间没有时区信息，假定为JST(UTC+9)
            display_time = earthquake.shock_time
            if display_time.tzinfo is None:
                display_time = display_time.replace(tzinfo=timezone(timedelta(hours=9)))
            lines.append(
                f"⏰发震时间：{JMAEarthquakeFormatter.format_time(display_time, 'UTC+8')}"
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
            lines.append(f"🏔️深度：{earthquake.depth} km")
        elif info_type == "震度速报":
            lines.append("🏔️深度：调查中")

        # 最大震度
        if earthquake.scale is not None:
            lines.append(f"💥最大震度：{earthquake.scale}")

        # 津波信息
        if earthquake.domestic_tsunami:
            tsunami_mapping = {
                "None": "无津波风险",
                "Unknown": "不明",
                "Checking": "调查中",
                "NonEffective": "若干海面变动，无被害忧虑",
                "Watch": "津波注意报",
                "Warning": "津波警报",
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
                        locs = scale_groups[scale_key]

                        # 如果地点太多，分行显示或截断（避免消息过长）
                        # 详细模式下，我们尝试显示更多，但为了QQ消息限制，还是限制一下每级显示数量
                        # 例如每级最多显示20个
                        max_show = 20
                        locs_to_show = locs[:max_show]

                        loc_str = "、".join(locs_to_show)
                        if len(locs) > max_show:
                            loc_str += f" 等{len(locs)}处"

                        lines.append(f"  [震度{scale_disp}] {loc_str}")
                else:
                    # 默认模式：只显示最大震度区域
                    max_scale_key = max(scale_groups.keys()) if scale_groups else None
                    if max_scale_key:
                        scale_disp = get_scale_disp(max_scale_key)
                        locs = scale_groups[max_scale_key][:5]
                        lines.append(
                            f"📡震度 {scale_disp} 观测点：{'、'.join(locs)}{'等' if len(scale_groups[max_scale_key]) > 5 else ''}"
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
    def format_message(earthquake: EarthquakeData) -> str:
        """格式化USGS地震情报消息"""
        measurement_type = USGSEarthquakeFormatter.determine_measurement_type(
            earthquake
        )
        lines = [f"🚨[地震情报] 美国地质调查局(USGS) [{measurement_type}]"]

        # 时间
        if earthquake.shock_time:
            lines.append(
                f"⏰发震时间：{USGSEarthquakeFormatter.format_time(earthquake.shock_time)}"
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
            lines.append(f"🏔️深度：{earthquake.depth} km")

        return "\n".join(lines)


class GlobalQuakeFormatter(BaseMessageFormatter):
    """Global Quake地震情报格式化器"""

    @staticmethod
    def format_message(earthquake: EarthquakeData) -> str:
        """格式化Global Quake地震情报消息"""
        lines = ["🚨[地震预警] Global Quake"]

        # 报数信息
        report_num = getattr(earthquake, "updates", 1)
        lines.append(f"📋第 {report_num} 报")

        # 时间
        if earthquake.shock_time:
            lines.append(
                f"⏰发震时间：{GlobalQuakeFormatter.format_time(earthquake.shock_time)}"
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
            lines.append(f"🏔️深度：{earthquake.depth} km")

        # 预估最大烈度
        if earthquake.intensity is not None:
            lines.append(f"💥预估最大烈度：{earthquake.intensity}")

        # 最大加速度
        if earthquake.max_pga is not None:
            lines.append(f"📈最大加速度：{earthquake.max_pga:.1f} gal")

        # 测站信息
        if earthquake.stations:
            total = earthquake.stations.get("total", 0)
            used = earthquake.stations.get("used", 0)
            lines.append(f"📡触发测站：{used}/{total}")

        return "\n".join(lines)
