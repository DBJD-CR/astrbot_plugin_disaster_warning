"""
消息构建服务。
负责文本消息、卡片、地图、远程媒体图件等消息内容拼装，
进一步收敛 MessagePushManager 中的构建职责。
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urlparse

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain

from ...domain.event_models import (
    EarthquakeEvent,
    EventEnvelope,
    TsunamiEvent,
    WeatherEvent,
)
from ...services.identity.event_identity import resolve_report_num
from ...sources.source_catalog import get_source_ids_by_type
from ...sources.source_entry import SourceType


class MessageBuildService:
    """消息构建服务。"""

    TSUNAMI_MEDIA_KEYS: tuple[str, ...] = ("earthquake", "amplitude", "coastal")

    def __init__(self, manager):
        # 通过主消息管理器复用构建器、发送器、缓存和配置能力。
        self.manager = manager

    @staticmethod
    def _get_envelope(event: EventEnvelope):
        """统一获取领域 envelope。"""
        return event

    @staticmethod
    def _get_domain_event(event: EventEnvelope):
        """统一获取领域事件。"""
        return event.event

    @staticmethod
    def _get_event_metadata(event: EventEnvelope) -> dict[str, Any]:
        """统一获取事件 metadata 视图。"""
        envelope = event
        domain_event = event.event

        merged: dict[str, Any] = {}
        domain_metadata = getattr(domain_event, "metadata", None)
        if isinstance(domain_metadata, dict):
            merged.update(domain_metadata)

        metadata = getattr(envelope, "metadata", None)
        if isinstance(metadata, dict):
            merged.update(metadata)

        return merged

    @staticmethod
    def _get_split_map_source_ids() -> set[str]:
        """返回需要分离发送地图的地震预警来源集合。"""
        return set(get_source_ids_by_type(SourceType.EARTHQUAKE_WARNING)) - {
            "global_quake"
        }

    @staticmethod
    def _resolve_source_id(event: EventEnvelope) -> str:
        """统一解析执行路径中的 source_id。"""
        return (getattr(event, "source_id", "") or "").strip()

    @staticmethod
    def _build_map_cache_key(lat: float, lon: float, config: dict[str, Any]) -> str:
        """构建地图渲染缓存键。"""
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
    def _build_global_quake_card_cache_key(
        earthquake: EventEnvelope,
        message_format_config: dict[str, Any],
        display_timezone: str,
    ) -> str:
        """构建 Global Quake 卡片缓存键。"""
        payload = earthquake.payload
        metadata = earthquake.metadata if isinstance(earthquake.metadata, dict) else {}
        identity = earthquake.identity
        domain_event = earthquake.event
        # 只有地震事件才能生成这类卡片缓存键，其他事件类型直接视为调用错误。
        if not isinstance(domain_event, EarthquakeEvent):
            raise TypeError("Global Quake card cache key requires EarthquakeEvent")

        report_num = resolve_report_num(earthquake) or 1
        payload_marker = (
            payload.raw.get("id")
            if isinstance(payload, object)
            and hasattr(payload, "raw")
            and isinstance(payload.raw, dict)
            else None
        )
        key_obj = {
            "type": "global_quake_card",
            "event_id": getattr(identity, "event_id", "")
            or getattr(domain_event, "place_name", "")
            or "unknown_event",
            "report_num": report_num,
            "occurred_at": domain_event.occurred_at.isoformat()
            if getattr(domain_event, "occurred_at", None)
            else None,
            "latitude": domain_event.latitude,
            "longitude": domain_event.longitude,
            "magnitude": domain_event.magnitude,
            "depth": domain_event.depth,
            "intensity": domain_event.intensity,
            "place_name": domain_event.place_name,
            "max_pga": metadata.get("max_pga"),
            "stations": metadata.get("stations"),
            "payload_marker": payload_marker,
            "template": message_format_config.get("global_quake_template", "Aurora"),
            "map_source": message_format_config.get("map_source", "PetalMap矢量图亮"),
            "map_zoom_level": message_format_config.get("map_zoom_level", 5),
            "playwright_mode": message_format_config.get("playwright_mode", "local"),
            "timezone": display_timezone,
        }
        return json.dumps(key_obj, sort_keys=True, ensure_ascii=False)

    async def _append_remote_image_component(
        self,
        chain: MessageChain,
        image_url: str,
        *,
        media_label: str,
        allow_url_fallback: bool = True,
    ) -> bool:
        """将远程图片优先转为 Base64 附加到消息链，失败时可回退 URL。"""
        normalized_url = image_url.strip()
        # 这里只接受标准网络图片地址，避免把本地路径或其他协议误当成远程图件抓取。
        if not (
            isinstance(normalized_url, str)
            and (
                normalized_url.startswith("http://")
                or normalized_url.startswith("https://")
            )
        ):
            logger.debug(
                f"[灾害预警] 跳过非 HTTP 图片链接 ({media_label}): {normalized_url}"
            )
            return False

        fetch_result = await self.manager.fetch_remote_media(
            normalized_url,
            expected_kind="image",
        )
        if fetch_result and fetch_result.get("data"):
            try:
                b64_data = base64.b64encode(fetch_result["data"]).decode()
                chain.chain.append(Comp.Image.fromBase64(b64_data))
                return True
            except Exception as e:
                logger.warning(
                    "[灾害预警] 远程图片转Base64失败 "
                    f"({media_label}): source={fetch_result.get('source_url')}, final={fetch_result.get('final_url')}, "
                    f"content_type={fetch_result.get('content_type')}, bytes={fetch_result.get('bytes')}, error={type(e).__name__}: {e}"
                )

        if fetch_result:
            logger.warning(
                "[灾害预警] 远程图片抓取失败 "
                f"({media_label}): source={fetch_result.get('source_url')}, final={fetch_result.get('final_url')}, "
                f"status={fetch_result.get('status')}, content_type={fetch_result.get('content_type')}, "
                f"content_length={fetch_result.get('content_length')}, bytes={fetch_result.get('bytes')}, "
                f"error={fetch_result.get('exception_type') or 'FetchError'}: {fetch_result.get('error')}"
            )

        if allow_url_fallback:
            try:
                chain.chain.append(Comp.Image.fromURL(normalized_url))
                return True
            except Exception as e:
                parsed = urlparse(normalized_url)
                logger.warning(
                    "[灾害预警] 远程图片URL回退发送失败 "
                    f"({media_label}): scheme={parsed.scheme}, host={parsed.netloc}, url={normalized_url}, error={type(e).__name__}: {e}"
                )
        return False

    def build_message(self, event: EventEnvelope) -> MessageChain:
        """构建同步消息。"""
        # 同步构建路径只生成文本消息，适用于不需要额外附件的轻量场景。
        source_id = self._resolve_source_id(event)
        message_format_config = self.manager.config.get("message_format", {})
        return self.manager.text_message_builder.build(
            event,
            source_id,
            message_format_config,
        )

    async def build_message_async(
        self,
        event: EventEnvelope,
        runtime_config: dict[str, Any] | None = None,
    ) -> MessageChain:
        """构建异步消息，支持卡片、地图和图件附件。"""
        active_config = runtime_config or self.manager.config
        source_id = self._resolve_source_id(event)
        message_format_config = active_config.get("message_format", {})

        # 若当前事件满足 Global Quake 卡片条件，则优先直接返回整张卡片消息。
        global_quake_card = await self._try_build_global_quake_card(
            event,
            source_id=source_id,
            active_config=active_config,
            message_format_config=message_format_config,
        )
        if global_quake_card is not None:
            return global_quake_card

        chain = self.manager.text_message_builder.build(
            event,
            source_id,
            message_format_config,
            full_config=active_config,
        )

        await self._append_map_if_needed(
            chain,
            event,
            source_id=source_id,
            message_format_config=message_format_config,
        )
        await self._append_weather_icon_if_needed(chain, event, active_config)
        await self._append_tsunami_media_if_needed(chain, event)
        await self._append_cwa_report_media_if_needed(chain, event, source_id)
        return chain

    async def push_split_map(
        self,
        event: EventEnvelope,
        target_sessions: list[str],
        config: dict[str, Any],
    ) -> None:
        """后台渲染并发送分离的地图图片。"""
        try:
            domain_event = self._get_domain_event(event)
            if not isinstance(domain_event, EarthquakeEvent):
                return

            lat, lon = domain_event.latitude, domain_event.longitude
            # 地图渲染前先校验经纬度，避免无效坐标导致浏览器渲染报错。
            if (
                lat is None
                or lon is None
                or not (-90 <= lat <= 90)
                or not (-180 <= lon <= 180)
            ):
                return

            map_image_path = await self.render_map_image(lat, lon, config)
            if not map_image_path:
                return

            with open(map_image_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode()

            map_message = MessageChain([Comp.Image.fromBase64(b64_data)])
            for session in target_sessions:
                try:
                    await self.manager.session_sender.send(session, map_message)
                    logger.debug(f"[灾害预警] 分离地图已发送到 {session}")
                except Exception as e:
                    logger.error(f"[灾害预警] 分离地图发送到 {session} 失败: {e}")
        except Exception as e:
            logger.error(f"[灾害预警] 异步地图渲染任务失败: {e}")

    async def render_map_image(
        self, lat: float, lon: float, config: dict
    ) -> str | None:
        """渲染通用地图图片（带缓存复用）。"""

        async def render_map() -> str | None:
            return await self.manager.map_attachment_builder.render_map_image(
                lat,
                lon,
                config,
            )

        map_cache_key = self._build_map_cache_key(lat, lon, config)
        return await self.manager._render_with_cache(map_cache_key, render_map)

    async def _try_build_global_quake_card(
        self,
        event: EventEnvelope,
        *,
        source_id: str,
        active_config: dict[str, Any],
        message_format_config: dict[str, Any],
    ) -> MessageChain | None:
        use_gq_card = message_format_config.get("use_global_quake_card", False)
        domain_event = self._get_domain_event(event)
        if not (
            source_id == "global_quake"
            and use_gq_card
            and isinstance(domain_event, EarthquakeEvent)
        ):
            return None

        try:
            return await self.manager.global_quake_card_builder.build(
                event,
                active_config=active_config,
                message_format_config=message_format_config,
                cache_key_builder=self._build_global_quake_card_cache_key,
                render_with_cache=self.manager._render_with_cache,
            )
        except Exception as e:
            logger.error(f"[灾害预警] Global Quake 卡片渲染失败: {e}，回退到文本模式")
            return None

    async def _append_map_if_needed(
        self,
        chain: MessageChain,
        event: EventEnvelope,
        *,
        source_id: str,
        message_format_config: dict[str, Any],
    ) -> None:
        """按配置决定是否在主消息链中附加地图图片。"""
        include_map = message_format_config.get("include_map", False)
        split_map_sources = self._get_split_map_source_ids()
        domain_event = self._get_domain_event(event)
        if not include_map or not isinstance(domain_event, EarthquakeEvent):
            return

        if source_id in split_map_sources:
            logger.debug(
                f"[灾害预警] 数据源 {source_id} 属于分离地图发送类型，跳过同步附加"
            )
            return

        lat_valid = (
            domain_event.latitude is not None and -90 <= domain_event.latitude <= 90
        )
        lon_valid = (
            domain_event.longitude is not None and -180 <= domain_event.longitude <= 180
        )
        if not (lat_valid and lon_valid):
            return

        try:
            map_image_path = await self.render_map_image(
                domain_event.latitude,
                domain_event.longitude,
                message_format_config,
            )
            if not map_image_path:
                return
            try:
                with open(map_image_path, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode()
                chain.chain.append(Comp.Image.fromBase64(b64_data))
                logger.debug("[灾害预警] 已附加地图图片 (Base64模式)")
            except Exception as b64_err:
                logger.error(f"[灾害预警] 地图图片转Base64失败: {b64_err}")
        except Exception as e:
            logger.error(f"[灾害预警] 地图图片生成失败: {e}")

    async def _append_weather_icon_if_needed(
        self,
        chain: MessageChain,
        event: EventEnvelope,
        active_config: dict[str, Any],
    ) -> None:
        """按配置为气象事件附加预警图标。"""
        weather_config = active_config.get("weather_config", {})
        enable_weather_icon = weather_config.get("enable_weather_icon", True)
        domain_event = self._get_domain_event(event)
        if not (enable_weather_icon and isinstance(domain_event, WeatherEvent)):
            return

        metadata = self._get_event_metadata(event)
        p_code = (
            metadata.get("weather_code")
            or metadata.get("type")
            or metadata.get("alert_code")
            or metadata.get("code")
            or getattr(domain_event, "alert_type", "")
        )
        if not isinstance(p_code, str) or not p_code.strip():
            return

        p_code = p_code.strip()

        icon_url = f"https://image.nmc.cn/assets/img/alarm/{p_code}.png"
        try:
            chain.chain.append(Comp.Image.fromURL(icon_url))
            logger.debug(f"[灾害预警] 已附加气象预警图标: {icon_url}")
        except Exception as e:
            logger.error(f"[灾害预警] 附加气象预警图标失败: {e}")

    async def _append_tsunami_media_if_needed(
        self,
        chain: MessageChain,
        event: EventEnvelope,
    ) -> None:
        """按需把海啸图件附加到消息链。"""
        domain_event = self._get_domain_event(event)
        if not isinstance(domain_event, TsunamiEvent):
            return

        metadata = self._get_event_metadata(event)

        map_urls = metadata.get("map_urls")
        if not isinstance(map_urls, dict):
            return

        for map_key in self.TSUNAMI_MEDIA_KEYS:
            map_url = map_urls.get(map_key)
            if isinstance(map_url, str) and map_url.strip():
                await self._append_remote_image_component(
                    chain,
                    map_url.strip(),
                    media_label=f"海啸图件/{map_key}",
                    allow_url_fallback=True,
                )

    async def _append_cwa_report_media_if_needed(
        self,
        chain: MessageChain,
        event: EventEnvelope,
        source_id: str,
    ) -> None:
        """按需附加台湾地震报告相关图件。"""
        if source_id != "cwa_fanstudio_report":
            return

        metadata = self._get_event_metadata(event)

        report_image_urls: list[str] = []
        candidate_urls = [
            metadata.get("image_uri"),
            metadata.get("shakemap_uri"),
        ]
        for image_url in candidate_urls:
            if isinstance(image_url, str):
                normalized_url = image_url.strip()
                if normalized_url and normalized_url not in report_image_urls:
                    report_image_urls.append(normalized_url)

        for idx, image_url in enumerate(report_image_urls, start=1):
            await self._append_remote_image_component(
                chain,
                image_url,
                media_label=f"CWA地震报告图件/{idx}",
                allow_url_fallback=True,
            )
