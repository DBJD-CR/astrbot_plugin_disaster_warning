"""
遥测管理器 (Telemetry Manager)

用于收集匿名的插件使用情况、配置快照和错误信息。

数据脱敏说明:
- 不收集任何用户个人信息（如群号、QQ号、IP地址等）
- 配置快照仅收集统计性数据（如启用的数据源数量）
- 错误信息仅包含错误类型和模块名，不包含堆栈中的敏感路径
"""

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


class TelemetryManager:
    """遥测管理器 - 异步发送匿名遥测数据"""

    _ENDPOINT = "https://telemetry.aloys233.top/api/ingest"
    _ENCODED_KEY = "dGtfVFMxaVEtcGVJbUlKczFVM3VBcGM4anREUlRhbC00VGY="
    _APP_KEY = base64.b64decode(_ENCODED_KEY).decode()

    def __init__(
        self,
        config: dict,
        plugin_version: str = "unknown",
    ):
        """
        初始化遥测管理器

        Args:
            config: 插件配置对象
            plugin_version: 插件版本号
        """
        self._config = config
        self._plugin_version = plugin_version

        # 从配置中读取遥测开关
        telemetry_config = config.get("telemetry_config", {})
        self._enabled = telemetry_config.get("enabled", False)

        # 获取或创建实例 ID（存储在插件数据目录中）
        self._instance_id = self._get_or_create_instance_id()

        # aiohttp session (延迟初始化)
        self._session: aiohttp.ClientSession | None = None

        self._env = "production"

        if self._enabled:
            logger.debug(
                f"[灾害预警] 已启用匿名遥测 (Instance ID: {self._instance_id})"
            )
        else:
            logger.debug("[灾害预警] 遥测功能未启用")

    def _get_or_create_instance_id(self) -> str:
        """获取或创建实例 ID，存储在插件数据目录中"""

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
        """是否启用遥测"""
        return self._enabled

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp session"""
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
        发送遥测事件

        Args:
            event_name: 事件名称 (snake_case)
            data: 自定义数据对象
        """
        if not self._enabled:
            return False

        # 构造符合新 API 的 payload
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
                    logger.debug(f"[灾害预警] 遥测事件 '{event_name}' 发送成功")
                    return True
                elif response.status == 401:
                    logger.warning("[灾害预警] App Key 无效或项目已禁用")
                elif response.status == 429:
                    logger.warning("[灾害预警] 遥测请求频率超限")
                else:
                    logger.debug(f"[灾害预警] 遥测事件发送失败: HTTP {response.status}")

        except asyncio.TimeoutError:
            logger.debug("[灾害预警] 遥测请求超时")
            return False
        except aiohttp.ClientError as e:
            logger.debug(f"[灾害预警] 遥测网络错误: {e}")
            return False
        except Exception as e:
            # 静默处理所有错误，不影响插件正常运行
            logger.debug(f"[灾害预警] 未知错误: {e}")
            return False

        return False

    async def track_startup(self) -> bool:
        """上报启动事件和系统信息"""
        return await self.track(
            "startup",
            {
                "os": platform.system(),
                "os_version": platform.release(),
                "python_version": platform.python_version(),
                "arch": platform.machine(),
            },
        )

    async def track_shutdown(
        self, exit_code: int = 0, runtime_seconds: float = 0
    ) -> bool:
        """上报退出事件"""
        return await self.track(
            "shutdown",
            {
                "exit_code": exit_code,
                "runtime_seconds": runtime_seconds,
            },
        )

    async def track_config(self, config: dict) -> bool:
        """
        上报配置快照
        收集除敏感信息外的所有配置项
        敏感信息过滤列表：
        - admin_users
        - target_sessions
        - local_monitoring.latitude
        - local_monitoring.longitude
        - local_monitoring.place_name
        """
        if not self._enabled:
            return False

        try:
            # 深拷贝配置，避免修改原对象
            config_copy = copy.deepcopy(config)

            # 移除顶层敏感字段
            if "admin_users" in config_copy:
                del config_copy["admin_users"]
            if "target_sessions" in config_copy:
                del config_copy["target_sessions"]

            # 移除本地监控敏感字段
            if "local_monitoring" in config_copy:
                lm = config_copy["local_monitoring"]
                if isinstance(lm, dict):
                    if "latitude" in lm:
                        del lm["latitude"]
                    if "longitude" in lm:
                        del lm["longitude"]
                    if "place_name" in lm:
                        del lm["place_name"]

            return await self.track("config", config_copy)

        except Exception as e:
            logger.debug(f"[灾害预警] 配置快照提取失败: {e}")
            return False

    async def track_feature(self, feature_name: str, extra: dict = None) -> bool:
        """上报功能使用事件"""
        data = extra.copy() if extra else {}
        # 强制设置 feature，防止被 extra 覆盖
        data["feature"] = feature_name
        return await self.track("feature", data)

    async def track_error(
        self,
        exception: Exception,
        module: str = None,
    ) -> bool:
        """
        上报错误事件

        Args:
            exception: 捕获的异常对象
            module: 发生错误的模块名
        """
        # 先脱敏再截断，防止截断导致脱敏正则匹配失败
        raw_message = str(exception)
        sanitized_message = self._sanitize_message(raw_message)

        data = {
            "type": type(exception).__name__,
            "message": sanitized_message[:500],
            "module": module,
            "severity": "error",
        }

        # 获取堆栈并脱敏
        stack = "".join(
            traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        )
        data["stack"] = self._sanitize_stack(stack)[:4000]

        return await self.track("error", data)

    def _sanitize_stack(self, stack: str) -> str:
        """
        脱敏堆栈信息，移除敏感路径

        - 移除用户主目录路径
        - 保留相对于插件的路径
        - 隐藏用户名
        """

        # 替换 Windows 风格的用户路径
        # C:\Users\username\... -> <USER_HOME>\...
        stack = re.sub(r"[A-Za-z]:\\Users\\[^\\]+\\", r"<USER_HOME>\\", stack)

        # 替换 Unix 风格的用户路径
        # /home/username/... -> <USER_HOME>/...
        # /Users/username/... -> <USER_HOME>/...
        stack = re.sub(r"/(?:home|Users)/[^/]+/", r"<USER_HOME>/", stack)

        # 简化插件路径，只保留相对路径
        # .../astrbot_plugin_disaster_warning/... -> <PLUGIN>/...
        stack = re.sub(r".*astrbot_plugin_disaster_warning[/\\]", r"<PLUGIN>/", stack)

        # 移除可能的 site-packages 完整路径
        stack = re.sub(r".*site-packages[/\\]", r"<SITE_PACKAGES>/", stack)

        return stack

    def _sanitize_message(self, message: str) -> str:
        """脱敏错误消息，移除可能的敏感信息"""

        # 移除路径中的用户名
        message = re.sub(r"/(?:home|Users)/[^/\s]+/", r"<USER_HOME>/", message)
        message = re.sub(r"[A-Za-z]:\\Users\\[^\\\s]+\\", r"<USER_HOME>\\", message)

        return message

    async def close(self):
        """关闭遥测会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.debug("[灾害预警] 遥测会话已关闭")
