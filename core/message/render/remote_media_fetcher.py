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
        # 抓取器通过注入回调访问网络会话与内容类型判定能力，保持自身轻量。
        self._session_getter = session_getter  # 网络 session 异步获取回调
        self._image_type_checker = image_type_checker  # 图片 MIME 类型合法性校验回调
        self._content_type_guesser = (
            content_type_guesser  # URL 扩展名后缀 MIME 类型猜测回调
        )

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
            session = await self._session_getter(
                timeout_seconds
            )  # 异步获取 ClientSession
            # 执行带有重定向跟踪的 HTTP GET 请求
            async with session.get(normalized_url, allow_redirects=True) as response:
                # 把最终跳转地址、状态码与响应头统一记录下来，便于上层诊断抓取失败原因。
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

                # 仅处理 HTTP 200 成功的请求
                if response.status != 200:
                    result["error"] = f"HTTP {response.status}"
                    return result

                body = await response.read()  # 读取全部响应字节体
                result["bytes"] = len(body)
                # 再次校验下载后的文件实际大小
                if len(body) > max_bytes:
                    result["error"] = (
                        f"下载体过大: {len(body)} bytes > {max_bytes} bytes"
                    )
                    return result

                content_type = result["content_type"] or self._content_type_guesser(
                    result["final_url"]
                )
                result["content_type"] = content_type
                # 如果要求为图片，则使用回调校验 content-type 是否合法
                if expected_kind == "image" and not self._image_type_checker(
                    content_type
                ):
                    result["error"] = f"响应类型不是图片: {content_type or 'unknown'}"
                    return result

                result["data"] = body  # 写入读取到的二进制数据
                return result
        except Exception as e:
            # 捕获连接超时、DNS 错误等全部异常，并将异常名和描述记录返回
            result["error"] = str(e)
            result["exception_type"] = type(e).__name__
            return result
