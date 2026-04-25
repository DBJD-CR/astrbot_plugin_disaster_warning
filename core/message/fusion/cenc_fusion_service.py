"""
CENC 融合策略服务。
负责处理 Fan CENC 等待 Wolfx 烈度补充与 Wolfx 到达后的缓存/唤醒流程。
"""

from __future__ import annotations

import asyncio
import time

from astrbot.api import logger

from ...domain.event_models import EarthquakeEvent, EventEnvelope


class CENCFusionService:
    """CENC 融合策略服务。"""

    def __init__(self, manager, execute_push):
        # 融合服务通过主消息管理器访问融合状态仓储，并复用统一推送执行入口。
        self.manager = manager
        self._execute_push = execute_push

    @staticmethod
    def _get_earthquake_data(
        event: EventEnvelope,
    ) -> EarthquakeEvent | None:
        data = getattr(event, "event", None)
        if isinstance(data, EarthquakeEvent):
            return data
        return None

    async def intercept_fan_event(
        self,
        event: EventEnvelope,
        timeout: int,
        *,
        target_sessions: list[str] | None = None,
        session_config_getter=None,
    ) -> bool:
        """拦截 Fan 侧事件并等待 Wolfx 烈度补充。"""
        earthquake = self._get_earthquake_data(event)
        if earthquake is None:
            return await self._execute_push(
                event,
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        store = self.manager._fusion_state_store
        store.prune()

        event_key = store.get_fusion_event_key(earthquake)
        report_num = store.get_fusion_report_num(earthquake)
        cached_payload = store.select_cached_report_payload(
            store.cenc_wolfx_cache.get(event_key, {}), report_num
        )
        if (
            isinstance(cached_payload, dict)
            and cached_payload.get("intensity") is not None
        ):
            earthquake.intensity = cached_payload["intensity"]
            logger.info(
                f"[灾害预警] 融合策略: Fan CENC 事件 {event.id} 命中 Wolfx 缓存并补充烈度: {earthquake.intensity}"
            )
            return await self._execute_push(
                event,
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        logger.info(
            f"[灾害预警] 融合策略: 拦截 Fan CENC 事件 {event.id} (event_key={event_key}, report={report_num})，等待 Wolfx 补充 ({timeout}s)..."
        )

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        # pending_key 需要足够唯一，避免同一事件同一报次的并发等待互相覆盖。
        pending_key = f"{event_key}#{report_num}#{event.id}#{int(time.time() * 1000)}"

        store.cenc_pending[pending_key] = {
            "event": event,
            "future": future,
            "event_key": event_key,
            "report_num": report_num,
            "created_at": time.time(),
        }

        async def wait_timeout():
            try:
                await asyncio.sleep(timeout)
                if not future.done():
                    future.set_result("timeout")
            except Exception as e:
                if not future.done():
                    future.set_exception(e)

        asyncio.create_task(wait_timeout())

        try:
            result = await future
            store.cenc_pending.pop(pending_key, None)

            if result == "timeout":
                logger.info("[灾害预警] 融合策略: CENC 等待超时，推送原始 Fan 事件")
                return await self._execute_push(
                    event,
                    target_sessions=target_sessions,
                    session_config_getter=session_config_getter,
                )
            if result == "fused":
                logger.info("[灾害预警] 融合策略: CENC 融合完成，推送补充后的 Fan 事件")
                return await self._execute_push(
                    event,
                    target_sessions=target_sessions,
                    session_config_getter=session_config_getter,
                )
        except Exception as e:
            logger.error(f"[灾害预警] CENC 融合策略处理异常: {e}")
            return await self._execute_push(
                event,
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        return False

    def handle_wolfx_event(self, wolfx_event: EventEnvelope):
        """处理 Wolfx 到达事件，并尝试唤醒等待中的 Fan CENC 事件。"""
        earthquake = self._get_earthquake_data(wolfx_event)
        if earthquake is None:
            return

        intensity = getattr(earthquake, "intensity", None)
        if intensity is None:
            return

        store = self.manager._fusion_state_store
        store.prune()

        event_key = store.get_fusion_event_key(earthquake)
        report_num = store.get_fusion_report_num(earthquake)
        if not event_key:
            return

        event_cache = store.cenc_wolfx_cache.setdefault(event_key, {})
        event_cache[report_num] = {"intensity": intensity, "created_at": time.time()}

        pending_key = store.find_best_pending_key(
            store.cenc_pending, event_key, report_num
        )
        if not pending_key:
            return

        try:
            item = store.cenc_pending.get(pending_key)
            if not isinstance(item, dict):
                return

            fan_event = item.get("event")
            future = item.get("future")
            fan_earthquake = self._get_earthquake_data(fan_event)
            if fan_event is None or fan_earthquake is None:
                return

            fan_earthquake.intensity = intensity
            logger.info(
                f"[灾害预警] 融合策略: 成功用 Wolfx 补充 Fan CENC 事件 {pending_key} 的烈度: {intensity}"
            )

            if future is not None and hasattr(future, "done") and not future.done():
                future.set_result("fused")

            store.cenc_pending.pop(pending_key, None)
        except Exception as e:
            logger.error(f"[灾害预警] CENC 融合操作失败: {e}")
