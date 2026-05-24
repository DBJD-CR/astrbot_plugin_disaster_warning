"""
消息推送执行服务。
负责会话级筛选、消息构建缓存、并发发送与推送结果汇总，
进一步减少 MessagePushManager 中的过程式编排代码。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain

from ...domain.event_models import EventEnvelope


class PushExecutionService:
    """消息推送执行服务。"""

    def __init__(self, manager):
        # 执行服务通过主消息管理器获取会话发送、消息构建与规则评估能力。
        self.manager = manager  # 主消息管理器 MessagePushManager 实例

    @staticmethod
    def _build_plaintext_fallback_message(message: MessageChain) -> MessageChain | None:
        """构建发送失败后的降级消息，保留文本与安全的本地图片组件。"""
        if not isinstance(message, MessageChain):
            return None

        fallback_components: list[Any] = []
        text_parts: list[str] = []
        for component in getattr(message, "chain", []) or []:
            text = getattr(component, "text", None)
            if isinstance(text, str) and text.strip():
                text_parts.append(text)
                continue

            component_type = type(component).__name__.lower()
            if "image" not in component_type:
                continue

            file_attr = getattr(component, "file", None)
            path_attr = getattr(component, "path", None)
            url_attr = getattr(component, "url", None)
            data_attr = getattr(component, "data", None)
            base64_attr = getattr(component, "base64", None)

            # 只保留非 HTTP 外部网络地址的安全本地物理路径图片及 Base64 字符图片做降级发送，过滤危险的不在线网络大图
            if (
                isinstance(file_attr, str)
                and file_attr.strip()
                and not str(file_attr).startswith(("http://", "https://"))
            ):
                fallback_components.append(component)
                continue
            if (
                isinstance(path_attr, str)
                and path_attr.strip()
                and not str(path_attr).startswith(("http://", "https://"))
            ):
                fallback_components.append(component)
                continue
            if data_attr:
                fallback_components.append(component)
                continue
            if isinstance(base64_attr, str) and base64_attr.strip():
                fallback_components.append(component)
                continue
            if isinstance(url_attr, str) and url_attr.strip().startswith(
                ("http://", "https://")
            ):
                continue

        merged_text = "\n".join(
            part.rstrip() for part in text_parts if part.strip()
        ).strip()
        if merged_text:
            fallback_components.insert(0, Plain(merged_text))

        if not fallback_components:
            return None
        return MessageChain(fallback_components)

    async def execute(
        self,
        event: EventEnvelope,
        *,
        target_sessions: list[str] | None = None,
        session_config_getter=None,
        commit_state: bool = True,
    ) -> dict[str, Any]:
        """执行会话级消息过滤评估、动态并发渲染与最终投递派发。"""
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

        source_id = (getattr(event, "source_id", "") or "").strip()
        push_success_count = 0
        passed_sessions: list[str] = []
        # 记录每个会话最终使用的 message_format，供后续地图拆分发送时按配置分组复用。
        session_message_format_config: dict[str, dict[str, Any]] = {}
        # 统计预筛阶段的拦截原因，便于输出汇总日志。
        filter_reason_stats: dict[str, int] = {}
        # 保留更细粒度的拦截原因明细，避免不同数据源/分组被压扁成同一句日志。
        filter_reason_detail_stats: dict[str, int] = {}
        # 统计实际发送阶段的失败原因，避免与规则拦截混淆。
        send_failure_stats: dict[str, int] = {}

        # 收集预筛选通过的所有会话名单与配置
        push_candidates = self._collect_push_candidates(
            event,
            sessions,
            session_config_getter=session_config_getter,
            filter_reason_stats=filter_reason_stats,
            filter_reason_detail_stats=filter_reason_detail_stats,
        )

        # 同一事件在不同会话下若渲染参数一致，则共享同一个消息构建任务，
        # 避免并发下重复渲染文本/地图/卡片。
        message_task_cache: dict[str, asyncio.Task[MessageChain]] = {}
        message_task_lock = asyncio.Lock()

        async def get_or_build_message(runtime_config: dict[str, Any]) -> MessageChain:
            # 构建缓存键时纳入所有会影响展示结果的关键配置，避免不同配置误复用。
            message_format_config = runtime_config.get("message_format", {})
            weather_config = runtime_config.get("weather_config", {})
            cache_key = json.dumps(
                {
                    "event_id": event.id,
                    "source": event.source_id,
                    "event_type": event.event_type,
                    "display_timezone": runtime_config.get("display_timezone", "UTC+8"),
                    "message_format": {
                        "include_map": message_format_config.get("include_map", False),
                        "map_source": message_format_config.get(
                            "map_source", "PetalMap矢量图亮"
                        ),
                        "map_zoom_level": message_format_config.get(
                            "map_zoom_level", 5
                        ),
                        "playwright_mode": message_format_config.get(
                            "playwright_mode", "local"
                        ),
                        "use_global_quake_card": message_format_config.get(
                            "use_global_quake_card", False
                        ),
                        "global_quake_template": message_format_config.get(
                            "global_quake_template", "Aurora"
                        ),
                        "detailed_jma_intensity": message_format_config.get(
                            "detailed_jma_intensity", False
                        ),
                    },
                    "weather": {
                        "enable_weather_icon": weather_config.get(
                            "enable_weather_icon", True
                        ),
                        "max_description_length": weather_config.get(
                            "max_description_length", 384
                        ),
                    },
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            task = message_task_cache.get(cache_key)
            if task is None:
                async with message_task_lock:
                    task = message_task_cache.get(cache_key)
                    if task is None:
                        # 触发异步消息渲染任务 (包含文本和地图卡片渲染)
                        task = asyncio.create_task(
                            self.manager.message_build_service.build_message_async(
                                event,
                                runtime_config=runtime_config,
                            )
                        )
                        message_task_cache[cache_key] = task
            return await task

        async def push_to_session(
            session: str,
            runtime_config: dict[str, Any],
        ) -> tuple[bool, str, dict[str, Any] | None, str | None]:
            try:
                # 预筛通过后，在真正发送前再次复核；真实推送提交报数状态，
                # 模拟推送只复用筛选与渲染链路，不污染运行时规则状态。
                decision = self.manager.evaluate_push_decision(
                    event,
                    runtime_config=runtime_config,
                    session_id=session,
                    emit_filter_log=False,
                    commit_state=commit_state,
                )
                if not decision.accepted:
                    if decision.detail:
                        logger.debug(
                            f"[灾害预警] 事件 {event.id} 在会话 {session} 发送前复核未通过，原因：{decision.reason}（{decision.detail}）"
                        )
                    else:
                        logger.debug(
                            f"[灾害预警] 事件 {event.id} 在会话 {session} 发送前复核未通过，原因：{decision.reason}"
                        )
                    return False, session, None, "发送前复核未通过"

                logger.debug(
                    f"[灾害预警] 事件 {event.id} 通过会话 {session} 的发送前复核，准备发送消息"
                )
                # 获取复用或动态渲染的图片/卡片消息链
                message = await get_or_build_message(runtime_config)
                # 调用底座 Session 发送器下发消息
                await self.manager.session_sender.send(session, message)
                logger.debug(f"[灾害预警] 事件 {event.id} 已推送到 {session}")
                return True, session, runtime_config.get("message_format", {}), None
            except Exception as e:
                error_name = type(e).__name__
                logger.error(f"[灾害预警] 推送到 {session} 失败: {e}")

                # 如果富媒体发送失败，则尝试从原消息链中提取纯文本进行降级重发。
                fallback_message = self._build_plaintext_fallback_message(
                    locals().get("message")
                )
                if fallback_message is not None:
                    try:
                        await self.manager.session_sender.send(
                            session, fallback_message
                        )
                        logger.warning(
                            f"[灾害预警] 会话 {session} 富媒体发送失败，已自动降级重发: {error_name}"
                        )
                        return (
                            True,
                            session,
                            runtime_config.get("message_format", {}),
                            None,
                        )
                    except Exception as fallback_error:
                        fallback_error_name = type(fallback_error).__name__
                        logger.error(
                            f"[灾害预警] 会话 {session} 纯文本降级重发失败: {fallback_error}"
                        )
                        return (
                            False,
                            session,
                            None,
                            f"富媒体发送失败({error_name})，纯文本降级失败({fallback_error_name})",
                        )

                logger.warning(
                    f"[灾害预警] 会话 {session} 富媒体发送失败，且消息中无可用纯文本可降级: {error_name}"
                )
                return False, session, None, f"富媒体发送失败({error_name})"

        if push_candidates:
            # 通过并发发送缩短整批会话推送耗时，但单个会话的发送前复核仍各自独立执行。
            push_tasks = [
                asyncio.create_task(push_to_session(session, runtime_config))
                for session, runtime_config in push_candidates
            ]
            push_results = await asyncio.gather(*push_tasks, return_exceptions=True)

            for result in push_results:
                if isinstance(result, Exception):
                    logger.error(f"[灾害预警] 会话推送任务异常: {result}")
                    continue

                ok, session, msg_cfg, failure_reason = result
                if ok:
                    push_success_count += 1
                    passed_sessions.append(session)
                    session_message_format_config[session] = msg_cfg or {}
                elif failure_reason:
                    send_failure_stats[failure_reason] = (
                        send_failure_stats.get(failure_reason, 0) + 1
                    )

        self.manager.last_success_sessions = passed_sessions
        return {
            "success": push_success_count > 0,
            "push_success_count": push_success_count,
            "passed_sessions": passed_sessions,
            "session_message_format_config": session_message_format_config,
            "filter_reason_stats": filter_reason_stats,
            "filter_reason_detail_stats": filter_reason_detail_stats,
            "send_failure_stats": send_failure_stats,
            "source_id": source_id,
        }

    def _collect_push_candidates(
        self,
        event: EventEnvelope,
        sessions: list[str],
        *,
        session_config_getter=None,
        filter_reason_stats: dict[str, int] | None = None,
        filter_reason_detail_stats: dict[str, int] | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        """收集所有通过初筛的待发送目标会话名单（commit_state为False，在此阶段不污染报数状态）。"""
        # 这里仅做“预筛”，所以 commit_state=False，避免在真正发送前就提前消耗报数状态。
        candidates: list[tuple[str, dict[str, Any]]] = []
        if filter_reason_stats is None:
            filter_reason_stats = {}
        if filter_reason_detail_stats is None:
            filter_reason_detail_stats = {}

        simulation_bypass = bool(
            getattr(event, "metadata", {}).get(
                "simulation_bypass_regular_filters", False
            )
        )

        for session in sessions:
            # 会话级配置允许不同会话使用不同推送规则与展示参数。
            runtime_config = (
                session_config_getter(session)
                if callable(session_config_getter)
                else self.manager.config
            )
            if not isinstance(runtime_config, dict):
                runtime_config = self.manager.config
            else:
                runtime_config = dict(runtime_config)

            if simulation_bypass:
                runtime_config["__simulation_bypass_regular_filters"] = True

            if runtime_config.get("push_enabled", True) is False:
                if simulation_bypass:
                    runtime_config["push_enabled"] = True
                else:
                    logger.debug(f"[灾害预警] 会话 {session} 推送开关关闭，跳过")
                    continue

            # 过滤判定评估
            decision = self.manager.evaluate_push_decision(
                event,
                runtime_config=runtime_config,
                session_id=session,
                emit_filter_log=False,
                commit_state=False,
            )
            if not decision.accepted:
                reason = decision.reason or "未通过推送条件"
                reason_detail = decision.detail or ""
                filter_reason_stats[reason] = filter_reason_stats.get(reason, 0) + 1
                detail_key = f"{reason}（{reason_detail}）" if reason_detail else reason
                filter_reason_detail_stats[detail_key] = (
                    filter_reason_detail_stats.get(detail_key, 0) + 1
                )
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
