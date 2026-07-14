"""
EQSC 台风 HTTP 客户端。

负责向 EQSC API 发送台风数据查询请求，并维护简单的内存缓存以减少重复请求。
成功拉取的 HTTP 响应会同步写入原始消息日志（若已启用），便于排障回溯。
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlencode

import aiohttp

from astrbot.api import logger

from .eqsc_token_manager import EqscTokenManager


class EqscTyphoonClient:
    """EQSC 台风数据 HTTP 客户端。"""

    def __init__(
        self,
        token_manager: EqscTokenManager,
        config: dict[str, Any],
        message_logger: Any | None = None,
    ):
        """初始化台风客户端。

        Args:
            token_manager: EQSC 令牌管理器实例。
            config: EQSC 配置字典，包含 cache_ttl 等字段。
            message_logger: 可选原始消息记录器；启用后会落盘 EQSC HTTP 响应。
        """
        self._token_manager = token_manager
        self._base_url = str(config.get("base_url", "")).strip().rstrip("/")
        self._message_logger = message_logger
        # 缓存结构: {typhoon_id: (data, expires_at)}
        self._cache: dict[str, tuple[dict[str, Any], float]] = {}
        # 无参查询缓存（全部最新台风列表）
        self._list_cache: tuple[list[dict[str, Any]], float] | None = None
        # 缓存 TTL（秒），默认 5 分钟，与 EQSC 更新频率一致
        self._cache_ttl = int(config.get("cache_ttl", 300))
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """确保 aiohttp 会话可用。"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(
                total=25,
                connect=8,
                sock_connect=8,
                sock_read=15,
            )
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """关闭会话。"""
        if self._session and not self._session.closed:
            await self._session.close()
        await self._token_manager.close()

    def _is_cache_valid(self, expires_at: float) -> bool:
        """检查缓存是否仍然有效。"""
        return time.time() < expires_at

    def clear_cache(self) -> None:
        """清除所有缓存。"""
        self._cache.clear()
        self._list_cache = None

    @staticmethod
    def _mask_token(token: str | None) -> str:
        """脱敏 token，便于 401 排障。"""
        value = str(token or "").strip()
        if not value:
            return "<empty>"
        if len(value) <= 10:
            return value[:2] + "***"
        return f"{value[:6]}...{value[-4:]}(len={len(value)})"

    def _build_request_url(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """拼接带查询参数的完整请求 URL，供原始日志展示。"""
        if not params:
            return url
        query = urlencode(
            {str(key): str(value) for key, value in params.items() if value is not None}
        )
        if not query:
            return url
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{query}"

    def _log_http_response(
        self,
        *,
        url: str,
        params: dict[str, Any] | None,
        status_code: int | None,
        response_data: Any,
    ) -> None:
        """将 EQSC HTTP 响应写入原始消息日志（若记录器已启用）。

        优先使用带 source 标识的 log_raw_message，便于在原始日志中区分 EQSC；
        若记录器仅提供旧版 log_http_response，则回退兼容。
        """
        if not self._message_logger:
            return
        try:
            log_url = self._build_request_url(url, params)
            connection_info = {
                "url": log_url,
                "status_code": status_code,
                "connection_type": "http",
                "provider": "eqsc",
            }
            # 使用独立 source，方便在 raw_messages.log 中筛选 EQSC 报文
            if hasattr(self._message_logger, "log_raw_message"):
                self._message_logger.log_raw_message(
                    source="http_eqsc",
                    message_type="http_response",
                    payload_data=response_data,
                    connection_info=connection_info,
                )
            else:
                self._message_logger.log_http_response(
                    url=log_url,
                    response_data=response_data,
                    status_code=status_code,
                )
        except Exception as e:
            logger.debug(f"[灾害预警] EQSC 原始响应日志写入失败: {e}")

    async def _request_json(
        self,
        *,
        url: str,
        access_token: str,
        params: dict[str, Any] | None = None,
        log_label: str,
        allow_retry_on_auth_error: bool = True,
    ) -> tuple[int, Any, str]:
        """发送 EQSC GET 请求，返回 (status, json_or_none, raw_text)。

        遇到 401/403 时会强制刷新 AccessToken 并重试一次，避免“刚拿到 token
        但业务接口短暂鉴权失败/旧 token 失效”时直接放弃。
        成功响应会同步写入原始消息日志，便于回溯 EQSC 报文。
        """
        session = await self._ensure_session()
        current_token = access_token
        last_status = 0
        last_text = ""

        for attempt in range(2):
            headers = {"Authorization": f"Bearer {current_token}"}
            async with session.get(url, headers=headers, params=params) as response:
                last_status = response.status
                last_text = (await response.text()).strip()
                if response.status == 200:
                    try:
                        # 优先用已读文本反序列化，避免二次读 body
                        parsed = json.loads(last_text) if last_text else {}
                        self._log_http_response(
                            url=url,
                            params=params,
                            status_code=response.status,
                            response_data=parsed,
                        )
                        return (
                            response.status,
                            parsed,
                            last_text,
                        )
                    except Exception:
                        logger.warning(
                            f"[灾害预警] {log_label} 响应 JSON 解析失败: {last_text[:200]}"
                        )
                        self._log_http_response(
                            url=url,
                            params=params,
                            status_code=response.status,
                            response_data=last_text[:500] if last_text else "",
                        )
                        return response.status, None, last_text

                if response.status in (401, 403):
                    self._token_manager.invalidate()
                    logger.warning(
                        f"[灾害预警] {log_label} 鉴权失败: HTTP {response.status}；"
                        f"token={self._mask_token(current_token)}"
                        + (f"；响应: {last_text[:160]}" if last_text else "")
                    )
                    if allow_retry_on_auth_error and attempt == 0:
                        refreshed = await self._token_manager.get_access_token(
                            force_refresh=True
                        )
                        if refreshed and refreshed != current_token:
                            logger.info(
                                f"[灾害预警] {log_label} 已刷新 AccessToken，准备重试一次"
                            )
                            current_token = refreshed
                            continue
                    return response.status, None, last_text

                logger.warning(
                    f"[灾害预警] {log_label} 失败: HTTP {response.status}"
                    + (f"；响应: {last_text[:160]}" if last_text else "")
                )
                return response.status, None, last_text

        return last_status, None, last_text

    async def fetch_typhoon_by_id(
        self,
        typhoon_id: str,
        access_token: str | None = None,
    ) -> dict[str, Any] | None:
        """按台风 ID 查询台风详细数据。

        EQSC 的台风 ID 格式为 4 位（年份后2位+编号2位），
        FAN Studio 的台风 ID 格式为 6 位（年份4位+编号2位），
        调用方需在传入前完成 ID 转换。

        Args:
            typhoon_id: EQSC 格式的台风 ID（4位）。
            access_token: 可复用的 AccessToken；若未提供则内部自行获取。

        Returns:
            台风数据字典，或 None 表示查询失败/未找到。
        """
        # 检查缓存
        cached = self._cache.get(typhoon_id)
        if cached and self._is_cache_valid(cached[1]):
            logger.debug(f"[灾害预警] EQSC 台风 {typhoon_id} 命中缓存")
            return cached[0]

        # 获取 AccessToken
        if access_token is None:
            access_token = await self._token_manager.get_access_token()
        if not access_token:
            return None

        try:
            url = f"{self._base_url}/typhoonNMC.json"
            status, data, _raw = await self._request_json(
                url=url,
                access_token=access_token,
                params={"id": typhoon_id},
                log_label=f"EQSC 查询台风 {typhoon_id}",
            )
            if status != 200 or not isinstance(data, dict):
                return None

            # 解析响应：{"typhoon": [{...}]}
            typhoon_list = data.get("typhoon", []) if isinstance(data, dict) else []
            if not typhoon_list:
                logger.debug(f"[灾害预警] EQSC 台风 {typhoon_id} 未找到匹配数据")
                return None

            # 取第一个匹配的台风
            typhoon_data = typhoon_list[0]
            # 写入缓存
            self._cache[typhoon_id] = (typhoon_data, time.time() + self._cache_ttl)
            logger.debug(f"[灾害预警] EQSC 台风 {typhoon_id} 查询成功并已缓存")
            return typhoon_data

        except Exception as e:
            logger.error(
                f"[灾害预警] EQSC 查询台风 {typhoon_id} 异常: "
                f"{type(e).__name__}: {e or repr(e)}"
            )
            return None

    async def fetch_typhoon_list(
        self,
        access_token: str | None = None,
    ) -> list[dict[str, Any]]:
        """查询 EQSC 台风列表（无参，至多约 20 个最新台风，含历史）。

        注意：该接口并非严格“仅活跃台风”，实际常返回最新历史编报集合。
        兼容别名：`fetch_active_typhoons`。
        """
        # 检查缓存
        if self._list_cache and self._is_cache_valid(self._list_cache[1]):
            logger.debug("[灾害预警] EQSC 台风列表命中缓存")
            return self._list_cache[0]

        # 获取 AccessToken
        if access_token is None:
            access_token = await self._token_manager.get_access_token()
        if not access_token:
            return []

        try:
            url = f"{self._base_url}/typhoonNMC.json"
            status, data, _raw = await self._request_json(
                url=url,
                access_token=access_token,
                log_label="EQSC 查询台风列表",
            )
            if status != 200 or not isinstance(data, dict):
                return []

            typhoon_list = data.get("typhoon", []) if isinstance(data, dict) else []
            # 写入缓存
            self._list_cache = (typhoon_list, time.time() + self._cache_ttl)
            logger.debug(
                f"[灾害预警] EQSC 台风列表查询成功，共 {len(typhoon_list)} 个台风"
            )
            return typhoon_list

        except Exception as e:
            logger.error(
                f"[灾害预警] EQSC 查询台风列表异常: {type(e).__name__}: {e or repr(e)}"
            )
            return []

    async def fetch_active_typhoons(
        self,
        access_token: str | None = None,
    ) -> list[dict[str, Any]]:
        """兼容旧名：实际返回 EQSC 无参台风列表（含历史）。"""
        return await self.fetch_typhoon_list(access_token=access_token)

    def find_typhoon_by_name(
        self,
        typhoon_list: list[dict[str, Any]],
        name_cn: str = "",
        name_en: str = "",
    ) -> dict[str, Any] | None:
        """在台风列表中按名称匹配台风。

        Args:
            typhoon_list: EQSC 返回的台风列表。
            name_cn: 台风中文名。
            name_en: 台风英文名。

        Returns:
            匹配到的台风数据字典，或 None。
        """
        for typhoon in typhoon_list:
            if not isinstance(typhoon, dict):
                continue
            eqsc_name_cn = str(typhoon.get("nameCN", "") or "").strip()
            eqsc_name_en = str(typhoon.get("nameEN", "") or "").strip()
            if name_cn and eqsc_name_cn and name_cn == eqsc_name_cn:
                return typhoon
            if name_en and eqsc_name_en and name_en.upper() == eqsc_name_en.upper():
                return typhoon
        return None


__all__ = ["EqscTyphoonClient"]
