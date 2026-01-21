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
import os
import platform
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

import aiohttp

from astrbot.api import logger


class TelemetryManager:
    """遥测管理器 - 异步发送匿名遥测数据"""

    _ENDPOINT = "https://telemetry.aloys233.top/api/ingest"
    _ENCODED_KEY = "dGtfOV91RFNfNy1LRkdfc1pSQ2JtRGJLWDZfb1lBd1Z5MHI="
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
        self._session: Optional[aiohttp.ClientSession] = None

        # 环境信息 (只收集一次)
        self._env_info = {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "os": platform.system().lower(),
            "arch": platform.machine(),
        }

        if self._enabled:
            logger.info(
                f"[遥测] 已启用匿名遥测 (Instance ID: {self._instance_id})"
            )
        else:
            logger.debug("[遥测] 遥测功能未启用")

    def _get_or_create_instance_id(self) -> str:
        """获取或创建实例 ID，存储在插件数据目录中"""
        from astrbot.api.star import StarTools
        
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
            logger.debug(f"[遥测] 已生成新的实例 ID: {instance_id}")

            return instance_id

        except Exception as e:
            # 如果无法读写文件，生成临时 ID
            logger.warning(f"[遥测] 无法持久化实例 ID: {e}")
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
        event: str,
        data: Optional[dict[str, Any]] = None,
        env: str = "production",
    ) -> bool:
        """
        发送遥测事件

        Args:
            event: 事件名称 (snake_case)
            data: 自定义数据对象 (第一层 key 用于聚合分析)
            env: 环境标识 (production/development/staging)

        Returns:
            是否发送成功
        """
        if not self._enabled:
            return False

        from datetime import datetime, timezone
        
        # 构造符合 API v2 的批量格式
        event_item = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        
        payload = {
            "instance_id": self._instance_id,
            "version": self._plugin_version,
            "env": env,
            "batch": [event_item],
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
                    logger.debug(f"[遥测] 事件 '{event}' 发送成功")
                    return True
                elif response.status == 401:
                    logger.warning("[遥测] App Key 无效或项目已禁用")
                elif response.status == 429:
                    logger.warning("[遥测] 请求频率超限")
                else:
                    logger.debug(f"[遥测] 事件发送失败: HTTP {response.status}")

        except asyncio.TimeoutError:
            logger.debug("[遥测] 请求超时")
        except aiohttp.ClientError as e:
            logger.debug(f"[遥测] 网络错误: {e}")
        except Exception as e:
            # 静默处理所有错误，不影响插件正常运行
            logger.debug(f"[遥测] 未知错误: {e}")

        return False

    async def track_system_info(self) -> bool:
        """发送系统环境信息"""
        return await self.track(
            "system_info",
            {
                **self._env_info,
                "plugin_version": self._plugin_version,
            },
        )

    async def track_config_snapshot(self, config: dict) -> bool:
        """
        发送配置快照 (脱敏后)

        只收集统计性数据，不包含任何敏感信息
        """
        if not self._enabled:
            return False

        # 提取脱敏的配置摘要
        try:
            data_sources = config.get("data_sources", {})
            local_monitoring = config.get("local_monitoring", {})
            filters = config.get("earthquake_filters", {})
            weather = config.get("weather_config", {})

            # 统计启用的数据源数量
            enabled_sources_count = 0
            for service_name, service_config in data_sources.items():
                if isinstance(service_config, dict) and service_config.get(
                    "enabled", False
                ):
                    # 计算该服务下启用的子项数量
                    for key, value in service_config.items():
                        if key != "enabled" and value is True:
                            enabled_sources_count += 1

            snapshot = {
                # 数据源统计
                "sources_enabled": enabled_sources_count,
                "fan_studio_enabled": data_sources.get("fan_studio", {}).get(
                    "enabled", False
                ),
                "p2p_enabled": data_sources.get("p2p_earthquake", {}).get(
                    "enabled", False
                ),
                "wolfx_enabled": data_sources.get("wolfx", {}).get("enabled", False),
                "global_quake_enabled": data_sources.get("global_quake", {}).get(
                    "enabled", False
                ),
                # 本地监控
                "local_monitoring_enabled": local_monitoring.get("enabled", False),
                "local_strict_mode": local_monitoring.get("strict_mode", False),
                # 过滤器
                "intensity_filter_enabled": filters.get("intensity_filter", {}).get(
                    "enabled", False
                ),
                "scale_filter_enabled": filters.get("scale_filter", {}).get(
                    "enabled", False
                ),
                # 气象
                "weather_filter_enabled": weather.get("weather_filter", {}).get(
                    "enabled", False
                ),
            }

            return await self.track("config_stats", snapshot)

        except Exception as e:
            logger.debug(f"[遥测] 配置快照提取失败: {e}")
            return False


    async def track_error(
        self,
        error_type: str,
        module: str,
        message: Optional[str] = None,
        stack: Optional[str] = None,
    ) -> bool:
        """
        发送错误事件

        Args:
            error_type: 错误类型 (如 ConnectionError, ValueError)
            module: 发生错误的模块名
            message: 错误简述 (可选)
            stack: 完整堆栈跟踪 (可选)
        """
        data = {
            "type": error_type,
            "module": module,
        }

        if message:
            data["message"] = self._sanitize_message(message)[:500]

        if stack:
            # 脱敏并限制堆栈长度
            data["stack"] = self._sanitize_stack(stack)[:4000]

        return await self.track("exception", data)

    def _sanitize_stack(self, stack: str) -> str:
        """
        脱敏堆栈信息，移除敏感路径
        
        - 移除用户主目录路径
        - 保留相对于插件的路径
        - 隐藏用户名
        """
        import re
        
        # 替换 Windows 风格的用户路径
        # C:\Users\username\... -> <USER_HOME>\...
        stack = re.sub(
            r'[A-Za-z]:\\Users\\[^\\]+\\',
            r'<USER_HOME>\\',
            stack
        )
        
        # 替换 Unix 风格的用户路径
        # /home/username/... -> <USER_HOME>/...
        # /Users/username/... -> <USER_HOME>/...
        stack = re.sub(
            r'/(?:home|Users)/[^/]+/',
            r'<USER_HOME>/',
            stack
        )
        
        # 简化插件路径，只保留相对路径
        # .../astrbot_plugin_disaster_warning/... -> <PLUGIN>/...
        stack = re.sub(
            r'.*astrbot_plugin_disaster_warning[/\\]',
            r'<PLUGIN>/',
            stack
        )
        
        # 移除可能的 site-packages 完整路径
        stack = re.sub(
            r'.*site-packages[/\\]',
            r'<SITE_PACKAGES>/',
            stack
        )
        
        return stack

    def _sanitize_message(self, message: str) -> str:
        """脱敏错误消息，移除可能的敏感信息"""
        import re
        
        # 移除路径中的用户名
        message = re.sub(
            r'/(?:home|Users)/[^/\s]+/',
            r'<USER_HOME>/',
            message
        )
        message = re.sub(
            r'[A-Za-z]:\\Users\\[^\\\s]+\\',
            r'<USER_HOME>\\',
            message
        )
        
        return message

    async def close(self):
        """关闭遥测会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.debug("[遥测] 会话已关闭")
