"""
事件去重器
允许多数据源推送同一事件，但防止同一数据源重复推送
"""

from datetime import datetime, timedelta, timezone

from astrbot.api import logger

from ..models.models import DataSource, DisasterEvent, EarthquakeData


class EventDeduplicator:
    """事件去重器 - 允许多数据源推送同一事件"""

    def __init__(
        self,
        time_window_minutes: int = 1,
        location_tolerance_km: float = 20.0,
        magnitude_tolerance: float = 0.5,
    ):
        self.time_window = timedelta(minutes=time_window_minutes)
        self.location_tolerance = location_tolerance_km
        self.magnitude_tolerance = magnitude_tolerance

        # 记录每个数据源的事件：事件指纹 -> {数据源: 事件信息}
        self.recent_events: dict[str, dict[str, dict]] = {}

    def should_push_event(self, event: DisasterEvent) -> bool:
        """判断是否应该推送事件 - 允许多数据源推送同一事件"""
        if not isinstance(event.data, EarthquakeData):
            return True  # 非地震事件直接推送

        earthquake = event.data
        source_id = self._get_source_id(event)

        # 生成事件指纹
        event_fingerprint = self.generate_event_fingerprint(earthquake)

        # 关键修复：如果地震时间解析失败，使用当前时间作为后备
        current_time = (
            earthquake.shock_time
            if earthquake.shock_time is not None
            else datetime.now(timezone.utc)
        )

        logger.debug(
            f"[灾害预警] 检查事件: {event.source.value}, 指纹: {event_fingerprint}"
        )

        # 检查是否已有相似事件
        if event_fingerprint in self.recent_events:
            source_events = self.recent_events[event_fingerprint]

            # 检查同一数据源是否已推送过
            if source_id in source_events:
                existing_event = source_events[source_id]

                # 如果在时间窗口内，检查是否允许更新
                time_diff = abs(
                    (current_time - existing_event["timestamp"]).total_seconds() / 60
                )

                if time_diff <= self.time_window.total_seconds() / 60:
                    if self._should_allow_update(earthquake, existing_event):
                        logger.debug(
                            f"[灾害预警] 允许同一数据源更新: {event.source.value}"
                        )
                        # 更新记录 - 添加当前报数到已处理集合
                        current_report = getattr(earthquake, "updates", 1)
                        existing_event["processed_reports"].add(current_report)
                        existing_event["timestamp"] = current_time
                        existing_event["is_final"] = existing_event[
                            "is_final"
                        ] or getattr(earthquake, "is_final", False)
                        return True
                    else:
                        logger.debug(
                            f"[灾害预警] 同一数据源重复事件，过滤: {event.source.value}"
                        )
                        return False
                else:
                    logger.debug("[灾害预警] 同一数据源事件已过期，允许推送")

            # 不同数据源，允许推送（允许多数据源推送同一事件）
            logger.info(f"[灾害预警] 不同数据源，允许推送: {event.source.value}")
            current_report = getattr(earthquake, "updates", 1)
            # 提取JMA issue_type
            issue_type = ""
            if hasattr(earthquake, "raw_data") and isinstance(
                earthquake.raw_data, dict
            ):
                issue_type = earthquake.raw_data.get("issue", {}).get("type", "")

            self.recent_events[event_fingerprint][source_id] = {
                "timestamp": current_time,
                "source": event.source.value,
                "latitude": earthquake.latitude or 0,
                "longitude": earthquake.longitude or 0,
                "magnitude": earthquake.magnitude or 0,
                "info_type": earthquake.info_type or "",
                "issue_type": issue_type,  # 保存JMA issue type
                "processed_reports": {current_report},  # 使用集合存储已处理的报数
                "is_final": getattr(earthquake, "is_final", False),
            }
            return True

        # 新事件，记录并允许推送
        current_report = getattr(earthquake, "updates", 1)

        # 提取JMA issue_type
        issue_type = ""
        if hasattr(earthquake, "raw_data") and isinstance(earthquake.raw_data, dict):
            issue_type = earthquake.raw_data.get("issue", {}).get("type", "")

        self.recent_events[event_fingerprint] = {
            source_id: {
                "timestamp": current_time,
                "source": event.source.value,
                "latitude": earthquake.latitude or 0,
                "longitude": earthquake.longitude or 0,
                "magnitude": earthquake.magnitude or 0,
                "info_type": earthquake.info_type or "",
                "issue_type": issue_type,  # 保存JMA issue type
                "processed_reports": {current_report},  # 使用集合存储已处理的报数
                "is_final": getattr(earthquake, "is_final", False),
            }
        }

        logger.debug(f"[灾害预警] 事件通过基础去重检查: {event.source.value}")
        return True

    def generate_event_fingerprint(self, earthquake: EarthquakeData) -> str:
        """生成事件指纹 - 基于地理位置和震级的简化指纹"""
        # GlobalQuake使用UUID作为事件ID，直接使用该ID作为指纹
        # 这样可以避免同一事件因为毫秒级时间差异而生成不同指纹
        if earthquake.source == DataSource.GLOBAL_QUAKE:
            event_id = earthquake.event_id or earthquake.id
            if event_id:
                return f"gq_{event_id}"

        if not earthquake.latitude or not earthquake.longitude:
            return "unknown_location"

        # 将坐标量化到指定精度（20km网格）
        lat_grid = round(earthquake.latitude * (111.0 / self.location_tolerance)) / (
            111.0 / self.location_tolerance
        )
        lon_grid = round(earthquake.longitude * (111.0 / self.location_tolerance)) / (
            111.0 / self.location_tolerance
        )

        # 震级量化到容差级别
        mag_grid = (
            round((earthquake.magnitude or 0) / self.magnitude_tolerance)
            * self.magnitude_tolerance
        )

        # 处理时间：统一转换为UTC aware datetime并截断到分钟
        shock_time = earthquake.shock_time
        # 如果是naive datetime，添加UTC时区
        if shock_time.tzinfo is None:
            shock_time = shock_time.replace(tzinfo=timezone.utc)
        time_minute = shock_time.replace(second=0, microsecond=0)

        return f"{lat_grid:.3f},{lon_grid:.3f},{mag_grid:.1f},{time_minute.strftime('%Y%m%d%H%M')}"

    def _should_allow_update(
        self, current_earthquake: EarthquakeData, existing_event: dict
    ) -> bool:
        """判断是否应该允许事件更新"""
        # 获取当前报数
        current_report = getattr(current_earthquake, "updates", 1)

        # 获取已处理的报数集合（兼容旧格式）
        processed_reports = existing_event.get("processed_reports", set())
        if not isinstance(processed_reports, set):
            # 兼容旧的 updates 字段格式
            old_updates = existing_event.get("updates", 1)
            processed_reports = {old_updates}

        # 检查当前报数是否已处理过
        if current_report not in processed_reports:
            logger.debug(
                f"[灾害预警] 新报数: 第{current_report}报 (已处理: {sorted(processed_reports)})"
            )
            return True

        # 最终报检查 - 即使报数已处理，如果变为最终报也允许
        if getattr(current_earthquake, "is_final", False) and not existing_event.get(
            "is_final", False
        ):
            logger.info("[灾害预警] 最终报更新: 非最终报 -> 最终报")
            return True

        # USGS状态升级
        if current_earthquake.source == DataSource.FAN_STUDIO_USGS:
            current_info_type = (current_earthquake.info_type or "").lower()
            existing_info_type = (existing_event.get("info_type", "") or "").lower()

            if existing_info_type == "automatic" and current_info_type == "reviewed":
                logger.debug("[灾害预警] 允许USGS状态升级: automatic -> reviewed")
                return True

        # JMA地震情报状态升级检测
        # 优先级: 震度速报 < 震源相关情报 < 震源・震度情报 < 各地震度相关情报
        # 对应的 issue type: ScalePrompt < Destination < ScaleAndDestination < DetailScale
        jma_types = ["ScalePrompt", "Destination", "ScaleAndDestination", "DetailScale"]

        # 获取当前的 issue type
        current_issue_type = ""
        if hasattr(current_earthquake, "raw_data") and isinstance(
            current_earthquake.raw_data, dict
        ):
            current_issue_type = current_earthquake.raw_data.get("issue", {}).get(
                "type", ""
            )

        # 获取已存在的 issue type
        existing_issue_type = existing_event.get("issue_type", "")

        if current_issue_type in jma_types and existing_issue_type in jma_types:
            try:
                curr_idx = jma_types.index(current_issue_type)
                prev_idx = jma_types.index(existing_issue_type)
                # 只有状态升级（索引变大）时才允许更新
                if curr_idx > prev_idx:
                    logger.info(
                        f"[灾害预警] 允许JMA情报升级: {existing_issue_type} -> {current_issue_type}"
                    )
                    return True
            except ValueError:
                pass

        # 通用状态升级（针对CENC等）
        current_info_type = (current_earthquake.info_type or "").lower()
        existing_info_type = (existing_event.get("info_type", "") or "").lower()

        # 自动测定 -> 正式测定
        if "自动" in existing_info_type and "正式" in current_info_type:
            logger.info(
                f"[灾害预警] 允许状态升级: {existing_info_type} -> {current_info_type}"
            )
            return True

        logger.debug(f"[灾害预警] 报数 {current_report} 已处理过，跳过")
        return False

    def _get_source_id(self, event: DisasterEvent) -> str:
        """获取事件的数据源ID"""
        source_mapping = {
            DataSource.FAN_STUDIO_CEA.value: "cea_fanstudio",
            DataSource.WOLFX_CENC_EEW.value: "cea_wolfx",
            DataSource.FAN_STUDIO_CWA.value: "cwa_fanstudio",
            DataSource.WOLFX_CWA_EEW.value: "cwa_wolfx",
            DataSource.FAN_STUDIO_JMA.value: "jma_fanstudio",
            DataSource.P2P_EEW.value: "jma_p2p",
            DataSource.P2P_EARTHQUAKE.value: "jma_p2p_info",
            DataSource.WOLFX_JMA_EEW.value: "jma_wolfx",
            DataSource.FAN_STUDIO_CENC.value: "cenc_fanstudio",
            DataSource.FAN_STUDIO_USGS.value: "usgs_fanstudio",
            DataSource.GLOBAL_QUAKE.value: "global_quake",
        }

        return source_mapping.get(event.source.value, event.source.value)

    def cleanup_old_events(self):
        """清理过期事件"""
        cutoff_time = datetime.now(timezone.utc) - self.time_window * 2  # 保留2倍时间窗口

        old_fingerprints = []
        for fingerprint, source_events in self.recent_events.items():
            # 检查所有数据源的事件是否都过期
            all_expired = True
            for event_info in source_events.values():
                timestamp = event_info["timestamp"]

                # 根据时间戳类型选择对应的截止时间进行比较
                if timestamp.tzinfo is None:
                    # naive datetime，转换为aware后比较
                    cutoff_naive = cutoff_time.replace(tzinfo=None)
                    if timestamp >= cutoff_naive:
                        all_expired = False
                        break
                else:
                    # offset-aware 时间可以直接与其他 offset-aware 时间比较
                    if timestamp >= cutoff_time:
                        all_expired = False
                        break

            if all_expired:
                old_fingerprints.append(fingerprint)

        for fingerprint in old_fingerprints:
            del self.recent_events[fingerprint]
