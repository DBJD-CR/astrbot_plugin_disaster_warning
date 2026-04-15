"""
消息推送过滤策略。
从 MessagePushManager 中拆出的纯判定逻辑，负责根据运行时组件判断事件是否应推送。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ....models.data_source_config import (
    get_intensity_based_sources,
    get_scale_based_sources,
    is_source_enabled_in_data_sources,
)
from ....models.models import DisasterEvent, EarthquakeData, WeatherAlarmData
from ...support.event_metadata import resolve_event_time_aware, resolve_source_id


def should_push_event_with_components(
    event: DisasterEvent,
    *,
    runtime_config: dict[str, Any],
    runtime_components: dict[str, Any],
    session_id: str | None = None,
    filter_reason_out: list[str] | None = None,
    emit_filter_log: bool = True,
    commit_state: bool = True,
    logger_instance=None,
) -> bool:
    """基于运行时组件判断是否应该推送事件。"""

    def reject(reason: str, log_message: str | None = None) -> bool:
        # 统一封装拒绝出口，保证筛选原因采集与日志行为一致。
        if filter_reason_out is not None:
            filter_reason_out.append(reason)
        if emit_filter_log and log_message and logger_instance is not None:
            logger_instance.info(log_message)
        return False

    def reject_with_detail(
        reason: str,
        detail: str | None = None,
        log_message: str | None = None,
    ) -> bool:
        # 某些过滤器会输出主因 + 细节，调用方可用 [0]/[1] 约定读取。
        if filter_reason_out is not None:
            filter_reason_out.append(reason)
            if detail:
                filter_reason_out.append(detail)
        if emit_filter_log and log_message and logger_instance is not None:
            logger_instance.info(log_message)
        return False

    # 第一层：过滤明显过旧的事件，防止历史消息在重连/补拉时重新推送。
    event_time_aware = resolve_event_time_aware(event)
    if event_time_aware:
        current_time_utc = datetime.now(timezone.utc)
        time_diff = (current_time_utc - event_time_aware).total_seconds() / 3600
        if time_diff > 1:
            return reject(
                "事件时间过早",
                f"[灾害预警] 事件时间过早（{time_diff:.1f}小时前），过滤",
            )

    # 第二层：检查当前会话是否启用了该数据源。
    source_id = resolve_source_id(event)
    data_sources_cfg = runtime_config.get("data_sources", {})
    if not is_source_enabled_in_data_sources(source_id, data_sources_cfg):
        return reject(
            "会话数据源开关关闭",
            f"[灾害预警] 会话 {session_id or 'global'} 已禁用数据源 {source_id}，跳过推送",
        )

    # 非地震事件只走各自专属过滤逻辑；气象预警会额外通过 weather_filter 做文本规则过滤。
    if not isinstance(event.data, EarthquakeData):
        if isinstance(event.data, WeatherAlarmData):
            title_text = event.data.title or event.data.headline or ""
            weather_decision = runtime_components["weather_filter"].evaluate(
                title_text,
                event.data.headline or "",
            )
            if weather_decision.get("filtered"):
                return reject_with_detail(
                    str(weather_decision.get("reason") or "气象预警过滤"),
                    str(weather_decision.get("detail") or ""),
                )
        return True

    earthquake = event.data
    # 地震类事件先过关键词过滤，属于最粗粒度的文本级阻断。
    if runtime_components["keyword_filter"].should_filter(earthquake):
        return reject(
            "关键词过滤",
            f"[灾害预警] 事件被关键词过滤器过滤: {source_id}",
        )

    # 按数据源类别分别进入不同强度/震级过滤器。
    if source_id == "global_quake":
        if runtime_components["global_quake_filter"].should_filter(earthquake):
            return reject(
                "Global Quake过滤器",
                "[灾害预警] 事件被Global Quake过滤器过滤",
            )
    elif source_id in get_intensity_based_sources():
        if runtime_components["intensity_filter"].should_filter(earthquake):
            return reject(
                "烈度过滤器",
                f"[灾害预警] 事件被烈度过滤器过滤: {source_id}",
            )
    elif source_id in get_scale_based_sources():
        if runtime_components["scale_filter"].should_filter(earthquake):
            return reject(
                "震度过滤器",
                f"[灾害预警] 事件被震度过滤器过滤: {source_id}",
            )
    elif source_id == "usgs_fanstudio":
        if runtime_components["usgs_filter"].should_filter(earthquake):
            return reject("USGS过滤器", "[灾害预警] 事件被USGS过滤器过滤")

    # 报数控制器既可用于预筛，也可用于真正发送前提交状态，取决于 commit_state。
    if not runtime_components["report_controller"].should_push_report(
        event, commit_state=commit_state
    ):
        return reject(
            "报数控制器",
            f"[灾害预警] 事件被报数控制器过滤: {source_id}",
        )

    # 本地监控会在需要时为事件补充本地估算，并可基于本地条件阻止推送。
    result = runtime_components["local_monitor"].inject_local_estimation(earthquake)
    if result is not None and not result.get("is_allowed", True):
        return reject("本地监控过滤")

    return True
