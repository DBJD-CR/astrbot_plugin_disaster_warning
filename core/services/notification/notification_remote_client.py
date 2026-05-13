"""远端通知客户端。"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ....utils.version import get_plugin_version


class NotificationRemoteClient:
    """负责构造远端通知接口请求并拉取原始通知数据。"""

    NOTIFICATION_BASE_URL = "https://pluginpush.aloys23.link"
    NOTIFICATION_APP_SLUG = "17bdeac6-bd59-461d-a436-2072f862b031"

    def __init__(self, plugin_version_getter=None):
        self._plugin_version_getter = plugin_version_getter

    def _get_plugin_version(self) -> str:
        """获取用于通知平台版本过滤的插件版本号。"""
        if self._plugin_version_getter:
            version = self._plugin_version_getter()
        else:
            version = get_plugin_version()
        normalized = str(version or "0.0.0").strip().lstrip("vV")
        return normalized if normalized and normalized != "unknown" else "0.0.0"

    def build_remote_url(self) -> str:
        """构造远端通知更新接口地址。"""
        base_url = self.NOTIFICATION_BASE_URL.strip().rstrip("/")
        app_slug = self.NOTIFICATION_APP_SLUG.strip().strip("/")
        if not base_url or not app_slug:
            return ""
        query = urlencode({"plugin_version": self._get_plugin_version()})
        return f"{base_url}/api/v1/{app_slug}/notifications/updates?{query}"

    async def fetch(self) -> list[dict[str, Any]]:
        """拉取远端原始通知数组。"""
        url = self.build_remote_url()
        if not url:
            return []

        def _request() -> list[dict[str, Any]]:
            request = Request(
                url,
                method="GET",
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/133.0.0.0 Safari/537.36"
                    ),
                },
            )
            with urlopen(request, timeout=10) as response:
                body = response.read().decode("utf-8")
            payload = json.loads(body)
            if not isinstance(payload, list):
                raise ValueError("通知接口返回体不是数组")
            return payload

        try:
            return await asyncio.to_thread(_request)
        except HTTPError as e:
            raise RuntimeError(f"通知接口请求失败，HTTP {e.code}") from e
        except URLError as e:
            raise RuntimeError(f"通知接口连接失败: {e.reason}") from e
        except TimeoutError as e:
            raise RuntimeError("通知接口请求超时") from e
