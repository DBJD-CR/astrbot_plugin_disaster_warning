"""
CENC 融合策略服务。
负责处理 Fan CENC 等待 Wolfx 烈度补充与 Wolfx 到达后的缓存/唤醒流程。
"""

from __future__ import annotations

import asyncio
import time

from astrbot.api import logger

from ....models.models import DisasterEvent, EarthquakeData


class CENCFusionService:
    """CENC 融合策略服务。"""

    def __init__(self, manager, execute_push):
        self.manager = manager
        self._execute_push = execute_push

    async def intercept_fan_event(
        self,
        event: DisasterEvent,
        timeout: int,
        *,
        target_sessions: list[str] | None = None,
        session_config_getter=None,
    ) -> bool:
        if not isinstance(event.data, EarthquakeData):
            return await self._execute_push(
                event,
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        # 进入拦截流程前先清理过期 pending / cache，避免旧融合状态干扰当前报次。
        self.manager._prune_fusion_states()
        store = self.manager._fusion_state_store

        event_key = self.manager._get_fusion_event_key(event.data)
        report_num = self.manager._get_fusion_report_num(event.data)
        cached_payload = self.manager._select_cached_report_payload(
            store.cenc_wolfx_cache.get(event_key, {}), report_num
        )
        # 若 Wolfx 补充信息已先到，则直接命中缓存完成“即时融合”，无需再等待。
        if (
            isinstance(cached_payload, dict)
            and cached_payload.get("intensity") is not None
        ):
            event.data.intensity = cached_payload["intensity"]
            logger.info(
                f"[灾害预警] 融合策略: Fan CENC 事件 {event.id} 命中 Wolfx 缓存并补充烈度: {event.data.intensity}"
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
        # pending_key 中混入 event_id 与时间戳，避免同 event_key / report 下多次拦截时相互覆盖。
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

    def handle_wolfx_event(self, wolfx_event: DisasterEvent):
        if not isinstance(wolfx_event.data, EarthquakeData):
            return

        intensity = getattr(wolfx_event.data, "intensity", None)
        if intensity is None:
            return

        self.manager._prune_fusion_states()
        store = self.manager._fusion_state_store

        event_key = self.manager._get_fusion_event_key(wolfx_event.data)
        report_num = self.manager._get_fusion_report_num(wolfx_event.data)
        if not event_key:
            return

        event_cache = store.cenc_wolfx_cache.setdefault(event_key, {})
        # Wolfx 数据无论是否命中等待中的 Fan 事件，都先入缓存，供稍后到达的 Fan 事件直接复用。
        event_cache[report_num] = {"intensity": intensity, "created_at": time.time()}

        pending_key = self.manager._find_best_pending_key(
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
            if not isinstance(fan_event, DisasterEvent) or not isinstance(
                fan_event.data, EarthquakeData
            ):
                return

            fan_event.data.intensity = intensity
            logger.info(
                f"[灾害预警] 融合策略: 成功用 Wolfx 补充 Fan CENC 事件 {pending_key} 的烈度: {intensity}"
            )

            if future is not None and hasattr(future, "done") and not future.done():
                future.set_result("fused")

            store.cenc_pending.pop(pending_key, None)
        except Exception as e:
            logger.error(f"[灾害预警] CENC 融合操作失败: {e}")
