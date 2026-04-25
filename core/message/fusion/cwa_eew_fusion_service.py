"""
CWA EEW 融合策略服务。
负责处理 Fan CWA EEW 等待 Wolfx 影响区域补充与 Wolfx 到达后的缓存/唤醒流程。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from astrbot.api import logger

from ...domain.event_models import EarthquakeEvent, EventEnvelope
from ...domain.event_payload import SourcePayload


class CWAEewFusionService:
    """CWA EEW 融合策略服务。"""

    def __init__(self, manager, execute_push):
        # 通过管理器访问融合状态，并复用统一推送执行入口。
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

    @staticmethod
    def _ensure_source_payload(event: EventEnvelope) -> SourcePayload:
        """确保事件上挂载统一原始载荷对象。"""
        envelope = event
        payload = envelope.payload
        if isinstance(payload, SourcePayload):
            return payload
        source_payload = SourcePayload(
            source_id=envelope.source_id or "",
            raw=dict(payload) if isinstance(payload, dict) else {},
        )
        envelope.payload = source_payload
        return source_payload

    @classmethod
    def _apply_impact_area(
        cls,
        event: EventEnvelope,
        earthquake: EarthquakeEvent,
        impact_area: str,
    ) -> None:
        """把影响区域写回事件载荷与领域事件对象。"""
        source_payload = cls._ensure_source_payload(event)
        source_payload.raw["wolfx_impact_area"] = impact_area
        source_payload.attributes["impact_area"] = impact_area
        if not getattr(earthquake, "province", None):
            earthquake.province = impact_area

    async def intercept_fan_event(
        self,
        event: EventEnvelope,
        timeout: int,
        *,
        target_sessions: list[str] | None = None,
        session_config_getter=None,
    ) -> bool:
        """拦截 Fan CWA EEW 事件并等待 Wolfx 影响区域补充。"""
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
            store.cwa_eew_wolfx_cache.get(event_key, {}), report_num
        )
        if isinstance(cached_payload, dict) and cached_payload.get("impact_area"):
            impact_area = str(cached_payload["impact_area"]).strip()
            if impact_area:
                cls = type(self)
                cls._apply_impact_area(event, earthquake, impact_area)
                logger.info(
                    f"[灾害预警] 融合策略: Fan CWA EEW 事件 {event.id} 命中 Wolfx 缓存并补充影响区域: {impact_area}"
                )
                return await self._execute_push(
                    event,
                    target_sessions=target_sessions,
                    session_config_getter=session_config_getter,
                )

        logger.info(
            f"[灾害预警] 融合策略: 拦截 Fan CWA EEW 事件 {event.id} (event_key={event_key}, report={report_num})，等待 Wolfx 补充 ({timeout}s)..."
        )

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        pending_key = f"{event_key}#{report_num}#{event.id}#{int(time.time() * 1000)}"

        store.cwa_eew_pending[pending_key] = {
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
            store.cwa_eew_pending.pop(pending_key, None)

            if result == "timeout":
                logger.info("[灾害预警] 融合策略: CWA EEW 等待超时，推送原始 Fan 事件")
                return await self._execute_push(
                    event,
                    target_sessions=target_sessions,
                    session_config_getter=session_config_getter,
                )
            if result == "fused":
                logger.info(
                    "[灾害预警] 融合策略: CWA EEW 融合完成，推送补充后的 Fan 事件"
                )
                return await self._execute_push(
                    event,
                    target_sessions=target_sessions,
                    session_config_getter=session_config_getter,
                )
        except Exception as e:
            logger.error(f"[灾害预警] CWA EEW 融合策略处理异常: {e}")
            return await self._execute_push(
                event,
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        return False

    @staticmethod
    def _extract_wolfx_impact_area(
        payload_raw: dict[str, Any],
        fallback: Any = None,
    ) -> str | None:
        """从 Wolfx 载荷中尽量提取影响区域文本。"""
        candidates: list[Any] = []
        if fallback is not None:
            candidates.append(fallback)
        candidates.extend(
            [
                payload_raw.get("wolfx_impact_area"),
                payload_raw.get("locationDesc"),
                payload_raw.get("impactArea"),
                payload_raw.get("ImpactArea"),
                payload_raw.get("affectedArea"),
                payload_raw.get("AffectedArea"),
                payload_raw.get("area"),
                payload_raw.get("Area"),
            ]
        )

        warn_area = payload_raw.get("WarnArea")
        if isinstance(warn_area, dict):
            candidates.extend(
                [
                    warn_area.get("Chiiki"),
                    warn_area.get("Area"),
                    warn_area.get("AreaName"),
                    warn_area.get("Name"),
                    warn_area.get("County"),
                ]
            )
        elif warn_area is not None:
            candidates.append(warn_area)

        for candidate in candidates:
            if isinstance(candidate, list):
                parts = [str(item).strip() for item in candidate if str(item).strip()]
                if parts:
                    return "、".join(parts)
                continue
            if isinstance(candidate, str):
                normalized = candidate.strip()
                if normalized:
                    return normalized
                continue
            if candidate is not None:
                normalized = str(candidate).strip()
                if normalized:
                    return normalized
        return None

    def extract_wolfx_impact_area(
        self,
        wolfx_event: EventEnvelope,
        wolfx_earthquake: EarthquakeEvent,
    ) -> str | None:
        source_payload = type(self)._ensure_source_payload(wolfx_event)
        return type(self)._extract_wolfx_impact_area(
            source_payload.to_dict(),
            getattr(wolfx_earthquake, "province", None),
        )

    def handle_wolfx_event(self, wolfx_event: EventEnvelope):
        """处理 Wolfx 到达事件，并尝试唤醒等待中的 Fan CWA EEW 事件。"""
        earthquake = self._get_earthquake_data(wolfx_event)
        if earthquake is None:
            return

        impact_area = self.extract_wolfx_impact_area(wolfx_event, earthquake)
        if not impact_area:
            return

        store = self.manager._fusion_state_store
        store.prune()

        event_key = store.get_fusion_event_key(earthquake)
        report_num = store.get_fusion_report_num(earthquake)
        if not event_key:
            return

        event_cache = store.cwa_eew_wolfx_cache.setdefault(event_key, {})
        event_cache[report_num] = {
            "impact_area": impact_area,
            "created_at": time.time(),
        }

        pending_key = store.find_best_pending_key(
            store.cwa_eew_pending, event_key, report_num
        )
        if not pending_key:
            return

        try:
            item = store.cwa_eew_pending.get(pending_key)
            if not isinstance(item, dict):
                return

            fan_event = item.get("event")
            future = item.get("future")
            fan_earthquake = self._get_earthquake_data(fan_event)
            if fan_event is None or fan_earthquake is None:
                return

            type(self)._apply_impact_area(fan_event, fan_earthquake, impact_area)

            logger.info(
                f"[灾害预警] 融合策略: 成功用 Wolfx 补充 Fan CWA EEW 事件 {pending_key} 的影响区域: {impact_area}"
            )

            if future is not None and hasattr(future, "done") and not future.done():
                future.set_result("fused")

            store.cwa_eew_pending.pop(pending_key, None)
        except Exception as e:
            logger.error(f"[灾害预警] CWA EEW 融合操作失败: {e}")
