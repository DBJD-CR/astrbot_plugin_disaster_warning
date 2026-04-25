"""
事件接入分发服务。
负责根据 source 特征与策略配置决定事件应同步处理还是转后台任务分发，
从 SourceMessageRouter 中迁出运行时分发策略判断。
"""

from __future__ import annotations

import asyncio

from astrbot.api import logger

from ..sources.source_catalog import get_source_entry


class EventIngressDispatchService:
    """事件接入分发服务。"""

    def __init__(self, service):
        """保存灾害服务引用，供分发阶段访问配置与主处理链。"""
        self.service = service

    def should_dispatch_in_background(self, source_id: str) -> bool:
        """判断指定数据源是否应转为后台异步分发。"""
        entry = get_source_entry(source_id)
        if entry is None:
            return False
        if (entry.dispatch_family or "").strip() != "fan_studio_eew":
            return False
        if not entry.fusion_group:
            return False

        # 只有启用了对应融合策略的快报源，才值得改为后台执行，避免阻塞接入线程。
        message_manager = getattr(self.service, "message_manager", None)
        config = getattr(message_manager, "config", {}) if message_manager else {}
        strategies_cfg = (
            config.get("strategies", {}) if isinstance(config, dict) else {}
        )
        strategy_key_map = {
            "cenc_intensity": "cenc_fusion",
            "cwa_impact_area": "cwa_eew_fusion",
        }
        strategy_key = strategy_key_map.get(entry.fusion_group)
        if not strategy_key:
            return False
        strategy_config = strategies_cfg.get(strategy_key, {})
        return bool(
            isinstance(strategy_config, dict) and strategy_config.get("enabled", False)
        )

    async def dispatch_event(self, event, *, source_id: str, source_label: str) -> None:
        """按策略把事件直接送入主链或转为后台任务。"""
        if self.should_dispatch_in_background(source_id):

            async def _dispatch_event_non_blocking(disaster_event):
                # 后台任务只负责调用主事件处理链，并把异常留在日志中，不回抛到接入层。
                try:
                    await self.service._handle_disaster_event(disaster_event)
                except Exception as dispatch_err:
                    logger.error(
                        f"[灾害预警] {source_label} 异步分发失败: {dispatch_err}"
                    )

            task = asyncio.create_task(
                _dispatch_event_non_blocking(event),
                name=f"dw_{source_id}_dispatch_{event.id}",
            )
            if hasattr(self.service, "register_background_task"):
                self.service.register_background_task(task)
            return

        await self.service._handle_disaster_event(event)


__all__ = ["EventIngressDispatchService"]
