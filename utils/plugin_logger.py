from typing import Any

from astrbot.api import logger


class PluginLogger:
    """插件日志代理，用于控制事件流相关日志的分级、降级和屏蔽。"""

    def __init__(self) -> None:
        self._config: dict[str, Any] | None = None

    def set_config(self, config: dict[str, Any]) -> None:
        """注入最新的插件配置。"""
        self._config = config

    def _should_suppress_or_downgrade(self, is_event_linked: bool) -> tuple[bool, str]:
        """
        判断是否需要对当前日志进行处理。
        返回 (是否拦截/降级, 具体行为: "debug" | "mute" | "none")
        """
        if not is_event_linked or not self._config:
            return False, "none"

        # 使用 hasattr 安全判断以兼容 AstrBotConfig 的 get 访问方法
        if not hasattr(self._config, "get"):
            return False, "none"

        debug_config = self._config.get("debug_config", {})
        if not hasattr(debug_config, "get"):
            debug_config = {}

        log_mode = debug_config.get("log_mode", self._config.get("log_mode", "全量"))
        if log_mode != "简洁":
            return False, "none"

        # 简洁模式下，获取降级行为
        behavior = debug_config.get(
            "log_downgrade_behavior",
            self._config.get("log_downgrade_behavior", "降级为DEBUG"),
        )
        if behavior == "完全屏蔽":
            return True, "mute"
        return True, "debug"

    def info(
        self, msg: str, *args: Any, is_event_linked: bool = False, **kwargs: Any
    ) -> None:
        """记录 INFO 级别日志。"""
        should_process, action = self._should_suppress_or_downgrade(is_event_linked)
        if should_process:
            if action == "debug":
                logger.debug(msg, *args, **kwargs)
            # action == "mute" 则直接屏蔽，什么都不做
        else:
            logger.info(msg, *args, **kwargs)

    def warning(
        self, msg: str, *args: Any, is_event_linked: bool = False, **kwargs: Any
    ) -> None:
        """记录 WARNING 级别日志。"""
        should_process, action = self._should_suppress_or_downgrade(is_event_linked)
        if should_process:
            if action == "debug":
                logger.debug(msg, *args, **kwargs)
        else:
            logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """记录 ERROR 级别日志。错误日志由于其关键性，不受简洁模式限制。"""
        logger.error(msg, *args, **kwargs)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """记录 DEBUG 级别日志。"""
        logger.debug(msg, *args, **kwargs)


# 全局单例对象
plugin_logger = PluginLogger()
