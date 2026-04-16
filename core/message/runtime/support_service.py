"""
消息管理器支持工具服务。
负责消息构建缓存键生成与远程图片附加辅助逻辑，
进一步减少 MessagePushManager 中的工具方法数量。
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urlparse

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain

from ....models.models import DisasterEvent, EarthquakeData


class MessageManagerSupportService:
    """消息管理器支持工具服务。"""

    def __init__(self, manager):
        self.manager = manager

    @staticmethod
    def build_map_cache_key(lat: float, lon: float, config: dict[str, Any]) -> str:
        """构建地图渲染缓存键。"""
        # 坐标取 5 位小数即可兼顾精度与缓存命中率，避免浮点尾差导致无意义失配。
        key_obj = {
            "type": "map",
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "map_source": config.get("map_source", "PetalMap矢量图亮"),
            "map_zoom_level": config.get("map_zoom_level", 5),
            "playwright_mode": config.get("playwright_mode", "local"),
        }
        return json.dumps(key_obj, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def build_global_quake_card_cache_key(
        earthquake: EarthquakeData,
        message_format_config: dict[str, Any],
        display_timezone: str,
    ) -> str:
        """构建 Global Quake 卡片缓存键。"""
        key_obj = {
            "type": "global_quake_card",
            "event_id": earthquake.event_id or earthquake.id,
            "updates": getattr(earthquake, "updates", 1),
            "shock_time": (
                earthquake.shock_time.isoformat()
                if getattr(earthquake, "shock_time", None)
                else None
            ),
            "latitude": earthquake.latitude,
            "longitude": earthquake.longitude,
            "magnitude": earthquake.magnitude,
            "depth": earthquake.depth,
            "intensity": earthquake.intensity,
            "place_name": earthquake.place_name,
            "template": message_format_config.get("global_quake_template", "Aurora"),
            "map_source": message_format_config.get("map_source", "PetalMap矢量图亮"),
            "map_zoom_level": message_format_config.get("map_zoom_level", 5),
            "playwright_mode": message_format_config.get("playwright_mode", "local"),
            "timezone": display_timezone,
        }
        return json.dumps(key_obj, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def build_message_build_cache_key(
        event: DisasterEvent,
        runtime_config: dict[str, Any],
    ) -> str:
        """构建消息构建缓存键（同事件+同渲染参数复用）。"""
        message_format_config = runtime_config.get("message_format", {})
        weather_config = runtime_config.get("weather_config", {})

        # 这里不直接序列化整份配置，而是仅提取真正影响渲染结果的字段，
        # 避免无关配置变化导致缓存过度失效。
        key_obj = {
            "event_id": event.id,
            "source": event.source.value
            if hasattr(event.source, "value")
            else str(event.source),
            "display_timezone": runtime_config.get("display_timezone", "UTC+8"),
            "message_format": {
                "include_map": message_format_config.get("include_map", False),
                "map_source": message_format_config.get(
                    "map_source", "PetalMap矢量图亮"
                ),
                "map_zoom_level": message_format_config.get("map_zoom_level", 5),
                "playwright_mode": message_format_config.get(
                    "playwright_mode", "local"
                ),
                "use_global_quake_card": message_format_config.get(
                    "use_global_quake_card", False
                ),
                "global_quake_template": message_format_config.get(
                    "global_quake_template", "Aurora"
                ),
                "detailed_jma_intensity": message_format_config.get(
                    "detailed_jma_intensity", False
                ),
            },
            "weather": {
                "enable_weather_icon": weather_config.get("enable_weather_icon", True),
                "max_description_length": weather_config.get(
                    "max_description_length", 384
                ),
            },
        }
        return json.dumps(key_obj, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def is_http_url(url: str | None) -> bool:
        """判断是否为可抓取的 HTTP(S) URL。"""
        if not isinstance(url, str):
            return False
        normalized = url.strip()
        return normalized.startswith("http://") or normalized.startswith("https://")

    async def append_remote_image_component(
        self,
        chain: MessageChain,
        image_url: str,
        *,
        media_label: str,
        allow_url_fallback: bool = True,
    ) -> bool:
        """将远程图片优先转为 Base64 附加到消息链，失败时可回退 URL。"""
        normalized_url = image_url.strip()
        if not self.is_http_url(normalized_url):
            logger.debug(
                f"[灾害预警] 跳过非 HTTP 图片链接 ({media_label}): {normalized_url}"
            )
            return False

        # 优先抓取并转 Base64，可提升不同平台下的图片可达性与稳定性。
        fetch_result = await self.manager.fetch_remote_media(
            normalized_url,
            expected_kind="image",
        )
        if fetch_result and fetch_result.get("data"):
            try:
                b64_data = base64.b64encode(fetch_result["data"]).decode()
                chain.chain.append(Comp.Image.fromBase64(b64_data))
                logger.debug(
                    "[灾害预警] 已附加远程图片(Base64) "
                    f"{media_label}: source={fetch_result.get('source_url')}, "
                    f"final={fetch_result.get('final_url')}, "
                    f"content_type={fetch_result.get('content_type')}, "
                    f"bytes={fetch_result.get('bytes')}"
                )
                return True
            except Exception as e:
                logger.warning(
                    "[灾害预警] 远程图片转Base64失败 "
                    f"({media_label}): source={fetch_result.get('source_url')}, "
                    f"final={fetch_result.get('final_url')}, "
                    f"content_type={fetch_result.get('content_type')}, "
                    f"bytes={fetch_result.get('bytes')}, "
                    f"error={type(e).__name__}: {e}"
                )

        if fetch_result:
            logger.warning(
                "[灾害预警] 远程图片抓取失败 "
                f"({media_label}): source={fetch_result.get('source_url')}, "
                f"final={fetch_result.get('final_url')}, "
                f"status={fetch_result.get('status')}, "
                f"content_type={fetch_result.get('content_type')}, "
                f"content_length={fetch_result.get('content_length')}, "
                f"bytes={fetch_result.get('bytes')}, "
                f"error={fetch_result.get('exception_type') or 'FetchError'}: {fetch_result.get('error')}"
            )

        # 当平台支持 URL 图片时，回退 URL 发送能避免因下载失败导致整条图件缺失。
        if allow_url_fallback:
            try:
                chain.chain.append(Comp.Image.fromURL(normalized_url))
                logger.debug(
                    f"[灾害预警] 远程图片已回退为URL发送 ({media_label}): {normalized_url}"
                )
                return True
            except Exception as e:
                parsed = urlparse(normalized_url)
                logger.warning(
                    "[灾害预警] 远程图片URL回退发送失败 "
                    f"({media_label}): scheme={parsed.scheme}, host={parsed.netloc}, "
                    f"url={normalized_url}, error={type(e).__name__}: {e}"
                )

        return False
