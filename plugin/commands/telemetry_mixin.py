"""
命令服务遥测混入模块。

为插件命令服务提供统一的匿名行为遥测上报适配。
避免各命令服务重复实现 plugin.telemetry 提取与 best-effort 上报逻辑。
"""

from __future__ import annotations

from typing import Any

from ...core.services.telemetry.telemetry_utils import track_feature_safely


class CommandTelemetryMixin:
    """命令服务匿名行为遥测混入。"""

    async def _track_command_feature(
        self,
        feature_name: str,
        extra: dict[str, Any] | None = None,
        *,
        log_context: str = "命令行为遥测",
    ) -> bool:
        """安全上报命令匿名行为事件。"""
        # 统一尝试在命令类实例中安全提取插件中的遥测对象
        telemetry = getattr(getattr(self, "plugin", None), "telemetry", None)
        return await track_feature_safely(
            telemetry,
            feature_name,
            extra,
            log_context=log_context,
        )


__all__ = ["CommandTelemetryMixin"]
