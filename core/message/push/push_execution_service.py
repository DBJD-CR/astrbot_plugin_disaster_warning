"""
消息推送执行服务。
负责会话级筛选、消息构建缓存、并发发送与推送结果汇总，
进一步减少 MessagePushManager 中的过程式编排代码。
"""

from __future__ import annotations

import asyncio
from typing import Any

from astrbot.api import logger
from astrbot.api.event import MessageChain

from ....models.models import DisasterEvent


class PushExecutionService:
    """消息推送执行服务。"""

    def __init__(self, manager):
        self.manager = manager

    async def execute(
        self,
        event: DisasterEvent,
        *,
        target_sessions: list[str] | None = None,
        session_config_getter=None,
    ) -> dict[str, Any]:
        """执行会话级推送流程并返回结果摘要。"""
        # 每次执行前重置成功会话列表，避免旧批次结果污染当前事件。
        self.manager.last_success_sessions = []

        sessions = (
            target_sessions
            if target_sessions is not None
            else self.manager.config.get("target_sessions", [])
        )
        if not sessions:
            logger.warning("[灾害预警] 没有配置目标会话，无法推送消息")
            return {
                "success": False,
                "push_success_count": 0,
                "passed_sessions": [],
                "session_message_format_config": {},
                "filter_reason_stats": {},
                "source_id": "",
            }

        source_id = self.manager.resolve_source_id_for_execution(event)
        push_success_count = 0
        passed_sessions: list[str] = []
        # 记录每个会话最终使用的 message_format，供后续地图拆分发送时按配置分组复用。
        session_message_format_config: dict[str, dict[str, Any]] = {}
        # 统计预筛阶段的拦截原因，便于输出汇总日志。
        filter_reason_stats: dict[str, int] = {}

        push_candidates = self._collect_push_candidates(
            event,
            sessions,
            session_config_getter=session_config_getter,
            filter_reason_stats=filter_reason_stats,
        )

        # 同一事件在不同会话下若渲染参数一致，则共享同一个消息构建任务，
        # 避免并发下重复渲染文本/地图/卡片。
        message_task_cache: dict[str, asyncio.Task[MessageChain]] = {}
        message_task_lock = asyncio.Lock()

        async def get_or_build_message(runtime_config: dict[str, Any]) -> MessageChain:
            cache_key = self.manager._build_message_build_cache_key(
                event, runtime_config
            )
            task = message_task_cache.get(cache_key)
            if task is None:
                async with message_task_lock:
                    task = message_task_cache.get(cache_key)
                    if task is None:
                        task = asyncio.create_task(
                            self.manager.build_message_async(
                                event, runtime_config=runtime_config
                            )
                        )
                        message_task_cache[cache_key] = task
            return await task

        async def push_to_session(
            session: str,
            runtime_config: dict[str, Any],
        ) -> tuple[bool, str, dict[str, Any] | None]:
            try:
                filter_reasons: list[str] = []
                # 预筛通过后，在真正发送前再次复核并提交报数状态，
                # 防止并发场景下状态变化导致“预筛可发、实际不该发”的竞态问题。
                if not self.manager.should_push_event(
                    event,
                    runtime_config=runtime_config,
                    session_id=session,
                    filter_reason_out=filter_reasons,
                    emit_filter_log=False,
                    commit_state=True,
                ):
                    reason = filter_reasons[0] if filter_reasons else "未通过推送条件"
                    reason_detail = filter_reasons[1] if len(filter_reasons) > 1 else ""
                    if reason_detail:
                        logger.debug(
                            f"[灾害预警] 事件 {event.id} 在会话 {session} 发送前复核未通过，原因：{reason}（{reason_detail}）"
                        )
                    else:
                        logger.debug(
                            f"[灾害预警] 事件 {event.id} 在会话 {session} 发送前复核未通过，原因：{reason}"
                        )
                    return False, session, None

                logger.debug(
                    f"[灾害预警] 事件 {event.id} 通过会话 {session} 的发送前复核，准备发送消息"
                )
                message = await get_or_build_message(runtime_config)
                await self.manager.send_message(session, message)
                logger.debug(f"[灾害预警] 事件 {event.id} 已推送到 {session}")
                return True, session, runtime_config.get("message_format", {})
            except Exception as e:
                logger.error(f"[灾害预警] 推送到 {session} 失败: {e}")
                return False, session, None

        if push_candidates:
            push_tasks = [
                asyncio.create_task(push_to_session(session, runtime_config))
                for session, runtime_config in push_candidates
            ]
            push_results = await asyncio.gather(*push_tasks, return_exceptions=True)

            for result in push_results:
                if isinstance(result, Exception):
                    logger.error(f"[灾害预警] 会话推送任务异常: {result}")
                    continue

                ok, session, msg_cfg = result
                if ok:
                    push_success_count += 1
                    passed_sessions.append(session)
                    session_message_format_config[session] = msg_cfg or {}

        self.manager.last_success_sessions = passed_sessions
        return {
            "success": push_success_count > 0,
            "push_success_count": push_success_count,
            "passed_sessions": passed_sessions,
            "session_message_format_config": session_message_format_config,
            "filter_reason_stats": filter_reason_stats,
            "source_id": source_id,
        }

    def _collect_push_candidates(
        self,
        event: DisasterEvent,
        sessions: list[str],
        *,
        session_config_getter=None,
        filter_reason_stats: dict[str, int] | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        # 这里仅做“预筛”，所以 commit_state=False，避免在真正发送前就提前消耗报数状态。
        candidates: list[tuple[str, dict[str, Any]]] = []
        if filter_reason_stats is None:
            filter_reason_stats = {}

        for session in sessions:
            runtime_config = (
                session_config_getter(session)
                if callable(session_config_getter)
                else self.manager.config
            )
            if not isinstance(runtime_config, dict):
                runtime_config = self.manager.config

            if runtime_config.get("push_enabled", True) is False:
                logger.debug(f"[灾害预警] 会话 {session} 推送开关关闭，跳过")
                continue

            filter_reasons: list[str] = []
            if not self.manager.should_push_event(
                event,
                runtime_config=runtime_config,
                session_id=session,
                filter_reason_out=filter_reasons,
                emit_filter_log=False,
                commit_state=False,
            ):
                reason = filter_reasons[0] if filter_reasons else "未通过推送条件"
                reason_detail = filter_reasons[1] if len(filter_reasons) > 1 else ""
                filter_reason_stats[reason] = filter_reason_stats.get(reason, 0) + 1
                if reason_detail:
                    logger.debug(
                        f"[灾害预警] 事件 {event.id} 在会话 {session} 的预筛选阶段被拦截，原因：{reason}（{reason_detail}）"
                    )
                else:
                    logger.debug(
                        f"[灾害预警] 事件 {event.id} 在会话 {session} 的预筛选阶段被拦截，原因：{reason}"
                    )
                continue

            candidates.append((session, runtime_config))

        return candidates
