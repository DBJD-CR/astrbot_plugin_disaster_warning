"""
远程媒体会话与 MIME 支撑服务。
"""

from __future__ import annotations

import mimetypes

import aiohttp
from aiohttp import ClientSession

from astrbot.api import logger


class MessageRemoteMediaService:
    """远程媒体会话与 MIME 支撑服务。"""

    def __init__(self, manager):
        # 该服务专门负责远程媒体抓取会话的复用与内容类型辅助判断。
        self.manager = manager

    async def get_session(self, timeout_seconds: int | None = None) -> ClientSession:
        """获取可复用的远程媒体抓取 Session。"""
        session_timeout_seconds = (
            timeout_seconds
            if isinstance(timeout_seconds, (int, float)) and timeout_seconds > 0
            else self.manager._remote_media_session_timeout_seconds
        )

        if (
            self.manager._remote_media_session
            and not self.manager._remote_media_session.closed
        ):
            current_timeout = getattr(
                self.manager._remote_media_session.timeout,
                "total",
                session_timeout_seconds,
            )
            # 仅当超时配置一致时复用旧 session；否则重建，避免旧超时参数继续泄漏到新请求。
            if current_timeout == session_timeout_seconds:
                return self.manager._remote_media_session

            try:
                await self.manager._remote_media_session.close()
            except Exception as e:
                logger.debug(f"[灾害预警] 关闭旧远程媒体 Session 失败: {e}")
            finally:
                self.manager._remote_media_session = None

        timeout = aiohttp.ClientTimeout(total=session_timeout_seconds)
        # 统一伪装常见浏览器请求头，提升部分远程图片服务的兼容性。
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
        }
        self.manager._remote_media_session = aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
        )
        return self.manager._remote_media_session

    async def close_session(self) -> None:
        """关闭远程媒体抓取 Session。"""
        if (
            self.manager._remote_media_session
            and not self.manager._remote_media_session.closed
        ):
            await self.manager._remote_media_session.close()
        self.manager._remote_media_session = None

    @staticmethod
    def is_image_content_type(content_type: str | None) -> bool:
        """判断响应 Content-Type 是否为图片。"""
        if not isinstance(content_type, str):
            return False
        mime = content_type.split(";", 1)[0].strip().lower()
        return mime.startswith("image/")

    @staticmethod
    def guess_image_content_type(url: str) -> str | None:
        """根据 URL 后缀猜测图片 MIME。"""
        guessed_type, _ = mimetypes.guess_type(url)
        if isinstance(guessed_type, str) and guessed_type.startswith("image/"):
            return guessed_type
        return None
