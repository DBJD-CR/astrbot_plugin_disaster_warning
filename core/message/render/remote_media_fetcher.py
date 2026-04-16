"""
远程媒体抓取器。
负责抓取远程图片并返回结构化结果，减少 MessagePushManager 中的媒体获取职责。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class RemoteMediaFetcher:
    """远程媒体抓取器。"""

    def __init__(
        self,
        *,
        session_getter: Callable[[int | float | None], Awaitable[Any]],
        image_type_checker: Callable[[str | None], bool],
        content_type_guesser: Callable[[str | None], str | None],
    ):
        self._session_getter = session_getter
        self._image_type_checker = image_type_checker
        self._content_type_guesser = content_type_guesser

    async def fetch(
        self,
        url: str,
        *,
        timeout_seconds: int | float | None = None,
        max_bytes: int = 10 * 1024 * 1024,
        expected_kind: str = "image",
    ) -> dict[str, Any]:
        """抓取远程媒体并返回结构化结果。"""
        normalized_url = url.strip()
        result: dict[str, Any] = {
            # 返回统一结构，便于上层日志与回退逻辑直接复用，无需感知 aiohttp 细节。
            "source_url": normalized_url,
            "final_url": normalized_url,
            "status": None,
            "content_type": None,
            "content_length": None,
            "bytes": None,
            "error": None,
            "exception_type": None,
        }

        try:
            session = await self._session_getter(timeout_seconds)
            async with session.get(normalized_url, allow_redirects=True) as response:
                result["status"] = response.status
                result["final_url"] = str(response.url)
                result["content_type"] = response.headers.get("Content-Type")
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    result["content_length"] = int(content_length)
                    # 若服务端已声明体积超限，则直接提前返回，避免无意义下载。
                    if result["content_length"] > max_bytes:
                        result["error"] = (
                            f"响应体过大: {result['content_length']} bytes > {max_bytes} bytes"
                        )
                        return result

                if response.status != 200:
                    result["error"] = f"HTTP {response.status}"
                    return result

                body = await response.read()
                result["bytes"] = len(body)
                if len(body) > max_bytes:
                    result["error"] = (
                        f"下载体过大: {len(body)} bytes > {max_bytes} bytes"
                    )
                    return result

                content_type = result["content_type"] or self._content_type_guesser(
                    result["final_url"]
                )
                result["content_type"] = content_type
                if expected_kind == "image" and not self._image_type_checker(
                    content_type
                ):
                    result["error"] = f"响应类型不是图片: {content_type or 'unknown'}"
                    return result

                result["data"] = body
                return result
        except Exception as e:
            result["error"] = str(e)
            result["exception_type"] = type(e).__name__
            return result
