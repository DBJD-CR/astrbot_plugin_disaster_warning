"""
消息构建服务。
负责文本消息、卡片、地图、远程媒体图件等消息内容拼装，
进一步收敛 MessagePushManager 中的构建职责。
"""

from __future__ import annotations

import base64
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain

from ....models.data_source_config import get_eew_sources
from ....models.models import (
    DisasterEvent,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)


class MessageBuildService:
    """消息构建服务。"""

    def __init__(self, manager):
        self.manager = manager

    def build_message(self, event: DisasterEvent) -> MessageChain:
        """构建同步消息。"""
        # 同步版本只负责纯文本主干，适合无需异步渲染附件的简单调用场景。
        source_id = self.manager.resolve_source_id_for_execution(event)
        message_format_config = self.manager.config.get("message_format", {})
        return self.manager.text_message_builder.build(
            event,
            source_id,
            message_format_config,
        )

    async def build_message_async(
        self,
        event: DisasterEvent,
        runtime_config: dict[str, Any] | None = None,
    ) -> MessageChain:
        """构建异步消息，支持卡片、地图和图件附件。"""
        active_config = runtime_config or self.manager.config
        source_id = self.manager.resolve_source_id_for_execution(event)
        message_format_config = active_config.get("message_format", {})

        # Global Quake 启用专用卡片时优先走整卡渲染，避免先拼文本再附加地图的重复工作。
        global_quake_card = await self._try_build_global_quake_card(
            event,
            source_id=source_id,
            active_config=active_config,
            message_format_config=message_format_config,
        )
        if global_quake_card is not None:
            return global_quake_card

        # 默认路径先构建文本主消息，再按事件类型补充可选附件。
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
        event: DisasterEvent,
        target_sessions: list[str],
        config: dict[str, Any],
    ) -> None:
        """后台渲染并发送分离的地图图片。"""
        try:
            lat, lon = event.data.latitude, event.data.longitude
            # 分离地图是纯附件补发，所以经纬度不合法时直接放弃，不影响主消息已发送结果。
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
                    await self.manager.send_message(session, map_message)
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

        # 地图渲染代价较高，因此统一通过 manager 的渲染缓存做去重与复用。
        map_cache_key = self.manager._build_map_cache_key(lat, lon, config)
        return await self.manager._render_with_cache(map_cache_key, render_map)

    async def _try_build_global_quake_card(
        self,
        event: DisasterEvent,
        *,
        source_id: str,
        active_config: dict[str, Any],
        message_format_config: dict[str, Any],
    ) -> MessageChain | None:
        use_gq_card = message_format_config.get("use_global_quake_card", False)
        if not (
            source_id == "global_quake"
            and use_gq_card
            and isinstance(event.data, EarthquakeData)
        ):
            return None

        try:
            return await self.manager.global_quake_card_builder.build(
                event.data,
                active_config=active_config,
                message_format_config=message_format_config,
                cache_key_builder=self.manager._build_global_quake_card_cache_key,
                render_with_cache=self.manager._render_with_cache,
            )
        except Exception as e:
            logger.error(f"[灾害预警] Global Quake 卡片渲染失败: {e}，回退到文本模式")
            return None

    async def _append_map_if_needed(
        self,
        chain: MessageChain,
        event: DisasterEvent,
        *,
        source_id: str,
        message_format_config: dict[str, Any],
    ) -> None:
        include_map = message_format_config.get("include_map", False)
        split_map_sources = set(get_eew_sources()) - {"global_quake"}
        if not include_map or not isinstance(event.data, EarthquakeData):
            return

        if source_id in split_map_sources:
            logger.debug(
                f"[灾害预警] 数据源 {source_id} 属于分离地图发送类型，跳过同步附加"
            )
            return

        lat_valid = event.data.latitude is not None and -90 <= event.data.latitude <= 90
        lon_valid = (
            event.data.longitude is not None and -180 <= event.data.longitude <= 180
        )
        if not (lat_valid and lon_valid):
            return

        try:
            map_image_path = await self.render_map_image(
                event.data.latitude,
                event.data.longitude,
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
        event: DisasterEvent,
        active_config: dict[str, Any],
    ) -> None:
        weather_config = active_config.get("weather_config", {})
        enable_weather_icon = weather_config.get("enable_weather_icon", True)
        if not (enable_weather_icon and isinstance(event.data, WeatherAlarmData)):
            return

        p_code = event.data.type
        if not p_code:
            return

        icon_url = f"https://image.nmc.cn/assets/img/alarm/{p_code}.png"
        try:
            chain.chain.append(Comp.Image.fromURL(icon_url))
            logger.debug(f"[灾害预警] 已附加气象预警图标: {icon_url}")
        except Exception as e:
            logger.error(f"[灾害预警] 附加气象预警图标失败: {e}")

    async def _append_tsunami_media_if_needed(
        self,
        chain: MessageChain,
        event: DisasterEvent,
    ) -> None:
        if not isinstance(event.data, TsunamiData):
            return

        map_urls = getattr(event.data, "map_urls", {}) or {}
        if not isinstance(map_urls, dict):
            return

        for map_key in ["earthquake", "amplitude", "coastal"]:
            map_url = map_urls.get(map_key)
            if isinstance(map_url, str) and map_url.strip():
                await self.manager._append_remote_image_component(
                    chain,
                    map_url,
                    media_label=f"海啸图件/{map_key}",
                    allow_url_fallback=True,
                )

    async def _append_cwa_report_media_if_needed(
        self,
        chain: MessageChain,
        event: DisasterEvent,
        source_id: str,
    ) -> None:
        if not (
            source_id == "cwa_fanstudio_report"
            and isinstance(event.data, EarthquakeData)
        ):
            return

        report_image_urls: list[str] = []
        for image_url in [
            getattr(event.data, "image_uri", None),
            getattr(event.data, "shakemap_uri", None),
        ]:
            if isinstance(image_url, str):
                normalized_url = image_url.strip()
                if normalized_url and normalized_url not in report_image_urls:
                    report_image_urls.append(normalized_url)

        for idx, image_url in enumerate(report_image_urls, start=1):
            await self.manager._append_remote_image_component(
                chain,
                image_url,
                media_label=f"CWA地震报告图件/{idx}",
                allow_url_fallback=True,
            )
