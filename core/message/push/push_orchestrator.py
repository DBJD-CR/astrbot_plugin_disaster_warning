"""
消息推送编排器。
负责根据事件来源与策略配置决定进入哪条推送路径，
将 MessagePushManager 中的入口编排逻辑外提，减少主管理器职责。
"""

from __future__ import annotations

from ....models.models import DisasterEvent
from ...support.config_accessor import ConfigAccessor
from ...support.event_metadata import resolve_source_id


class PushOrchestrator:
    """消息推送编排器。"""

    def __init__(
        self,
        config: dict,
        execute_push,
        cenc_fusion_service,
        cwa_eew_fusion_service,
    ):
        self.config = config
        self._config_accessor = ConfigAccessor(config)
        self._execute_push = execute_push
        self._cenc_fusion_service = cenc_fusion_service
        self._cwa_eew_fusion_service = cwa_eew_fusion_service

    async def push_event(
        self,
        event: DisasterEvent,
        target_sessions: list[str] | None = None,
        session_config_getter=None,
    ) -> bool:
        """根据策略配置编排事件推送流程。"""
        # 统一先解析标准化 source_id，避免上层分支依赖原始 source 枚举/字符串细节。
        source_id = resolve_source_id(event)
        strategies_cfg = self._config_accessor.strategies_config()

        # 两套融合策略配置彼此独立：CENC 解决烈度补充，CWA EEW 解决影响区域补充。
        cenc_fusion_config = strategies_cfg.get("cenc_fusion", {})
        cenc_fusion_enabled = cenc_fusion_config.get("enabled", False)

        cwa_eew_fusion_config = strategies_cfg.get("cwa_eew_fusion", {})
        cwa_eew_fusion_enabled = cwa_eew_fusion_config.get("enabled", False)

        # Fan 侧事件需要“拦截等待”Wolfx 补全，所以进入 intercept 分支。
        if cenc_fusion_enabled and source_id == "cenc_fanstudio":
            return await self._cenc_fusion_service.intercept_fan_event(
                event,
                cenc_fusion_config.get("timeout", 10),
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        # Wolfx 侧事件本身通常不直接推送，而是作为补充数据源写入缓存并唤醒等待中的 Fan 事件。
        if cenc_fusion_enabled and source_id == "cenc_wolfx":
            self._cenc_fusion_service.handle_wolfx_event(event)
            return False

        if cwa_eew_fusion_enabled and source_id == "cwa_fanstudio":
            return await self._cwa_eew_fusion_service.intercept_fan_event(
                event,
                cwa_eew_fusion_config.get("timeout", 6),
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        if cwa_eew_fusion_enabled and source_id == "cwa_wolfx":
            self._cwa_eew_fusion_service.handle_wolfx_event(event)
            return False

        # 未命中任何融合策略时，直接进入标准推送执行路径。
        return await self._execute_push(
            event,
            target_sessions=target_sessions,
            session_config_getter=session_config_getter,
        )
