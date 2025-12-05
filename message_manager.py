"""
消息推送管理器
"""

import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain

from .event_deduplicator import EventDeduplicator
from .models import (
    DataSource,
    DisasterEvent,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)


class MessagePushManager:
    """消息推送管理器"""

    def __init__(self, config: dict[str, Any], context):
        self.config = config
        self.context = context

        # 初始化事件去重器
        self.deduplicator = EventDeduplicator(
            time_window_minutes=1, location_tolerance_km=20.0, magnitude_tolerance=0.5
        )

        # 事件推送记录
        self.event_push_records: dict[str, list[dict]] = defaultdict(list)

        # 最终报记录
        self.final_reports: set[str] = set()

        # 推送频率控制配置
        self.push_every_n_reports = config.get("push_frequency_control", {}).get(
            "push_every_n_reports", 1
        )
        self.final_report_always_push = config.get("push_frequency_control", {}).get(
            "final_report_always_push", True
        )
        self.ignore_non_final_reports = config.get("push_frequency_control", {}).get(
            "ignore_non_final_reports", False
        )
        self.first_report_always_push = config.get("push_frequency_control", {}).get(
            "first_report_always_push", True
        )  # 新增：确保第1报总是被推送

        # 阈值配置
        self.thresholds = config.get("earthquake_thresholds", {})

        # 目标会话
        self.target_sessions = self._parse_target_sessions()

        # 地图配置
        self.include_map = config.get("message_format", {}).get("include_map", True)
        self.map_provider = config.get("message_format", {}).get(
            "map_provider", "openstreetmap"
        )
        self.map_zoom_level = config.get("message_format", {}).get("map_zoom_level", 5)

    def _parse_target_sessions(self) -> list[str]:
        """解析目标会话"""
        target_groups = self.config.get("target_groups", [])
        sessions = []

        for group_id in target_groups:
            if group_id:
                # 修复：使用正确的会话ID格式，动态获取平台名
                platform_name = self._get_platform_name_for_group(group_id)
                session = f"{platform_name}:GroupMessage:{group_id}"
                sessions.append(session)

        return sessions

    def _get_platform_name_for_group(self, group_id: str) -> str:
        """为群组获取平台名 - 从配置读取，支持历史学习"""
        # 方法1：从配置中读取用户指定的平台名
        config_platform = self.config.get("platform_name", "default")
        if config_platform and config_platform != "default":
            return config_platform

        # 方法2：从推送历史中学习（如果之前有成功推送的会话）
        for session_id in self.event_push_records.keys():
            if session_id.endswith(f":GroupMessage:{group_id}"):
                # 提取平台名（会话ID格式：platform:GroupMessage:group_id）
                parts = session_id.split(":")
                if len(parts) >= 3:
                    return parts[0]

        # 方法3：从最终报记录中提取
        for session_id in self.final_reports:
            if session_id.endswith(f":GroupMessage:{group_id}"):
                parts = session_id.split(":")
                if len(parts) >= 3:
                    return parts[0]

        # 方法4：使用配置中的默认值（首次推送时使用）
        default_platform = config_platform or "default"
        logger.debug(f"[灾害预警] 使用平台名 '{default_platform}' 用于群组 {group_id}")
        return default_platform

    def should_push_event(self, event: DisasterEvent) -> bool:
        """判断是否应该推送事件 - 详细的过滤逻辑判断"""
        event_id = self._get_event_id(event)

        # 统一的事件过滤日志记录
        filter_reasons = []

        # 🔥 修复：将时间检查放在最前面，确保不会被绕过
        # 检查事件时间是否过时（超过1小时）- 扩展到所有灾害类型
        event_time = self._get_event_time(event)
        if event_time:
            time_diff = (datetime.now() - event_time).total_seconds() / 3600  # 小时
            logger.debug(
                f"[灾害预警] 时间检查 - 事件ID: {event_id}, 事件时间: {event_time}, 当前时间: {datetime.now()}, 时间差: {time_diff:.1f}小时"
            )
            if time_diff > 1:
                logger.info(
                    f"[灾害预警] 事件 {event_id} 时间过早（{time_diff:.1f}小时前）"
                )
                return False
        else:
            logger.warning(f"[灾害预警] 事件 {event_id} 时间信息缺失，继续其他检查")

        # 检查阈值
        if not self._check_thresholds(event):
            filter_reasons.append("未通过阈值检查")

        # 检查是否是最终报
        is_final = self._is_final_report(event)
        if is_final:
            # 最终报总是推送，但需要检查时间限制
            if self.final_report_always_push:
                # 🔥 修复：最终报也需要检查时间，不能绕过时间限制
                event_time = self._get_event_time(event)
                if event_time:
                    time_diff = (datetime.now() - event_time).total_seconds() / 3600
                    if time_diff > 1:
                        logger.info(
                            f"[灾害预警] 事件 {event_id} 虽然是最终报，但时间过早（{time_diff:.1f}小时前），过滤"
                        )
                        return False
                logger.debug(f"[灾害预警] 事件 {event_id} 是最终报，允许推送")
                return True

        # ✅ 新增：检查是否是第1报，确保第1报总是被推送
        is_first_report = self._is_first_report(event)
        if is_first_report:
            if self.first_report_always_push:
                # 🔥 修复：第1报也需要检查时间，不能绕过时间限制
                event_time = self._get_event_time(event)
                if event_time:
                    time_diff = (datetime.now() - event_time).total_seconds() / 3600
                    if time_diff > 1:
                        logger.info(
                            f"[灾害预警] 事件 {event_id} 虽然是第1报，但时间过早（{time_diff:.1f}小时前），过滤"
                        )
                        return False
                logger.debug(f"[灾害预警] 事件 {event_id} 是第1报，允许推送")
                return True

        # 检查是否已经推送过最终报
        if event_id in self.final_reports:
            filter_reasons.append("最终报已推送过")

        # 检查推送频率控制
        if self.ignore_non_final_reports and not is_final:
            filter_reasons.append("非最终报被忽略")

        # 检查报数控制
        push_records = self.event_push_records.get(event_id, [])
        current_report_count = len(push_records) + 1

        # ✅ 优化：第1报已经在上面处理过了，这里只处理后续报数控制
        if current_report_count == 1:
            # 第1报已经在上面处理过了，这里不再重复判断
            if not self.first_report_always_push:
                # 如果第1报不强制推送，则检查报数控制
                if current_report_count % self.push_every_n_reports != 0:
                    filter_reasons.append(f"报数控制(第{current_report_count}报)")
        elif current_report_count % self.push_every_n_reports != 0:
            filter_reasons.append(f"报数控制(第{current_report_count}报)")

        # 如果有过滤原因，记录并返回False
        if filter_reasons:
            filter_reason = ", ".join(filter_reasons)
            logger.info(
                f"[灾害预警] 事件 {event_id} 未通过推送条件检查 - 原因: {filter_reason}"
            )
            return False

        logger.debug(f"[灾害预警] 事件 {event_id} 通过所有推送条件检查")
        return True

    def _get_event_time(self, event: DisasterEvent) -> datetime | None:
        """获取灾害事件的时间 - 支持所有灾害类型"""
        if isinstance(event.data, EarthquakeData):
            return event.data.shock_time
        elif isinstance(event.data, TsunamiData):
            return event.data.issue_time
        elif isinstance(event.data, WeatherAlarmData):
            # 气象预警优先使用生效时间，其次使用发布时间
            return event.data.effective_time or event.data.issue_time
        return None

    def _get_event_id(self, event: DisasterEvent) -> str:
        """获取事件ID"""
        if isinstance(event.data, EarthquakeData):
            return event.data.event_id or event.data.id
        elif isinstance(event.data, (TsunamiData, WeatherAlarmData)):
            return event.data.id
        return event.id

    def _is_first_report(self, event: DisasterEvent) -> bool:
        """判断是否为第1报 - 基于API文档的精确实现"""
        if isinstance(event.data, EarthquakeData):
            earthquake = event.data

            # 基于不同数据源的报数字段判断第1报
            if earthquake.source == DataSource.P2P_EARTHQUAKE:
                # P2P地震情報: 基于issue.serial字段判断第1报
                issue_info = earthquake.raw_data.get("issue", {})
                serial = issue_info.get("serial")
                if serial:
                    return serial == "1"
                # 备用：基于updates字段（如果存在）
                return (
                    earthquake.updates == 1 if hasattr(earthquake, "updates") else True
                )

            elif earthquake.source == DataSource.P2P_EEW:
                # P2P緊急地震速報: 基于issue.serial字段
                # 从API文档看，serial=1表示第1报
                issue_info = earthquake.raw_data.get("issue", {})
                return issue_info.get("serial") == "1" if issue_info else True

            elif earthquake.source in [
                DataSource.FAN_STUDIO_CEA,
                DataSource.FAN_STUDIO_CWA,
            ]:
                # 中国地震预警网/台湾中央气象署: 基于updates字段
                # API文档明确说明：updates=1表示第1报
                return earthquake.updates == 1

            elif earthquake.source in [
                DataSource.WOLFX_JMA_EEW,
                DataSource.WOLFX_CENC_EEW,
                DataSource.WOLFX_CWA_EEW,
            ]:
                # Wolfx EEW: 基于Serial或ReportNum字段
                # JMA: Serial字段，CENC: ReportNum字段
                if earthquake.source == DataSource.WOLFX_JMA_EEW:
                    return earthquake.raw_data.get("Serial") == 1
                else:
                    return earthquake.raw_data.get("ReportNum") == 1

            elif earthquake.source == DataSource.FAN_STUDIO_CENC:
                # 中国地震台网: 正式测定，通常只有1报，无更新机制
                # 基于infoTypeName字段判断
                info_type = earthquake.info_type or ""
                return "[正式测定]" in info_type or "[自动测定]" in info_type

            elif earthquake.source == DataSource.FAN_STUDIO_USGS:
                # USGS: 基于reviewed/automatic状态
                # 首次发布通常是automatic，后续可能是reviewed
                info_type = earthquake.info_type or ""
                return info_type.lower() == "automatic"

            else:
                # 默认：基于updates字段，updates=1或没有updates字段认为是第1报
                return earthquake.updates == 1 or not hasattr(earthquake, "updates")

        return False

    def _is_final_report(self, event: DisasterEvent) -> bool:
        """判断是否为最终报 - 基于API文档的增强实现"""
        if isinstance(event.data, EarthquakeData):
            earthquake = event.data

            # 方法1：直接检查is_final字段（最可靠，适用于支持的数据源）
            if earthquake.is_final:
                return True

            # 方法2：基于不同数据源的特性判断最终报

            # P2P地震情報: 基于issue.serial字段和消息特征
            if earthquake.source == DataSource.P2P_EARTHQUAKE:
                issue_info = earthquake.raw_data.get("issue", {})
                serial = issue_info.get("serial")
                if serial:
                    # 通常serial会递增，可以结合其他特征判断
                    # 例如：如果震度信息完整且serial较大，可能是最终报
                    return (
                        int(serial) >= 5
                        and earthquake.scale is not None
                        and earthquake.raw_data.get("earthquake", {}).get(
                            "maxScale", -1
                        )
                        != -1
                    )

            # P2P緊急地震速報: 基于issue.serial和isFinal字段
            elif earthquake.source == DataSource.P2P_EEW:
                issue_info = earthquake.raw_data.get("issue", {})
                serial = issue_info.get("serial")
                # 结合serial和是否有完整的震度信息
                if serial and int(serial) >= 3:
                    areas = earthquake.raw_data.get("areas", [])
                    if areas and all(
                        area.get("scaleTo") is not None for area in areas[:3]
                    ):
                        return True

            # 中国地震预警网/台湾中央气象署: 基于updates字段
            elif earthquake.source in [
                DataSource.FAN_STUDIO_CEA,
                DataSource.FAN_STUDIO_CWA,
            ]:
                # updates字段表示更新次数，但需要结合时间窗口判断
                # 如果updates较大且长时间无更新，可以认为是最终报
                if earthquake.updates >= 5:  # 至少5次更新后才考虑是最终报
                    # 这里可以添加时间窗口判断逻辑
                    return True

            # Wolfx EEW: 基于isFinal字段或Serial/ReportNum字段
            elif earthquake.source in [
                DataSource.WOLFX_JMA_EEW,
                DataSource.WOLFX_CENC_EEW,
                DataSource.WOLFX_CWA_EEW,
            ]:
                # 优先使用isFinal字段
                if earthquake.raw_data.get("isFinal") is True:
                    return True
                # 备用：基于Serial/ReportNum判断
                if earthquake.source == DataSource.WOLFX_JMA_EEW:
                    serial = earthquake.raw_data.get("Serial")
                    return serial is not None and serial >= 3
                else:
                    report_num = earthquake.raw_data.get("ReportNum")
                    return report_num is not None and report_num >= 3

            # 中国地震台网: 正式测定通常就是最终报
            elif earthquake.source == DataSource.FAN_STUDIO_CENC:
                info_type = earthquake.info_type or ""
                return "[正式测定]" in info_type

            # USGS: reviewed状态表示人工复核，通常是最终报
            elif earthquake.source == DataSource.FAN_STUDIO_USGS:
                info_type = earthquake.info_type or ""
                return info_type.lower() == "reviewed"

            # 方法3：基于时间窗口的启发式判断（备用方案）
            # 如果事件已经持续一段时间（如30分钟）且没有更新，可以认为是最终报
            # 这里可以实现更复杂的逻辑，基于事件时间和当前时间的差值

        return False

    def _check_thresholds(self, event: DisasterEvent) -> bool:
        """检查阈值"""
        if not isinstance(event.data, EarthquakeData):
            logger.debug(f"[灾害预警] 事件 {event.id} 不是地震事件，跳过阈值检查")
            return True  # 非地震事件不检查

        earthquake = event.data

        logger.debug(
            f"[灾害预警] 检查地震事件阈值 - 震级: {earthquake.magnitude}, 烈度: {earthquake.intensity}, 震度: {earthquake.scale}"
        )
        logger.debug(
            f"[灾害预警] 配置阈值 - 最小震级: {self.thresholds.get('min_magnitude')}, 最小烈度: {self.thresholds.get('min_intensity')}, 最小震度: {self.thresholds.get('min_scale')}"
        )

        # 检查震级
        min_magnitude = self.thresholds.get("min_magnitude", 0)
        if earthquake.magnitude is not None and earthquake.magnitude < min_magnitude:
            logger.debug(
                f"[灾害预警] 震级 {earthquake.magnitude} < 最小震级 {min_magnitude}"
            )
            return False

        # 检查烈度
        min_intensity = self.thresholds.get("min_intensity")
        if (
            min_intensity is not None
            and earthquake.intensity is not None
            and earthquake.intensity < min_intensity
        ):
            logger.debug(
                f"[灾害预警] 烈度 {earthquake.intensity} < 最小烈度 {min_intensity}"
            )
            return False

        # 检查震度
        min_scale = self.thresholds.get("min_scale")
        if min_scale is not None and earthquake.scale is not None:
            try:
                # 确保scale是数值类型
                scale_value = float(earthquake.scale)
                if scale_value < min_scale:
                    logger.debug(
                        f"[灾害预警] 震度 {scale_value} < 最小震度 {min_scale}"
                    )
                    return False
            except (ValueError, TypeError):
                logger.debug(f"[灾害预警] 震度值无法转换为数值: {earthquake.scale}")
                # 如果无法转换，跳过震度检查
                pass

        logger.debug(f"[灾害预警] 事件 {event.id} 通过所有阈值检查")
        return True

    async def push_event(self, event: DisasterEvent) -> bool:
        """推送事件"""
        logger.debug(f"[灾害预警] 处理事件推送: {event.id}")

        # 先去重检查 - 只推送首次接收的事件
        if not self.deduplicator.should_push_event(event):
            logger.debug(f"[灾害预警] 事件 {event.id} 被去重器过滤")
            return False

        if not self.should_push_event(event):
            # 详细过滤原因已经在should_push_event中记录，这里只记录简单信息
            logger.debug(f"[灾害预警] 事件 {event.id} 未通过推送条件检查")
            return False

        # 记录事件（用于后续去重）
        self.deduplicator.record_event(event)

        try:
            # 构建消息
            message = self._build_message(event)
            logger.debug(f"[灾害预警] 消息构建完成: {message}")

            # 获取目标会话
            target_sessions = self.target_sessions or self._get_all_sessions()
            logger.debug(f"[灾害预警] 目标会话: {target_sessions}")

            if not target_sessions:
                logger.warning("[灾害预警] 没有配置目标会话，无法推送消息")
                return False

            # 推送消息
            push_success_count = 0
            for session in target_sessions:
                try:
                    await self._send_message(session, message)
                    logger.info(f"[灾害预警] 消息已推送到 {session}")
                    push_success_count += 1
                except Exception as e:
                    logger.error(f"[灾害预警] 推送到 {session} 失败: {e}")

            # 记录推送
            self._record_push(event)
            logger.info(
                f"[灾害预警] 事件 {event.id} 推送完成，成功推送到 {push_success_count} 个会话"
            )
            return push_success_count > 0

        except Exception as e:
            logger.error(f"[灾害预警] 推送事件失败: {e}")
            return False

    def _build_message(self, event: DisasterEvent) -> MessageChain:
        """构建消息 - 统一使用专门格式化器，移除通用模板系统"""
        # 所有事件类型都使用专门的格式化器，确保功能完整性和一致性
        if isinstance(event.data, WeatherAlarmData):
            # 气象预警使用专门的格式化器
            message_text = MessageFormatter.format_weather_message(event.data)
        elif isinstance(event.data, TsunamiData):
            # 海啸预警使用专门的格式化器
            message_text = MessageFormatter.format_tsunami_message(event.data)
        elif isinstance(event.data, EarthquakeData):
            # 地震事件使用专门的格式化器 - 包含完整的数据源识别和智能信息类型
            message_text = MessageFormatter.format_earthquake_message(event.data)
        else:
            # 未知事件类型，使用基础格式化
            logger.warning(
                f"[灾害预警] 未知事件类型: {type(event.data)}，使用基础格式化"
            )
            message_text = f"🚨【未知事件】\n📋事件ID：{event.id}\n⏰时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # 构建消息链
        chain = [Comp.Plain(message_text)]

        # 添加地图链接（仅地震事件且包含经纬度）
        if self.include_map and isinstance(event.data, EarthquakeData):
            if event.data.latitude is not None and event.data.longitude is not None:
                map_url = self._generate_map_url(event.data)
                if map_url:
                    # 关键修复：绕过AstrBot的strip()问题
                    # 1. 使用独立的Plain组件，确保换行符不被strip()
                    # 2. 在URL前添加特殊字符，避免被strip()影响
                    # 3. 使用消息平台能识别的换行方式

                    # 关键修复：使用AstrBot官方推荐的零宽空格解决方案
                    # 在消息前后添加零宽空格 \u200b 以绕过 strip() 问题
                    # 参考：https://docs.astrbot.app/dev/star/guides/send-message#消息的发送

                    # 关键修复：零宽空格破坏URL完整性问题解决
                    # 1. 换行组件使用零宽空格（保护换行）
                    # 2. URL组件移除零宽空格（避免干扰URL识别）
                    # 3. 对URL进行URL编码，确保特殊字符正确处理

                    zero_width_space = "\u200b"

                    # 换行组件：使用零宽空格保护换行
                    chain.append(
                        Comp.Plain(f"{zero_width_space}\n🗺️地图:{zero_width_space}")
                    )  # 受保护的换行组件

                    # URL组件：移除零宽空格，避免干扰URL识别
                    # 对URL进行URL编码，确保空格和特殊字符正确处理
                    encoded_map_url = urllib.parse.quote(map_url, safe=":/?&=+")
                    chain.append(Comp.Plain(f" {encoded_map_url}"))  # 干净的URL组件

        return MessageChain(chain)

    def _get_source_display_name(self, source) -> str:
        """获取数据源的显示名称"""
        source_names = {
            "fan_studio_usgs": "USGS 地震情报",
            "fan_studio_cenc": "中国地震台网",
            "fan_studio_cea": "中国地震预警网",
            "fan_studio_cwa": "台湾中央气象署",
            "fan_studio_weather": "气象预警",
            "fan_studio_tsunami": "海啸预警",
            "wolfx_jma_eew": "日本气象厅",
            "wolfx_cenc_eew": "中国地震台网预警",
            "wolfx_cwa_eew": "台湾地震预警",
            "p2p_earthquake": "P2P地震情报",
            "p2p_eew": "P2P紧急地震速报",
            "global_quake": "Global Quake",
        }
        return (
            source_names.get(source.value, "灾害预警")
            if hasattr(source, "value")
            else "灾害预警"
        )

    def _generate_map_url(self, earthquake: EarthquakeData) -> str | None:
        """生成地图链接 - 优化URL长度和可识别性"""
        if earthquake.latitude is None or earthquake.longitude is None:
            return None

        lat = earthquake.latitude
        lon = earthquake.longitude
        zoom = self.map_zoom_level

        # 构建震中信息（简化版，减少URL长度）
        magnitude_info = f"M{earthquake.magnitude}" if earthquake.magnitude else "地震"
        location_info = earthquake.place_name if earthquake.place_name else "震中位置"

        if self.map_provider == "openstreetmap":
            # OpenStreetMap 简洁格式
            return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom={zoom}"

        elif self.map_provider == "google":
            # Google Maps 简洁格式
            return f"https://maps.google.com/maps?q={lat},{lon}&z={zoom}"

        elif self.map_provider == "baidu":
            # 百度地图坐标需要转换（WGS84->BD09）
            bd_lat, bd_lon = self._wgs84_to_bd09(lat, lon)

            # 简化：使用最基础的百度地图marker API
            baidu_map_url = f"https://api.map.baidu.com/marker?location={bd_lat},{bd_lon}&zoom={zoom}&title={magnitude_info}+Epicenter&content={location_info[:32]}&output=html"
            logger.info("[灾害预警] 已生成百度地图链接")
            return baidu_map_url

        elif self.map_provider == "amap":
            # 高德地图简洁格式
            return f"https://uri.amap.com/marker?position={lon},{lat}&zoom={zoom}"

    def _wgs84_to_bd09(self, lat: float, lon: float) -> tuple:
        """WGS84坐标转百度坐标（简化版）"""
        # 这里使用简化的坐标转换，实际应用中可能需要更精确的算法
        # 对于灾害预警，近似坐标已经足够
        return lat, lon

    def _get_all_sessions(self) -> list[str]:
        """获取所有会话"""
        # 这里需要实现获取所有活跃会话的逻辑
        # 暂时返回空列表，让插件主类来处理
        return []

    async def _send_message(self, session: str, message: MessageChain):
        """发送消息到指定会话"""
        await self.context.send_message(session, message)

    def _record_push(self, event: DisasterEvent):
        """记录推送"""
        event_id = self._get_event_id(event)

        # 记录推送信息
        push_info = {
            "timestamp": datetime.now(),
            "event_id": event_id,
            "disaster_type": event.disaster_type.value,
            "is_final": self._is_final_report(event),
        }

        self.event_push_records[event_id].append(push_info)

        # 如果是最终报，标记为已推送最终报
        if self._is_final_report(event):
            self.final_reports.add(event_id)

    def get_push_stats(self) -> dict[str, Any]:
        """获取推送统计"""
        total_events = len(self.event_push_records)
        total_pushes = sum(len(records) for records in self.event_push_records.values())
        final_reports_pushed = len(self.final_reports)

        return {
            "total_events": total_events,
            "total_pushes": total_pushes,
            "final_reports_pushed": final_reports_pushed,
            "recent_events": self._get_recent_events(),
        }

    def _get_recent_events(self, hours: int = 24) -> list[dict]:
        """获取最近的事件"""
        recent_time = datetime.now() - timedelta(hours=hours)
        recent_events = []

        for event_id, records in self.event_push_records.items():
            recent_records = [
                record for record in records if record["timestamp"] > recent_time
            ]

            if recent_records:
                recent_events.append(
                    {
                        "event_id": event_id,
                        "push_count": len(recent_records),
                        "last_push": max(
                            record["timestamp"] for record in recent_records
                        ),
                    }
                )

        return sorted(recent_events, key=lambda x: x["last_push"], reverse=True)

    def cleanup_old_records(self, days: int = 7):
        """清理旧记录"""
        cutoff_time = datetime.now() - timedelta(days=days)

        # 清理事件推送记录
        for event_id in list(self.event_push_records.keys()):
            records = self.event_push_records[event_id]
            recent_records = [
                record for record in records if record["timestamp"] > cutoff_time
            ]

            if recent_records:
                self.event_push_records[event_id] = recent_records
            else:
                del self.event_push_records[event_id]

        # 清理最终报记录
        self.final_reports.clear()

        logger.info(f"[灾害预警] 已清理 {days} 天前的推送记录")


