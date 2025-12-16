"""
专用消息格式化器
为不同数据源提供专门的消息格式化
"""

from datetime import datetime
from typing import Any

from ..models.data_source_config import get_data_source_config
from ..models.models import EarthquakeData, TsunamiData, WeatherAlarmData


class BaseMessageFormatter:
    """基础消息格式化器"""

    @staticmethod
    def format_coordinates(latitude: float, longitude: float) -> str:
        """格式化坐标显示"""
        lat_dir = "N" if latitude >= 0 else "S"
        lon_dir = "E" if longitude >= 0 else "W"
        return f"{abs(latitude):.2f}°{lat_dir}, {abs(longitude):.2f}°{lon_dir}"

    @staticmethod
    def format_time(dt: datetime, timezone: str = "UTC+8") -> str:
        """格式化时间显示"""
        if not dt:
            return "未知时间"
        return f"{dt.strftime('%Y年%m月%d日 %H时%M分%S秒')} ({timezone})"

    @staticmethod
    def get_map_link(
        latitude: float,
        longitude: float,
        provider: str = "baidu",
        zoom: int = 5,
        magnitude: float = None,
        place_name: str = None,
    ) -> str:
        """生成地图链接"""
        if latitude is None or longitude is None:
            return ""

        # 构建震中信息（简化版，减少URL长度）
        magnitude_info = f"M{magnitude}" if magnitude is not None else "地震"
        location_info = place_name if place_name else "震中位置"

        if provider == "openstreetmap":
            # OpenStreetMap 简洁格式
            return f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}&zoom={zoom}"

        elif provider == "google":
            # Google Maps 简洁格式
            return f"https://maps.google.com/maps?q={latitude},{longitude}&z={zoom}"

        elif provider == "baidu":
            # 百度地图直接使用WGS84坐标
            # 增加 coord_type=wgs84 提高精度
            # 确保 zoom 参数正确传递
            baidu_map_url = f"https://api.map.baidu.com/marker?location={latitude},{longitude}&zoom={zoom}&title={magnitude_info}+Epicenter&content={location_info[:32]}&coord_type=wgs84&output=html"
            return baidu_map_url

        elif provider == "amap":
            # 高德地图简洁格式
            # 高德Web端URI API可能不支持zoom参数，但尝试传递z参数
            return f"https://uri.amap.com/marker?position={longitude},{latitude}&name=震中位置&src=disaster_warning&coordinate=wgs84&callnative=0"

        # 默认返回百度地图
        return f"https://api.map.baidu.com/marker?location={latitude},{longitude}&zoom={zoom}&title={magnitude_info}+Epicenter&content={location_info[:32]}&coord_type=wgs84&output=html"

    @staticmethod
    def format_message(data: Any) -> str:
        """默认消息格式化"""
        lines = [f"🚨[{data.disaster_type.value}] 灾害预警 (基础格式)"]
        if hasattr(data, "id"):
            lines.append(f"📋ID: {data.id}")
        if hasattr(data, "shock_time") and data.shock_time:
            lines.append(f"⏰时间: {data.shock_time}")
        if hasattr(data, "place_name") and data.place_name:
            lines.append(f"📍地点: {data.place_name}")
        if hasattr(data, "raw_data") and data.raw_data:
            lines.append(f"📝数据: {data.raw_data}")
        return "\n".join(lines)


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
                f"⏰时间：{CEAEEWFormatter.format_time(earthquake.shock_time)}"
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
            lines.append(f"📊震级：M {earthquake.magnitude}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{earthquake.depth} km")

        # 预估最大烈度
        if earthquake.intensity is not None:
            lines.append(f"💥预估最大烈度：{earthquake.intensity}")

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
                f"⏰时间：{CWAEEWFormatter.format_time(earthquake.shock_time)}"
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
            lines.append(f"📊震级：M {earthquake.magnitude}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{earthquake.depth} km")

        # 预估最大震度
        if earthquake.scale is not None:
            lines.append(f"💥预估最大震度：{earthquake.scale}")

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
        # 震度5弱(4.5)以上为警报
        if earthquake.scale is not None and earthquake.scale >= 4.5:
            warning_type = "警报"

        lines = [f"🚨[紧急地震速报] [{warning_type}] 日本气象厅"]

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
                f"⏰时间：{JMAEEWFormatter.format_time(earthquake.shock_time, 'UTC+9')}"
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
            lines.append(f"📊震级：M {earthquake.magnitude}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{earthquake.depth} km")

        # 预估最大震度
        if earthquake.scale is not None:
            lines.append(f"💥预估最大震度：{earthquake.scale}")

        # 警报区域详情 (仅针对警报)
        raw_data = getattr(earthquake, "raw_data", {})
        if warning_type == "警报" and isinstance(raw_data, dict):
            areas = raw_data.get("areas", [])
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
                f"⏰时间：{CENCEarthquakeFormatter.format_time(earthquake.shock_time)}"
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
            lines.append(f"📊震级：M {earthquake.magnitude}")

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
    def format_message(earthquake: EarthquakeData) -> str:
        """格式化日本气象厅地震情报消息"""
        info_type = JMAEarthquakeFormatter.determine_info_type(earthquake)
        lines = [f"🚨[{info_type}] 日本气象厅"]

        # 时间
        if earthquake.shock_time:
            lines.append(
                f"⏰时间：{JMAEarthquakeFormatter.format_time(earthquake.shock_time, 'UTC+9')}"
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
            lines.append(f"📊震级：M {earthquake.magnitude}")
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

                # 显示最大震度的前几个地点
                max_scale_key = max(scale_groups.keys()) if scale_groups else None
                if max_scale_key:
                    # 转换震度显示
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
        """格式化美国地质调查局地震情报消息"""
        measurement_type = USGSEarthquakeFormatter.determine_measurement_type(
            earthquake
        )
        lines = [f"🚨[地震情报] 美国地质调查局(USGS) [{measurement_type}]"]

        # 时间
        if earthquake.shock_time:
            lines.append(
                f"⏰时间：{USGSEarthquakeFormatter.format_time(earthquake.shock_time, 'UTC+8')}"
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
            lines.append(f"📍震中：{earthquake.place_name} ({coords})")

        # 震级
        if earthquake.magnitude is not None:
            lines.append(f"📊震级：M {earthquake.magnitude}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{earthquake.depth} km")

        return "\n".join(lines)


class GlobalQuakeFormatter(BaseMessageFormatter):
    """Global Quake格式化器"""

    @staticmethod
    def format_message(earthquake: EarthquakeData) -> str:
        """格式化Global Quake消息"""
        lines = ["🚨[地震预警] Global Quake"]

        # 报数信息（如果有）
        report_num = getattr(earthquake, "updates", 1)
        report_info = f"第 {report_num} 报"
        lines.append(f"📋{report_info}")

        # 时间
        if earthquake.shock_time:
            lines.append(
                f"⏰时间：{GlobalQuakeFormatter.format_time(earthquake.shock_time)}"
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
            lines.append(f"📊震级：M {earthquake.magnitude}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{earthquake.depth} km")

        # 预估有感人数（如果有）
        raw_data = getattr(earthquake, "raw_data", {})
        if "estimated_felt" in raw_data:
            lines.append(f"👥预估有感：{raw_data['estimated_felt']} 人")
        if "estimated_strongly_felt" in raw_data:
            lines.append(f"⚡预估强有感：{raw_data['estimated_strongly_felt']} 人")

        # 预估最大烈度
        if earthquake.intensity is not None:
            lines.append(f"💥预估最大烈度：{earthquake.intensity}")

        # 触发测站数（如果有）
        if "triggered_stations" in raw_data:
            lines.append(f"📡触发测站：{raw_data['triggered_stations']} 个")

        return "\n".join(lines)


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
                timezone = "UTC+8"
            elif config and (
                "日本" in config.display_name or "日本气象厅" in config.display_name
            ):
                timezone = "UTC+9"
            else:
                timezone = "UTC+8"  # 默认使用中国时区
            lines.append(
                f"⏰发布时间：{TsunamiFormatter.format_time(tsunami.issue_time, timezone)}"
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

        # 发布时间 - 日本时区
        if tsunami.issue_time:
            lines.append(
                f"⏰発表時刻：{JMATsunamiFormatter.format_time(tsunami.issue_time, 'UTC+9')}"
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


# 格式化器映射
MESSAGE_FORMATTERS = {
    # EEW预警格式化器
    "cea_fanstudio": CEAEEWFormatter,
    "cea_wolfx": CEAEEWFormatter,
    "cwa_fanstudio": CWAEEWFormatter,
    "cwa_wolfx": CWAEEWFormatter,
    "jma_fanstudio": JMAEEWFormatter,
    "jma_p2p": JMAEEWFormatter,
    "jma_wolfx": JMAEEWFormatter,
    "global_quake": GlobalQuakeFormatter,
    # 地震情报格式化器
    "cenc_fanstudio": CENCEarthquakeFormatter,
    "cenc_wolfx": CENCEarthquakeFormatter,
    "jma_p2p_info": JMAEarthquakeFormatter,
    "jma_wolfx_info": JMAEarthquakeFormatter,
    "usgs_fanstudio": USGSEarthquakeFormatter,
    # 海啸预警格式化器
    "china_tsunami_fanstudio": TsunamiFormatter,
    "jma_tsunami_p2p": JMATsunamiFormatter,
    # 气象预警格式化器
    "china_weather_fanstudio": WeatherFormatter,
}


def get_formatter(source_id: str):
    """获取指定数据源的格式化器"""
    return MESSAGE_FORMATTERS.get(source_id, BaseMessageFormatter)


def format_earthquake_message(source_id: str, earthquake: EarthquakeData) -> str:
    """格式化地震消息"""
    formatter_class = get_formatter(source_id)
    if hasattr(formatter_class, "format_message"):
        return formatter_class.format_message(earthquake)

    # 回退到基础格式化
    return BaseMessageFormatter.format_message(earthquake)


def format_tsunami_message(source_id: str, tsunami: TsunamiData) -> str:
    """格式化海啸消息"""
    formatter_class = get_formatter(source_id)
    if hasattr(formatter_class, "format_message"):
        return formatter_class.format_message(tsunami)

    # 回退到基础格式化
    return BaseMessageFormatter.format_message(tsunami)


def format_weather_message(source_id: str, weather: WeatherAlarmData) -> str:
    """格式化气象消息"""
    formatter_class = get_formatter(source_id)
    if hasattr(formatter_class, "format_message"):
        return formatter_class.format_message(weather)

    # 回退到基础格式化
    return BaseMessageFormatter.format_message(weather)
