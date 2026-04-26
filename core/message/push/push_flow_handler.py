"""
消息推送流处理器。
负责串联去重、执行、结果后处理与错误遥测，
统一协调推送链路中的轻量流程编排职责。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from astrbot.api import logger

from ...domain.event_models import EarthquakeEvent, EventEnvelope
from ...services.identity.event_identity import resolve_report_num
from ...sources.source_catalog import get_source_ids_by_type
from ...sources.source_entry import SourceType


class PushFlowHandler:
    """推送流处理器。"""

    def __init__(self, manager):
        # 该处理器专注于推送链中的轻量流程编排，不直接承担消息构建细节。
        self.manager = manager

    async def execute_push(
        self,
        event: EventEnvelope,
        target_sessions: list[str] | None = None,
        session_config_getter=None,
    ) -> bool:
        """执行完整推送流程：去重、会话执行、后处理与异常遥测。"""
        logger.debug(f"[灾害预警] 执行事件推送流程: {event.id}")

        if not self.manager.deduplicator.should_push_event(event):
            logger.debug(f"[灾害预警] 事件 {event.id} 被去重器过滤")
            return False

        try:
            execution_result = await self.manager.push_execution_service.execute(
                event,
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )
            return await self.handle_execution_result(event, execution_result)
        except Exception as e:
            logger.error(f"[灾害预警] 推送事件失败: {e}")
            if self.manager._telemetry and self.manager._telemetry.enabled:
                await self.manager._telemetry.track_error(
                    e,
                    module="core.message_manager._execute_push",
                )
            return False

    async def handle_execution_result(
        self,
        event: EventEnvelope,
        execution_result: dict[str, Any],
    ) -> bool:
        """处理推送执行结果并返回最终是否有成功推送。"""
        push_success_count = int(execution_result.get("push_success_count", 0))
        passed_sessions = list(execution_result.get("passed_sessions", []))
        session_message_format_config = dict(
            execution_result.get("session_message_format_config", {})
        )
        filter_reason_stats = dict(execution_result.get("filter_reason_stats", {}))
        filter_reason_detail_stats = dict(
            execution_result.get("filter_reason_detail_stats", {})
        )
        send_failure_stats = dict(execution_result.get("send_failure_stats", {}))

        # 分离地图属于后处理动作，只有在主消息已完成发送筛选后才有意义。
        await self._dispatch_split_maps(
            event,
            passed_sessions=passed_sessions,
            session_message_format_config=session_message_format_config,
        )

        self._log_filter_summary(
            event,
            push_success_count=push_success_count,
            filter_reason_stats=filter_reason_stats,
            filter_reason_detail_stats=filter_reason_detail_stats,
            send_failure_stats=send_failure_stats,
        )

        self.manager.last_success_sessions = list(passed_sessions)
        self._log_push_completion(
            event,
            push_success_count=push_success_count,
            filter_reason_stats=filter_reason_stats,
            filter_reason_detail_stats=filter_reason_detail_stats,
            send_failure_stats=send_failure_stats,
        )
        return push_success_count > 0

    async def _dispatch_split_maps(
        self,
        event: EventEnvelope,
        *,
        passed_sessions: list[str],
        session_message_format_config: dict[str, dict[str, Any]],
    ) -> None:
        """为需要拆分地图的事件按配置分组异步派发地图推送。"""
        source_id = (getattr(event, "source_id", "") or "").strip()
        split_map_sources = set(
            get_source_ids_by_type(SourceType.EARTHQUAKE_WARNING)
        ) - {"global_quake"}
        domain_event = event.event
        if source_id not in split_map_sources or not isinstance(
            domain_event, EarthquakeEvent
        ):
            return

        identity = getattr(event, "identity", None)
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        current_report = resolve_report_num(event) or 1
        is_final = bool(
            getattr(identity, "is_final", False) or metadata.get("is_final", False)
        )
        # 分离地图不必每一报都发送，按首报、固定间隔报或最终报触发即可。
        map_push_n = 5
        should_gen_map = (
            current_report == 1 or current_report % map_push_n == 0 or is_final
        )
        if not should_gen_map or not passed_sessions:
            return

        logger.debug(f"[灾害预警] 触发异步地图渲染 (第 {current_report} 报)")
        grouped_sessions: dict[str, list[str]] = {}
        grouped_config: dict[str, dict[str, Any]] = {}
        for session in passed_sessions:
            msg_cfg = session_message_format_config.get(session, {})
            if not msg_cfg.get("include_map", False):
                continue

            config_key = json.dumps(msg_cfg, sort_keys=True, ensure_ascii=False)
            if config_key not in grouped_sessions:
                grouped_sessions[config_key] = []
                grouped_config[config_key] = msg_cfg
            grouped_sessions[config_key].append(session)

        for config_key, sessions in grouped_sessions.items():
            # 按消息格式配置分组后再异步派发，避免不同地图样式被错误混发。
            asyncio.create_task(
                self.manager.message_build_service.push_split_map(
                    event,
                    sessions,
                    grouped_config[config_key],
                )
            )

    def _log_filter_summary(
        self,
        event: EventEnvelope,
        *,
        push_success_count: int,
        filter_reason_stats: dict[str, int],
        filter_reason_detail_stats: dict[str, int],
        send_failure_stats: dict[str, int],
    ) -> None:
        """记录会话筛选结果摘要。"""
        # 这里把“规则拦截”和“发送失败”分开汇总，避免排障时混淆问题阶段。
        failure_summary = "，".join(
            f"{reason} {count} 个会话"
            for reason, count in sorted(send_failure_stats.items())
        )
        failure_suffix = f"，另有 {failure_summary} 发送失败" if failure_summary else ""

        detailed_stats = filter_reason_detail_stats or filter_reason_stats
        if detailed_stats:
            summary = "，".join(
                f"{reason} {count} 个会话"
                for reason, count in sorted(detailed_stats.items())
            )
            if push_success_count > 0:
                logger.info(
                    f"[灾害预警] 事件 {event.id} 已完成会话筛选，{push_success_count} 个会话通过，另有 {summary} 被拦截{failure_suffix}"
                )
            else:
                logger.info(
                    f"[灾害预警] 事件 {event.id} 未通过任何会话的推送条件，拦截情况：{summary}{failure_suffix}"
                )
        elif push_success_count > 0:
            logger.info(
                f"[灾害预警] 事件 {event.id} 已通过全部会话的推送条件，共 {push_success_count} 个会话{failure_suffix}"
            )
        elif failure_summary:
            logger.info(
                f"[灾害预警] 事件 {event.id} 已通过发送前筛选，但发送阶段全部失败：{failure_summary}"
            )

    def _log_push_completion(
        self,
        event: EventEnvelope,
        *,
        push_success_count: int,
        filter_reason_stats: dict[str, int],
        filter_reason_detail_stats: dict[str, int],
        send_failure_stats: dict[str, int],
    ) -> None:
        """记录推送完成日志。"""
        # 这一层更偏向最终完成态日志，与前面的筛选摘要日志形成互补。
        detailed_stats = filter_reason_detail_stats or filter_reason_stats
        if detailed_stats and push_success_count > 0:
            summary = "，".join(
                f"{reason}×{count}" for reason, count in sorted(detailed_stats.items())
            )
            logger.debug(f"[灾害预警] 事件 {event.id} 部分会话被过滤: {summary}")

        if send_failure_stats:
            summary = "，".join(
                f"{reason}×{count}"
                for reason, count in sorted(send_failure_stats.items())
            )
            logger.debug(f"[灾害预警] 事件 {event.id} 部分会话发送失败: {summary}")

        if push_success_count > 0:
            logger.info(
                f"[灾害预警] 事件 {event.id} 推送完成，成功推送到 {push_success_count} 个会话"
            )
        elif send_failure_stats:
            logger.warning(
                f"[灾害预警] 事件 {event.id} 推送完成，但没有任何会话发送成功"
            )