class MessageFormatter:
    """消息格式化器"""

    @staticmethod
    def format_earthquake_message(earthquake: EarthquakeData) -> str:
        """格式化地震消息 - 增强版本，包含完整信息和数据源"""
        # 基于数据源构建智能标题 - 修复数据源信息显示
        source_name = MessageFormatter._get_source_display_name(earthquake.source)
        lines = [f"🚨【{source_name}】"]

        # 震中 - 修复字段命名，使用"震中"而非"地点"
        if earthquake.place_name:
            lines.append(f"📍震中：{earthquake.place_name}")

        # 时间 - 添加时区信息，基于数据源智能识别
        if earthquake.shock_time:
            timezone = MessageFormatter._get_source_timezone(earthquake.source)
            lines.append(
                f"⏰时间：{earthquake.shock_time.strftime('%Y-%m-%d %H:%M:%S')} ({timezone})"
            )

        # 震级
        if earthquake.magnitude is not None:
            lines.append(f"📊震级：M {earthquake.magnitude}")

        # 深度
        if earthquake.depth is not None:
            lines.append(f"🏔️深度：{earthquake.depth} km")

        # 烈度/震度 - 智能显示，确保不缺失
        if earthquake.intensity is not None:
            lines.append(f"💥烈度：{earthquake.intensity}")
        elif earthquake.scale is not None:
            lines.append(f"💥震度：{earthquake.scale}")
        else:
            # 都没有时显示"无"
            lines.append("💥烈度：无")

        # 更新信息 - 确保显示报数
        if earthquake.updates > 0:
            lines.append(f"🔄报数：第 {earthquake.updates} 报")
        else:
            lines.append("🔄报数：第 1 报")

        # 最终报标识 - 智能显示，只对有最终报机制的数据源显示
        if MessageFormatter._has_final_report_support(earthquake.source):
            if earthquake.is_final:
                lines.append("🔚最终报：是")
            else:
                lines.append("🔚最终报：否")

        # 信息类型 - 基于API文档实现专业测定类型识别
        if earthquake.info_type:
            # 基于数据源和info_type字段，提供专业的测定类型显示
            if earthquake.source == DataSource.FAN_STUDIO_CENC:
                # CENC: 基于infoTypeName字段
                if "[正式测定]" in earthquake.info_type:
                    info_type = "中国地震台网 [正式测定]"
                elif "[自动测定]" in earthquake.info_type:
                    info_type = "中国地震台网 [自动测定]"
                else:
                    info_type = f"中国地震台网 {earthquake.info_type}"

            elif earthquake.source == DataSource.FAN_STUDIO_USGS:
                # USGS: 基于infoTypeName字段
                if earthquake.info_type.lower() == "automatic":
                    info_type = "USGS地震情报 [自动测定]"
                elif earthquake.info_type.lower() == "reviewed":
                    info_type = "USGS地震情报 [人工复核]"
                else:
                    info_type = f"USGS地震情报 {earthquake.info_type}"

            elif earthquake.source == DataSource.FAN_STUDIO_CEA:
                # CEA: 中国地震预警网，基于实际数据特征
                info_type = "中国地震预警网"

            elif earthquake.source == DataSource.FAN_STUDIO_CWA:
                # CWA: 台湾中央气象署，基于实际数据特征
                info_type = "台湾中央气象署"

            elif earthquake.source in [
                DataSource.WOLFX_CENC_EEW,
                DataSource.WOLFX_JMA_EEW,
                DataSource.WOLFX_CWA_EEW,
            ]:
                # Wolfx EEW: 基于type字段
                raw_type = earthquake.raw_data.get("type", "")
                if raw_type == "automatic":
                    if earthquake.source == DataSource.WOLFX_CENC_EEW:
                        info_type = "中国地震台网预警 [自动测定]"
                    elif earthquake.source == DataSource.WOLFX_JMA_EEW:
                        info_type = "日本气象厅预警 [自动测定]"
                    else:
                        info_type = "台湾地震预警 [自动测定]"
                elif raw_type == "reviewed":
                    if earthquake.source == DataSource.WOLFX_CENC_EEW:
                        info_type = "中国地震台网预警 [正式测定]"
                    elif earthquake.source == DataSource.WOLFX_JMA_EEW:
                        info_type = "日本气象厅预警 [正式测定]"
                    else:
                        info_type = "台湾地震预警 [正式测定]"
                else:
                    # 基于数据源的专业显示
                    if earthquake.source == DataSource.WOLFX_CENC_EEW:
                        info_type = "中国地震台网预警"
                    elif earthquake.source == DataSource.WOLFX_JMA_EEW:
                        info_type = "日本气象厅预警"
                    else:
                        info_type = "台湾地震预警"

            elif earthquake.source == DataSource.P2P_EARTHQUAKE:
                # P2P地震情報: 基于issue.type字段
                issue_type = earthquake.raw_data.get("issue", {}).get("type", "")
                if issue_type == "DetailScale":
                    info_type = "日本气象厅 [詳細震度]"
                elif issue_type == "ScalePrompt":
                    info_type = "日本气象厅 [震度速报]"
                elif issue_type == "Destination":
                    info_type = "日本气象厅 [震源情報]"
                else:
                    info_type = f"日本气象厅 [{issue_type}]"

            elif earthquake.source == DataSource.P2P_EEW:
                # P2P緊急地震速報: 固定类型
                info_type = "日本气象厅 [緊急地震速報]"

            else:
                info_type = f"地震情報 {earthquake.info_type}"
        else:
            # 基于API文档和现有代码实现，提供准确的默认类型
            if earthquake.source == DataSource.FAN_STUDIO_CENC:
                # CENC: 根据is_final判断正式/自动测定 (API文档第220行)
                info_type = (
                    "中国地震台网 [正式测定]"
                    if earthquake.is_final
                    else "中国地震台网 [自动测定]"
                )

            elif earthquake.source == DataSource.FAN_STUDIO_USGS:
                # USGS: 基于is_final的智能判断
                info_type = (
                    "USGS地震情报 [人工复核]"
                    if earthquake.is_final
                    else "USGS地震情报 [自动测定]"
                )

            elif earthquake.source == DataSource.FAN_STUDIO_CEA:
                # CEA: 中国地震预警网，API文档中无特定类型标识
                info_type = "中国地震预警网"

            elif earthquake.source == DataSource.FAN_STUDIO_CWA:
                # CWA: 台湾中央气象署，API文档中无特定类型标识
                info_type = "台湾中央气象署"

            elif earthquake.source == DataSource.P2P_EARTHQUAKE:
                # P2P地震情報: 基于API文档，默认显示
                info_type = "日本气象厅 [地震情報]"

            elif earthquake.source == DataSource.P2P_EEW:
                # P2P緊急地震速報: 基于API文档
                info_type = "日本气象厅 [緊急地震速報]"

            elif earthquake.source in [
                DataSource.WOLFX_JMA_EEW,
                DataSource.WOLFX_CENC_EEW,
                DataSource.WOLFX_CWA_EEW,
            ]:
                # Wolfx EEW: 紧急地震速报
                info_type = "緊急地震速報"

            else:
                info_type = "地震情報"

        lines.append(f"📋信息类型：{info_type}")

        return "\n".join(lines)

    @staticmethod
    def _get_source_timezone(source) -> str:
        """获取数据源的时区信息 - 基于API文档分析"""
        # 基于三份API文档的时区分析
        timezone_mapping = {
            # P2P地震情報 - UTC+9 (日本标准时间)
            "p2p_earthquake": "UTC+9",
            "p2p_eew": "UTC+9",
            # 日本气象厅 - UTC+9
            "wolfx_jma_eew": "UTC+9",
            # 中国数据源 - UTC+8 (北京时间)
            "fan_studio_cenc": "UTC+8",
            "fan_studio_cea": "UTC+8",
            "fan_studio_cwa": "UTC+8",
            "fan_studio_weather": "UTC+8",
            "fan_studio_tsunami": "UTC+8",
            "wolfx_cenc_eew": "UTC+8",
            "wolfx_cwa_eew": "UTC+8",
            # USGS - UTC+8 (文档明确说明)
            "fan_studio_usgs": "UTC+8",
            # 其他国际数据源 - 默认为UTC+8
            "global_quake": "UTC+8",
        }

        if hasattr(source, "value"):
            return timezone_mapping.get(source.value, "UTC+8")
        return "UTC+8"

    @staticmethod
    def _get_source_display_name(source) -> str:
        """获取数据源的显示名称 - 复用主类中的逻辑"""
        source_names = {
            "fan_studio_usgs": "USGS 地震情报",
            "fan_studio_cenc": "中国地震台网",
            "fan_studio_cea": "中国地震预警网",
            "fan_studio_cwa": "台湾中央气象署",
            "fan_studio_weather": "气象预警",
            "fan_studio_tsunami": "海啸预警",
            "wolfx_jma_eew": "日本气象厅",
            "wolfx_cenc_eew": "中国地震台网预警",
            "wolfx_cwa_eew": "台湾地震预警",
            "p2p_earthquake": "P2P地震情报",
            "p2p_eew": "P2P紧急地震速报",
            "global_quake": "Global Quake",
        }
        return (
            source_names.get(source.value, "地震情报")
            if hasattr(source, "value")
            else "地震情报"
        )

    @staticmethod
    def _has_final_report_support(source) -> bool:
        """判断数据源是否支持最终报状态"""
        # 基于API文档分析，只有以下数据源支持最终报机制
        final_report_supported_sources = {
            DataSource.FAN_STUDIO_CEA,  # 中国地震预警网 - 有updates字段
            DataSource.FAN_STUDIO_CWA,  # 台湾中央气象署 - 有updates字段
            DataSource.P2P_EARTHQUAKE,  # P2P地震情報 - 有完整的报数更新机制
            DataSource.P2P_EEW,  # P2P紧急地震速报 - 有报数机制
            DataSource.WOLFX_JMA_EEW,  # Wolfx JMA - 有isFinal字段
            DataSource.WOLFX_CENC_EEW,  # Wolfx CENC - 有ReportNum字段
            DataSource.WOLFX_CWA_EEW,  # Wolfx CWA - 有ReportNum字段
        }

        # 不支持最终报的数据源（单次测定，无更新机制）
        # FAN_STUDIO_CENC - 正式测定，无更新
        # FAN_STUDIO_USGS - 单次测定
        # FAN_STUDIO_EMSC - 单次测定
        # 其他非地震数据源

        return source in final_report_supported_sources

    @staticmethod
    def format_tsunami_message(tsunami: TsunamiData) -> str:
        """格式化海啸消息 - 丰富版本，包含更多实用信息"""
        lines = ["🌊【海啸预警】"]

        # 标题和级别
        if tsunami.title:
            lines.append(f"📋{tsunami.title}")
        if tsunami.level:
            lines.append(f"⚠️级别：{tsunami.level}")

        # 发布单位
        if tsunami.org_unit:
            lines.append(f"🏢发布：{tsunami.org_unit}")

        # 发布时间 - 添加时区信息
        if tsunami.issue_time:
            timezone = MessageFormatter._get_source_timezone(tsunami.source)
            lines.append(
                f"⏰发布时间：{tsunami.issue_time.strftime('%Y-%m-%d %H:%M:%S')} ({timezone})"
            )

        # 引发地震信息（如果有）
        if tsunami.subtitle:
            lines.append(f"🌍震源：{tsunami.subtitle}")

        # 预报区域详细信息
        if tsunami.forecasts:
            # 显示前2个区域的详细信息
            for i, forecast in enumerate(tsunami.forecasts[:2]):
                area_name = forecast.get("name", "")
                arrival_time = forecast.get("estimatedArrivalTime", "")
                max_wave = forecast.get("maxWaveHeight", "")
                area_level = forecast.get("warningLevel", "")

                if area_name:
                    # 基础区域信息
                    area_info = f"📍{area_name}"

                    # 添加警报级别（如果与主级别不同）
                    if area_level and area_level != tsunami.level:
                        area_info += f" [{area_level}]"

                    # 添加预计到达时间
                    if arrival_time:
                        area_info += f" 预计{arrival_time}到达"

                    # 添加预估波高
                    if max_wave:
                        area_info += f" 波高{max_wave}cm"

                    lines.append(area_info)

            # 如果还有更多区域，显示总数
            if len(tsunami.forecasts) > 2:
                lines.append(f"  ...等{len(tsunami.forecasts)}个预报区域")

        # 监测站实时数据（显示前2个监测站）
        if tsunami.monitoring_stations:
            lines.append("📊监测数据：")
            for i, station in enumerate(tsunami.monitoring_stations[:2]):
                station_name = station.get("stationName", "")
                location = station.get("location", "")
                max_wave = station.get("maxWaveHeight", "")
                monitor_time = station.get("time", "")

                if station_name:
                    station_info = f"  •{station_name}"
                    if location:
                        station_info += f"({location})"
                    if max_wave:
                        station_info += f" 波高{max_wave}cm"
                    if monitor_time:
                        station_info += f" {monitor_time}"
                    lines.append(station_info)

            # 如果还有更多监测站，显示总数
            if len(tsunami.monitoring_stations) > 2:
                lines.append(f"  ...等{len(tsunami.monitoring_stations)}个监测站")

        # 事件编码（用于追踪同一事件的更新）
        if tsunami.code:
            lines.append(f"🔄事件编号：{tsunami.code}")

        # 详细信息链接（从原始数据中提取）
        details = tsunami.raw_data.get("details", {})
        if details:
            html_url = details.get("htmlUrl", "")
            if html_url:
                lines.append(f"📄详情：{html_url}")

        return "\n".join(lines)

    @staticmethod
    def format_weather_message(weather: WeatherAlarmData) -> str:
        """格式化气象预警消息"""
        lines = ["⛈️【气象预警】"]

        # 标题
        if weather.headline:
            lines.append(f"📋{weather.headline}")

        # 描述
        if weather.description:
            # 限制描述长度
            desc = weather.description
            if len(desc) > 384:
                desc = desc[:384] + "..."
            lines.append(f"📝{desc}")

        # 生效时间 - 添加时区信息
        if weather.effective_time:
            timezone = MessageFormatter._get_source_timezone(weather.source)
            lines.append(
                f"⏰生效：{weather.effective_time.strftime('%Y-%m-%d %H:%M')} ({timezone})"
            )

        return "\n".join(lines)
