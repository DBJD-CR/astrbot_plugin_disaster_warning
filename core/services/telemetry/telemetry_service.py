"""
遥测服务主入口。
承载匿名遥测事件发送、配置快照上报与错误脱敏上报能力。

数据脱敏说明:
- 不收集任何用户个人信息（如群号、QQ号、IP地址等）
- 配置快照仅收集统计性数据（如启用的数据源数量）
- 错误信息仅包含错误类型和模块名，不包含堆栈中的敏感路径
"""

from __future__ import annotations

import asyncio
import base64
import copy
import platform
import re
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

import aiohttp

from astrbot.api import logger
from astrbot.api.star import StarTools

from ....utils.version import get_astrbot_version


class TelemetryManager:
    """遥测管理器。

    负责异步发送匿名遥测数据，并集中管理实例标识、脱敏与上报策略。
    """

    _ENDPOINT = "https://telemetry.aloys233.top/api/ingest"
    _ENCODED_KEY = "dGtfVFMxaVEtcGVJbUlKczFVM3VBcGM4anREUlRhbC00VGY="
    _APP_KEY = base64.b64decode(_ENCODED_KEY).decode()

    def __init__(
        self,
        config: dict,
        plugin_version: str = "unknown",
    ):
        """
        初始化遥测管理器。

        参数说明：
        - config: 插件配置对象
        - plugin_version: 插件版本号
        """
        self._config = config
        self._plugin_version = plugin_version

        # 获取 AstrBot 版本号
        self._astrbot_version = get_astrbot_version()

        # 从配置中读取遥测开关
        telemetry_config = config.get("telemetry_config", {})
        self._enabled = telemetry_config.get("enabled", True)

        # 获取或创建实例 ID（存储在插件数据目录中）
        self._instance_id = self._get_or_create_instance_id()

        # aiohttp session (延迟初始化)
        self._session: aiohttp.ClientSession | None = None

        self._env = "production"

        if self._enabled:
            logger.debug(
                f"[灾害预警] 已启用匿名遥测，实例标识为 {self._instance_id}，AstrBot 版本为 {self._astrbot_version}"
            )
        else:
            logger.debug("[灾害预警] 遥测功能未启用")

    def _get_or_create_instance_id(self) -> str:
        """获取或创建实例标识，并持久化到插件数据目录。"""

        try:
            # 使用 StarTools 获取插件数据目录（与 message_logger 一致）
            data_dir = StarTools.get_data_dir("astrbot_plugin_disaster_warning")
            id_file = data_dir / ".telemetry_id"

            # 尝试读取已存在的 ID
            if id_file.exists():
                instance_id = id_file.read_text().strip()
                if instance_id:
                    return instance_id

            # 生成新的 UUID
            instance_id = str(uuid.uuid4())

            # 保存到文件
            data_dir.mkdir(parents=True, exist_ok=True)
            id_file.write_text(instance_id)
            logger.debug(f"[灾害预警] 已生成新的实例 ID: {instance_id}")

            return instance_id

        except Exception as e:
            # 如果无法读写文件，生成临时 ID
            logger.warning(f"[灾害预警] 无法持久化实例 ID: {e}")
            return str(uuid.uuid4())

    @property
    def enabled(self) -> bool:
        """返回当前是否启用遥测。"""
        return self._enabled

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建内部网络会话。"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def track(
        self,
        event_name: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """
        发送遥测事件。

        参数说明：
        - event_name: 事件名称
        - data: 附加数据对象
        """
        if not self._enabled:
            return False

        payload = {
            "instance_id": self._instance_id,
            "version": self._plugin_version,
            "env": self._env,
            "batch": [
                {
                    "event": event_name,
                    "data": data or {},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }

        try:
            session = await self._get_session()
            headers = {
                "Content-Type": "application/json",
                "X-App-Key": self._APP_KEY,
            }

            async with session.post(
                self._ENDPOINT, json=payload, headers=headers
            ) as response:
                if response.status == 200:
                    return True
                if response.status == 401:
                    logger.warning("[灾害预警] App Key 无效或项目已禁用")
                elif response.status == 429:
                    logger.warning("[灾害预警] 遥测请求频率超限")
                else:
                    logger.debug(f"[灾害预警] 遥测事件发送失败: HTTP {response.status}")

        except asyncio.TimeoutError:
            logger.debug("[灾害预警] 遥测请求超时")
            return False
        except aiohttp.ClientConnectionError as e:
            logger.debug(f"[灾害预警] 遥测连接失败: {e}")
            return False
        except aiohttp.ClientPayloadError as e:
            logger.debug(f"[灾害预警] 遥测数据负载异常，错误为 {e}")
            return False
        except aiohttp.ClientError as e:
            logger.debug(f"[灾害预警] 遥测网络请求异常，错误为 {e}")
            return False
        except Exception as e:
            logger.debug(f"[灾害预警] 遥测发送遇到未知异常，错误为 {e}")
            return False

        return False

    async def track_startup(self) -> bool:
        """上报启动事件和系统信息。"""
        return await self.track(
            "startup",
            {
                "os": platform.system(),
                "os_version": platform.release(),
                "python_version": platform.python_version(),
                "arch": platform.machine(),
                "astrbot_version": self._astrbot_version,
            },
        )

    async def track_shutdown(
        self, exit_code: int = 0, runtime_seconds: float = 0
    ) -> bool:
        """上报退出事件。"""
        return await self.track(
            "shutdown",
            {
                "exit_code": exit_code,
                "runtime_seconds": runtime_seconds,
            },
        )

    async def track_heartbeat(self, uptime_seconds: float = 0) -> bool:
        """上报心跳事件。

        参数 `uptime_seconds` 表示当前累计运行秒数。
        """
        return await self.track(
            "heartbeat",
            {
                "uptime_seconds": uptime_seconds,
            },
        )

    async def track_config(self, config: dict) -> bool:
        """
        上报配置快照。

        会过滤管理员、目标会话、地理位置与管理端密码等敏感字段。
        """
        if not self._enabled:
            return False

        try:
            config_copy = copy.deepcopy(config)

            if "admin_users" in config_copy:
                del config_copy["admin_users"]
            if "target_sessions" in config_copy:
                del config_copy["target_sessions"]

            if "local_monitoring" in config_copy:
                lm = config_copy["local_monitoring"]
                if isinstance(lm, dict):
                    if "latitude" in lm:
                        del lm["latitude"]
                    if "longitude" in lm:
                        del lm["longitude"]
                    if "place_name" in lm:
                        del lm["place_name"]

            if "web_admin" in config_copy:
                wa = config_copy["web_admin"]
                if isinstance(wa, dict) and "password" in wa:
                    del wa["password"]

            return await self.track("config", config_copy)

        except Exception as e:
            logger.debug(f"[灾害预警] 配置快照提取失败: {e}")
            return False

    async def track_feature(self, feature_name: str, extra: dict | None = None) -> bool:
        """上报功能使用事件。"""
        data = extra.copy() if extra else {}
        data["feature"] = feature_name
        return await self.track("feature", data)

    async def track_error(
        self,
        exception: Exception,
        module: str | None = None,
    ) -> bool:
        """
        上报错误事件。

        参数说明：
        - exception: 捕获到的异常对象
        - module: 发生错误的模块名
        """
        raw_message = str(exception)
        if self._should_skip_error_telemetry(exception, raw_message, module):
            logger.debug(
                "[灾害预警] 命中遥测噪声过滤规则，跳过错误上报："
                f"异常类型为 {type(exception).__name__}，模块为 {module}，消息摘要：{raw_message[:200]}"
            )
            return False

        sanitized_message = self._sanitize_message(raw_message)

        data = {
            "type": type(exception).__name__,
            "message": sanitized_message[:500],
            "module": module,
            "severity": "error",
        }

        stack = "".join(
            traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        )
        data["stack"] = self._sanitize_stack(stack)[:4000]

        return await self.track("error", data)

    def _should_skip_error_telemetry(
        self,
        exception: Exception,
        raw_message: str,
        module: str | None = None,
    ) -> bool:
        """判断是否应跳过高频低价值错误的遥测上报。"""
        error_type = type(exception).__name__
        message = (raw_message or "").lower()
        module_name = (module or "").lower()

        if error_type == "TargetClosedError":
            return True
        if "target page, context or browser has been closed" in message:
            return True

        if (
            "executable doesn't exist" in message
            or "playwright install" in message
            or "ms-playwright" in message
        ):
            return True

        if "websocket异常关闭" in message and "1006" in message:
            return True
        if (
            module_name.startswith("core.websocket_manager.connect")
            and "1006" in message
        ):
            return True

        return False

    def _sanitize_stack(self, stack: str) -> str:
        """
        脱敏堆栈信息，移除敏感路径

        - 移除用户主目录路径
        - 保留相对于插件的路径
        - 隐藏用户名
        """
        stack = re.sub(r"[A-Za-z]:\\Users\\[^\\]+\\", r"<USER_HOME>\\", stack)
        stack = re.sub(r"/(?:home|Users|root)/[^/]+/", r"<USER_HOME>/", stack)
        stack = re.sub(r"/root/", r"<USER_HOME>/", stack)
        stack = re.sub(r".*astrbot_plugin_disaster_warning[/\\]", r"<PLUGIN>/", stack)
        stack = re.sub(r".*site-packages[/\\]", r"<SITE_PACKAGES>/", stack)
        return stack

    def _sanitize_message(self, message: str) -> str:
        """脱敏错误消息，移除可能的敏感信息。"""
        message = re.sub(r"/(?:home|Users|root)/[^/\s]+/", r"<USER_HOME>/", message)
        message = re.sub(r"/root/", r"<USER_HOME>/", message)
        message = re.sub(r"[A-Za-z]:\\Users\\[^\\\s]+\\", r"<USER_HOME>\\", message)
        return message

    async def close(self):
        """关闭遥测会话。"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.debug("[灾害预警] 遥测会话已关闭")


__all__ = ["TelemetryManager"]
