"""
消息推送管理器
实现优化的报数控制、拆分过滤器和改进的去重逻辑
"""

import asyncio
import base64
import glob
import json
import os
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from jinja2 import Template

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.star import StarTools

from ...models.data_source_config import (
    get_eew_sources,
    get_intensity_based_sources,
    get_scale_based_sources,
    is_source_enabled_in_data_sources,
)
from ...models.models import (
    DATA_SOURCE_MAPPING,
    DisasterEvent,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from ...utils.formatters import (
    CWAReportFormatter,
    GlobalQuakeFormatter,
    format_earthquake_message,
    format_tsunami_message,
    format_weather_message,
)
from ...utils.map_tile_sources import get_tile_url_js
from ...utils.version import get_plugin_version
from ..filters import (
    GlobalQuakeFilter,
    IntensityFilter,
    KeywordFilter,
    LocalIntensityFilter,
    ReportCountController,
    ScaleFilter,
    USGSFilter,
    WeatherFilter,
)
from ..support.event_deduplicator import EventDeduplicator
from .browser_manager import BrowserManager


class MessagePushManager:
    """消息推送管理器"""

    def __init__(self, config: dict[str, Any], context, telemetry=None):
        self.config = config
        self.context = context
        self._telemetry = telemetry
        # 初始化插件根目录 (用于访问 resources)
        self.plugin_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # 初始化数据存储目录 (使用 StarTools 获取，用于存放 temp)
        self.storage_dir = StarTools.get_data_dir("astrbot_plugin_disaster_warning")
        self.temp_dir = self.storage_dir / "temp"
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir, exist_ok=True)

        # 兼容旧代码，保留 data_dir 指向插件根目录，但建议逐步迁移
        self.data_dir = self.plugin_root

        # 初始化过滤器 - 使用新的配置路径
        earthquake_filters = config.get("earthquake_filters", {})

        # 关键词过滤器配置
        keyword_filter_config = earthquake_filters.get("keyword_filter", {})
        self.keyword_filter = KeywordFilter(
            enabled=keyword_filter_config.get("enabled", False),
            blacklist=keyword_filter_config.get("blacklist", []),
            whitelist=keyword_filter_config.get("whitelist", []),
        )

        # 烈度过滤器配置
        intensity_filter_config = earthquake_filters.get("intensity_filter", {})
        self.intensity_filter = IntensityFilter(
            enabled=intensity_filter_config.get("enabled", True),
            min_magnitude=intensity_filter_config.get("min_magnitude", 2.0),
            min_intensity=intensity_filter_config.get("min_intensity", 4.0),
        )

        # 震度过滤器配置
        scale_filter_config = earthquake_filters.get("scale_filter", {})
        self.scale_filter = ScaleFilter(
            enabled=scale_filter_config.get("enabled", True),
            min_magnitude=scale_filter_config.get("min_magnitude", 2.0),
            min_scale=scale_filter_config.get("min_scale", 1.0),
        )

        # USGS过滤器配置
        magnitude_only_filter_config = earthquake_filters.get(
            "magnitude_only_filter", {}
        )
        self.usgs_filter = USGSFilter(
            enabled=magnitude_only_filter_config.get("enabled", True),
            min_magnitude=magnitude_only_filter_config.get("min_magnitude", 4.5),
        )

        # Global Quake过滤器配置
        global_quake_filter_config = earthquake_filters.get("global_quake_filter", {})
        self.global_quake_filter = GlobalQuakeFilter(
            enabled=global_quake_filter_config.get("enabled", True),
            min_magnitude=global_quake_filter_config.get("min_magnitude", 4.5),
            min_intensity=global_quake_filter_config.get("min_intensity", 5.0),
        )

        # 初始化报数控制器
        push_config = config.get("push_frequency_control", {})
        self.report_controller = ReportCountController(
            cea_cwa_report_n=push_config.get("cea_cwa_report_n", 1),
            jma_report_n=push_config.get("jma_report_n", 3),
            gq_report_n=push_config.get("gq_report_n", 5),
            final_report_always_push=push_config.get("final_report_always_push", True),
            ignore_non_final_reports=push_config.get("ignore_non_final_reports", False),
        )

        # 初始化去重器
        self.deduplicator = EventDeduplicator(
            time_window_minutes=config.get("event_deduplication", {}).get(
                "time_window_minutes", 1
            ),
            location_tolerance_km=config.get("event_deduplication", {}).get(
                "location_tolerance_km", 20.0
            ),
            magnitude_tolerance=config.get("event_deduplication", {}).get(
                "magnitude_tolerance", 0.5
            ),
        )

        # 初始化本地监控过滤器
        self.local_monitor = LocalIntensityFilter(config.get("local_monitoring", {}))

        # 初始化气象预警过滤器
        weather_config = config.get("weather_config", {})
        weather_filter_config = weather_config.get("weather_filter", {})
        self.weather_filter = WeatherFilter(weather_filter_config)

        # 初始化浏览器管理器
        msg_config = config.get("message_format", {})
        raw_pool_size = msg_config.get("browser_pool_size", 2)
        try:
            pool_size = int(raw_pool_size)
        except (TypeError, ValueError):
            # 非法配置（如非整数）时回退到默认值 2
            pool_size = 2
        else:
            # 将非法的 0/负数视为无效并回退到默认值 2
            if pool_size < 1:
                pool_size = 2

        # 获取 Playwright 配置
        playwright_mode = msg_config.get("playwright_mode", "local")
        playwright_server_url = msg_config.get("playwright_server_url", "")

        self.browser_manager = BrowserManager(
            pool_size=pool_size,
            telemetry=telemetry,
            mode=playwright_mode,
            server_url=playwright_server_url,
        )

        # 启动时执行一次清理，避免开发环境下重载插件导致临时文件堆积
        self.cleanup_old_records()

        # 检查是否需要预启动浏览器
        # 如果启用了地图瓦片 (include_map) 或 Global Quake 卡片 (use_global_quake_card)
        # 则在后台异步预热浏览器，避免第一次推送时因启动浏览器造成延迟
        # 注意：远程模式使用 HTTP API，不需要预热
        msg_config = config.get("message_format", {})
        if playwright_mode == "local" and (
            msg_config.get("include_map", False)
            or msg_config.get("use_global_quake_card", False)
        ):
            logger.debug("[灾害预警] 检测到已启用卡片渲染功能，正在后台预热浏览器...")
            asyncio.create_task(self.browser_manager.initialize())

        # CENC 融合策略 Pending 列表
        # key: pending_key, value: {'event': event, 'future': asyncio.Future, 'event_key': str, 'report_num': int, 'created_at': float}
        self.cenc_pending = {}
        # CENC Wolfx 缓存
        # key: event_key, value: {report_num: {'intensity': float, 'created_at': float}}
        self.cenc_wolfx_cache = {}

        # CWA EEW 融合策略 Pending 列表
        # key: pending_key, value: {'event': event, 'future': asyncio.Future, 'event_key': str, 'report_num': int, 'created_at': float}
        self.cwa_eew_pending = {}
        # CWA Wolfx 缓存
        # key: event_key, value: {report_num: {'impact_area': str, 'created_at': float}}
        self.cwa_eew_wolfx_cache = {}

        # 融合缓存生命周期（秒）
        self._fusion_cache_ttl_seconds = 120

        # 会话级报数控制器缓存
        self._session_report_controllers: dict[
            tuple[str, str], ReportCountController
        ] = {}

        # 最近一次推送成功的会话列表（供服务层统计使用）
        self.last_success_sessions: list[str] = []

        # 渲染缓存（地图/卡片）
        # key -> (cache_time, image_path)
        self._render_image_cache: dict[str, tuple[float, str]] = {}
        # key -> in-flight render task
        self._render_inflight_tasks: dict[str, asyncio.Task[str | None]] = {}
        self._render_cache_lock = asyncio.Lock()
        self._render_cache_ttl_seconds = 180

    def _build_runtime_components(
        self,
        runtime_config: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """基于运行时配置构建过滤组件（支持会话级配置）。"""
        earthquake_filters = runtime_config.get("earthquake_filters", {})

        # 关键词过滤器配置
        keyword_filter_config = earthquake_filters.get("keyword_filter", {})
        keyword_filter = KeywordFilter(
            enabled=keyword_filter_config.get("enabled", False),
            blacklist=keyword_filter_config.get("blacklist", []),
            whitelist=keyword_filter_config.get("whitelist", []),
        )

        # 烈度过滤器配置
        intensity_filter_config = earthquake_filters.get("intensity_filter", {})
        intensity_filter = IntensityFilter(
            enabled=intensity_filter_config.get("enabled", True),
            min_magnitude=intensity_filter_config.get("min_magnitude", 2.0),
            min_intensity=intensity_filter_config.get("min_intensity", 4.0),
        )

        # 震度过滤器配置
        scale_filter_config = earthquake_filters.get("scale_filter", {})
        scale_filter = ScaleFilter(
            enabled=scale_filter_config.get("enabled", True),
            min_magnitude=scale_filter_config.get("min_magnitude", 2.0),
            min_scale=scale_filter_config.get("min_scale", 1.0),
        )

        # USGS过滤器配置
        magnitude_only_filter_config = earthquake_filters.get(
            "magnitude_only_filter", {}
        )
        usgs_filter = USGSFilter(
            enabled=magnitude_only_filter_config.get("enabled", True),
            min_magnitude=magnitude_only_filter_config.get("min_magnitude", 4.5),
        )

        # Global Quake过滤器配置
        global_quake_filter_config = earthquake_filters.get("global_quake_filter", {})
        global_quake_filter = GlobalQuakeFilter(
            enabled=global_quake_filter_config.get("enabled", True),
            min_magnitude=global_quake_filter_config.get("min_magnitude", 4.5),
            min_intensity=global_quake_filter_config.get("min_intensity", 5.0),
        )

        # 初始化报数控制器
        push_config = runtime_config.get("push_frequency_control", {})
        report_controller = self.report_controller
        if session_id:
            cache_key = (
                session_id,
                json.dumps(push_config, sort_keys=True, ensure_ascii=False),
            )
            cached = self._session_report_controllers.get(cache_key)
            if cached is None:
                cached = ReportCountController(
                    cea_cwa_report_n=push_config.get("cea_cwa_report_n", 1),
                    jma_report_n=push_config.get("jma_report_n", 3),
                    gq_report_n=push_config.get("gq_report_n", 5),
                    final_report_always_push=push_config.get(
                        "final_report_always_push", True
                    ),
                    ignore_non_final_reports=push_config.get(
                        "ignore_non_final_reports", False
                    ),
                )
                self._session_report_controllers[cache_key] = cached
            report_controller = cached

        # 初始化本地监控过滤器
        local_monitor = LocalIntensityFilter(runtime_config.get("local_monitoring", {}))

        # 初始化气象预警过滤器
        weather_config = runtime_config.get("weather_config", {})
        weather_filter_config = weather_config.get("weather_filter", {})
        weather_filter = WeatherFilter(weather_filter_config, emit_enable_log=False)

        return {
            "keyword_filter": keyword_filter,
            "intensity_filter": intensity_filter,
            "scale_filter": scale_filter,
            "usgs_filter": usgs_filter,
            "global_quake_filter": global_quake_filter,
            "report_controller": report_controller,
            "local_monitor": local_monitor,
            "weather_filter": weather_filter,
        }

    def _cleanup_render_image_cache(self):
        """清理过期或失效的渲染缓存。"""
        now = time.time()
        expired_keys = []
        for key, (cache_time, image_path) in self._render_image_cache.items():
            if now - cache_time > self._render_cache_ttl_seconds:
                expired_keys.append(key)
                continue
            if not os.path.exists(image_path):
                expired_keys.append(key)

        for key in expired_keys:
            self._render_image_cache.pop(key, None)

    async def _render_with_cache(
        self,
        cache_key: str,
        renderer: Callable[[], Awaitable[str | None]],
    ) -> str | None:
        """带去重与缓存的渲染包装器。"""
        render_task: asyncio.Task[str | None] | None = None

        async with self._render_cache_lock:
            self._cleanup_render_image_cache()

            cached_item = self._render_image_cache.get(cache_key)
            if cached_item:
                _, image_path = cached_item
                if os.path.exists(image_path):
                    logger.debug(f"[灾害预警] 命中渲染缓存: {cache_key}")
                    return image_path

            render_task = self._render_inflight_tasks.get(cache_key)
            if render_task is None:
                render_task = asyncio.create_task(renderer())
                self._render_inflight_tasks[cache_key] = render_task

        try:
            result_path = await render_task
            if result_path and os.path.exists(result_path):
                async with self._render_cache_lock:
                    self._render_image_cache[cache_key] = (time.time(), result_path)
            return result_path
        finally:
            async with self._render_cache_lock:
                if self._render_inflight_tasks.get(cache_key) is render_task:
                    self._render_inflight_tasks.pop(cache_key, None)

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
    def _build_message_build_cache_key(
        event: DisasterEvent,
        runtime_config: dict[str, Any],
    ) -> str:
        """构建消息构建缓存键（同事件+同渲染参数复用）。"""
        message_format_config = runtime_config.get("message_format", {})
        weather_config = runtime_config.get("weather_config", {})

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

    def should_push_event(
        self,
        event: DisasterEvent,
        runtime_config: dict[str, Any] | None = None,
        session_id: str | None = None,
        filter_reason_out: list[str] | None = None,
        emit_filter_log: bool = True,
    ) -> bool:
        """判断是否应该推送事件"""
        runtime_config = runtime_config or self.config
        runtime_components = self._build_runtime_components(runtime_config, session_id)

        def reject(reason: str, log_message: str | None = None) -> bool:
            if filter_reason_out is not None:
                filter_reason_out.append(reason)
            if emit_filter_log and log_message:
                logger.info(log_message)
            return False

        # 1. 时间检查（所有事件类型）- 这是最重要的过滤
        # 获取带时区的事件时间
        event_time_aware = self._get_event_time(event)

        if event_time_aware:
            # 使用UTC当前时间进行比较，确保时区无关性
            current_time_utc = datetime.now(timezone.utc)
            time_diff = (
                current_time_utc - event_time_aware
            ).total_seconds() / 3600  # 小时

            if time_diff > 1:
                return reject(
                    "事件时间过早",
                    f"[灾害预警] 事件时间过早（{time_diff:.1f}小时前），过滤",
                )

        source_id = self._get_source_id(event)
        data_sources_cfg = runtime_config.get("data_sources", {})
        if not is_source_enabled_in_data_sources(source_id, data_sources_cfg):
            return reject(
                "会话数据源开关关闭",
                f"[灾害预警] 会话 {session_id or 'global'} 已禁用数据源 {source_id}，跳过推送",
            )

        # 2. 非地震事件检查
        if not isinstance(event.data, EarthquakeData):
            # 气象预警事件需要进行过滤
            if isinstance(event.data, WeatherAlarmData):
                title_text = event.data.title or event.data.headline or ""
                if runtime_components["weather_filter"].should_filter(
                    title_text, event.data.headline or ""
                ):
                    return reject("气象关键字过滤")
            # 海啸和气象事件通过了过滤，可以推送
            return True

        # 3. 地震事件专用过滤逻辑
        earthquake = event.data

        # 通用关键词过滤 (适用于所有地震事件)
        if runtime_components["keyword_filter"].should_filter(earthquake):
            return reject(
                "关键词过滤",
                f"[灾害预警] 事件被关键词过滤器过滤: {source_id}",
            )

        # 数据源专用过滤器
        if source_id == "global_quake":
            # Global Quake专用过滤器
            if runtime_components["global_quake_filter"].should_filter(earthquake):
                return reject(
                    "Global Quake过滤器",
                    "[灾害预警] 事件被Global Quake过滤器过滤",
                )
        elif source_id in get_intensity_based_sources():
            # 使用烈度过滤器
            if runtime_components["intensity_filter"].should_filter(earthquake):
                return reject(
                    "烈度过滤器",
                    f"[灾害预警] 事件被烈度过滤器过滤: {source_id}",
                )
        elif source_id in get_scale_based_sources():
            # 使用震度过滤器
            if runtime_components["scale_filter"].should_filter(earthquake):
                return reject(
                    "震度过滤器",
                    f"[灾害预警] 事件被震度过滤器过滤: {source_id}",
                )
        elif source_id == "usgs_fanstudio":
            # USGS专用过滤器
            if runtime_components["usgs_filter"].should_filter(earthquake):
                return reject("USGS过滤器", "[灾害预警] 事件被USGS过滤器过滤")

        # 报数控制（仅EEW数据源）
        if not runtime_components["report_controller"].should_push_report(event):
            return reject(
                "报数控制器",
                f"[灾害预警] 事件被报数控制器过滤: {source_id}",
            )

        # 本地烈度过滤与注入（使用统一的辅助方法）
        result = runtime_components["local_monitor"].inject_local_estimation(earthquake)
        # result 为 None 表示未启用，否则检查 is_allowed
        if result is not None and not result.get("is_allowed", True):
            return reject("本地监控过滤")

        return True

    def _get_event_time(self, event: DisasterEvent) -> datetime | None:
        """获取灾害事件的带时区时间 (Aware Datetime)"""
        raw_time = None
        if isinstance(event.data, EarthquakeData):
            raw_time = event.data.shock_time
        elif isinstance(event.data, TsunamiData):
            raw_time = event.data.issue_time
        elif isinstance(event.data, WeatherAlarmData):
            raw_time = event.data.effective_time or event.data.issue_time

        if not raw_time:
            return None

        # 如果已经是Aware时间，直接返回
        if raw_time.tzinfo is not None:
            return raw_time

        # 根据数据源ID确定时区
        source_id = event.source_id or self._get_source_id(event)

        # 定义时区
        # JST (UTC+9)
        tz_jst = timezone(timedelta(hours=9))
        # CST (UTC+8)
        tz_cst = timezone(timedelta(hours=8))
        # UTC
        tz_utc = timezone.utc

        # 1. UTC+9 数据源
        # - Fan Studio JMA
        # - P2P Quake (所有)
        # - Wolfx JMA
        if (
            "jma" in source_id
            or "p2p" in source_id
            or source_id == "wolfx_jma_eew"
            or source_id == "wolfx_jma_eq"
        ):
            return raw_time.replace(tzinfo=tz_jst)

        # 2. UTC 数据源
        # - Global Quake
        if "global_quake" in source_id:
            return raw_time.replace(tzinfo=tz_utc)

        # 3. UTC+8 数据源 (默认)
        # - Fan Studio (除了 JMA, USGS已转为UTC+8)
        # - Wolfx (除了 JMA)
        # - China Weather/Tsunami
        return raw_time.replace(tzinfo=tz_cst)

    def _get_source_id(self, event: DisasterEvent) -> str:
        """获取事件的数据源ID"""
        # 动态生成反向映射：从 DataSource 枚举值映射回简短 ID
        # 这样只要在 models/models.py 的 DATA_SOURCE_MAPPING 中注册了，这里就会自动同步
        reverse_mapping = {v.value: k for k, v in DATA_SOURCE_MAPPING.items()}
        return reverse_mapping.get(event.source.value, event.source.value)

    async def push_event(
        self,
        event: DisasterEvent,
        target_sessions: list[str] | None = None,
        session_config_getter=None,
    ) -> bool:
        """推送事件入口"""
        source_id = self._get_source_id(event)

        strategies_cfg = self.config.get("strategies", {})

        # CENC 融合策略配置
        cenc_fusion_config = strategies_cfg.get("cenc_fusion", {})
        cenc_fusion_enabled = cenc_fusion_config.get("enabled", False)

        # CWA EEW 融合策略配置
        cwa_eew_fusion_config = strategies_cfg.get("cwa_eew_fusion", {})
        cwa_eew_fusion_enabled = cwa_eew_fusion_config.get("enabled", False)

        # 策略分支 1: Fan CENC 消息 -> 拦截并等待
        if cenc_fusion_enabled and source_id == "cenc_fanstudio":
            return await self._handle_cenc_fan_interception(
                event,
                cenc_fusion_config.get("timeout", 10),
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        # 策略分支 2: Wolfx CENC 消息 -> 尝试融合
        if cenc_fusion_enabled and source_id == "cenc_wolfx":
            self._handle_cenc_wolfx_fusion(event)
            # 无论是否融合成功，Wolfx 消息本身不再推送（因为它只作为补充数据或被视为重复）
            return False

        # 策略分支 3: Fan CWA EEW 消息 -> 拦截并等待
        if cwa_eew_fusion_enabled and source_id == "cwa_fanstudio":
            return await self._handle_cwa_fan_interception(
                event,
                cwa_eew_fusion_config.get("timeout", 6),
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        # 策略分支 4: Wolfx CWA EEW 消息 -> 尝试融合
        if cwa_eew_fusion_enabled and source_id == "cwa_wolfx":
            self._handle_cwa_wolfx_fusion(event)
            # 无论是否融合成功，Wolfx 消息本身不再推送（因为它只作为补充数据或被视为重复）
            return False

        # 默认流程
        return await self._execute_push(
            event,
            target_sessions=target_sessions,
            session_config_getter=session_config_getter,
        )

    @staticmethod
    def _get_fusion_event_key(data: EarthquakeData) -> str:
        """融合事件键：优先 event_id，回退 id。"""
        return str(getattr(data, "event_id", "") or getattr(data, "id", "")).strip()

    @staticmethod
    def _get_fusion_report_num(data: EarthquakeData) -> int:
        """融合报次：非正整数时回退为 1。"""
        raw = getattr(data, "updates", 1)
        try:
            report_num = int(raw)
        except (TypeError, ValueError):
            return 1
        return report_num if report_num > 0 else 1

    @staticmethod
    def _select_cached_report_payload(
        reports: dict[int, dict[str, Any]], target_report: int
    ) -> dict[str, Any] | None:
        """按报次精确匹配缓存（仅同报次融合）。"""
        if not reports:
            return None

        return reports.get(target_report)

    def _find_best_pending_key(
        self, pending_dict: dict[str, dict[str, Any]], event_key: str, report_num: int
    ) -> str | None:
        """在同 event_key 的 pending 中按报次精确匹配。"""
        exact = [
            (k, v)
            for k, v in pending_dict.items()
            if isinstance(v, dict)
            and v.get("event_key") == event_key
            and int(v.get("report_num", 1) or 1) == report_num
        ]
        if not exact:
            return None

        exact.sort(key=lambda item: float(item[1].get("created_at", 0.0)))
        return exact[0][0]

    def _prune_fusion_states(self) -> None:
        """清理融合 pending 与缓存中过期条目。"""
        now_ts = time.time()
        ttl = self._fusion_cache_ttl_seconds

        # 1) 清理 pending（过期视为超时）
        for pending_dict in [self.cenc_pending, self.cwa_eew_pending]:
            expired_keys = []
            for pending_key, item in pending_dict.items():
                if not isinstance(item, dict):
                    expired_keys.append(pending_key)
                    continue
                created_at = float(item.get("created_at", 0.0) or 0.0)
                if created_at > 0 and (now_ts - created_at) > ttl:
                    future = item.get("future")
                    if (
                        future is not None
                        and hasattr(future, "done")
                        and not future.done()
                    ):
                        future.set_result("timeout")
                    expired_keys.append(pending_key)
            for pending_key in expired_keys:
                pending_dict.pop(pending_key, None)

        # 2) 清理 Wolfx 缓存
        for cache_dict in [self.cenc_wolfx_cache, self.cwa_eew_wolfx_cache]:
            expired_event_keys = []
            for event_key, reports in cache_dict.items():
                if not isinstance(reports, dict):
                    expired_event_keys.append(event_key)
                    continue

                expired_reports = []
                for report_num, payload in reports.items():
                    created_at = 0.0
                    if isinstance(payload, dict):
                        created_at = float(payload.get("created_at", 0.0) or 0.0)
                    if created_at > 0 and (now_ts - created_at) > ttl:
                        expired_reports.append(report_num)

                for report_num in expired_reports:
                    reports.pop(report_num, None)

                if not reports:
                    expired_event_keys.append(event_key)

            for event_key in expired_event_keys:
                cache_dict.pop(event_key, None)

    async def _handle_cenc_fan_interception(
        self,
        event: DisasterEvent,
        timeout: int,
        target_sessions: list[str] | None = None,
        session_config_getter=None,
    ) -> bool:
        """处理 Fan CENC 消息拦截（支持 Wolfx 先到缓存）。"""
        if not isinstance(event.data, EarthquakeData):
            return await self._execute_push(
                event,
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        self._prune_fusion_states()

        event_key = self._get_fusion_event_key(event.data)
        report_num = self._get_fusion_report_num(event.data)

        # 先尝试命中已缓存 Wolfx 数据（处理 Wolfx 先到场景）
        cached_payload = self._select_cached_report_payload(
            self.cenc_wolfx_cache.get(event_key, {}), report_num
        )
        if (
            isinstance(cached_payload, dict)
            and cached_payload.get("intensity") is not None
        ):
            event.data.intensity = cached_payload["intensity"]
            logger.info(
                f"[灾害预警] 融合策略: Fan CENC 事件 {event.id} 命中 Wolfx 缓存并补充烈度: {event.data.intensity}"
            )
            return await self._execute_push(
                event,
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        logger.info(
            f"[灾害预警] 融合策略: 拦截 Fan CENC 事件 {event.id} (event_key={event_key}, report={report_num})，等待 Wolfx 补充 ({timeout}s)..."
        )

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        pending_key = f"{event_key}#{report_num}#{event.id}#{int(time.time() * 1000)}"

        self.cenc_pending[pending_key] = {
            "event": event,
            "future": future,
            "event_key": event_key,
            "report_num": report_num,
            "created_at": time.time(),
        }

        async def wait_timeout():
            try:
                await asyncio.sleep(timeout)
                if not future.done():
                    future.set_result("timeout")
            except Exception as e:
                if not future.done():
                    future.set_exception(e)

        asyncio.create_task(wait_timeout())

        try:
            result = await future
            self.cenc_pending.pop(pending_key, None)

            if result == "timeout":
                logger.info("[灾害预警] 融合策略: CENC 等待超时，推送原始 Fan 事件")
                return await self._execute_push(
                    event,
                    target_sessions=target_sessions,
                    session_config_getter=session_config_getter,
                )
            if result == "fused":
                logger.info("[灾害预警] 融合策略: CENC 融合完成，推送补充后的 Fan 事件")
                return await self._execute_push(
                    event,
                    target_sessions=target_sessions,
                    session_config_getter=session_config_getter,
                )

        except Exception as e:
            logger.error(f"[灾害预警] CENC 融合策略处理异常: {e}")
            return await self._execute_push(
                event,
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        return False

    def _handle_cenc_wolfx_fusion(self, wolfx_event: DisasterEvent):
        """处理 Wolfx CENC 消息融合（缓存优先 + 精确匹配）。"""
        if not isinstance(wolfx_event.data, EarthquakeData):
            return

        intensity = getattr(wolfx_event.data, "intensity", None)
        if intensity is None:
            return

        self._prune_fusion_states()

        event_key = self._get_fusion_event_key(wolfx_event.data)
        report_num = self._get_fusion_report_num(wolfx_event.data)
        if not event_key:
            return

        event_cache = self.cenc_wolfx_cache.setdefault(event_key, {})
        event_cache[report_num] = {"intensity": intensity, "created_at": time.time()}

        pending_key = self._find_best_pending_key(
            self.cenc_pending, event_key, report_num
        )
        if not pending_key:
            return

        try:
            item = self.cenc_pending.get(pending_key)
            if not isinstance(item, dict):
                return

            fan_event = item.get("event")
            future = item.get("future")
            if not isinstance(fan_event, DisasterEvent) or not isinstance(
                fan_event.data, EarthquakeData
            ):
                return

            fan_event.data.intensity = intensity
            logger.info(
                f"[灾害预警] 融合策略: 成功用 Wolfx 补充 Fan CENC 事件 {pending_key} 的烈度: {intensity}"
            )

            if future is not None and hasattr(future, "done") and not future.done():
                future.set_result("fused")

            self.cenc_pending.pop(pending_key, None)

        except Exception as e:
            logger.error(f"[灾害预警] CENC 融合操作失败: {e}")

    async def _handle_cwa_fan_interception(
        self,
        event: DisasterEvent,
        timeout: int,
        target_sessions: list[str] | None = None,
        session_config_getter=None,
    ) -> bool:
        """处理 Fan CWA EEW 消息拦截（支持 Wolfx 先到缓存与报次错位补充）。"""
        if not isinstance(event.data, EarthquakeData):
            return await self._execute_push(
                event,
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        self._prune_fusion_states()

        event_key = self._get_fusion_event_key(event.data)
        report_num = self._get_fusion_report_num(event.data)

        # 先尝试命中已缓存 Wolfx 数据（处理 Wolfx 先到场景）
        cached_payload = self._select_cached_report_payload(
            self.cwa_eew_wolfx_cache.get(event_key, {}), report_num
        )
        if isinstance(cached_payload, dict) and cached_payload.get("impact_area"):
            impact_area = str(cached_payload["impact_area"]).strip()
            if impact_area:
                if not isinstance(event.data.raw_data, dict):
                    event.data.raw_data = {}
                event.data.raw_data["wolfx_impact_area"] = impact_area
                if not getattr(event.data, "province", None):
                    event.data.province = impact_area
                logger.info(
                    f"[灾害预警] 融合策略: Fan CWA EEW 事件 {event.id} 命中 Wolfx 缓存并补充影响区域: {impact_area}"
                )
                return await self._execute_push(
                    event,
                    target_sessions=target_sessions,
                    session_config_getter=session_config_getter,
                )

        logger.info(
            f"[灾害预警] 融合策略: 拦截 Fan CWA EEW 事件 {event.id} (event_key={event_key}, report={report_num})，等待 Wolfx 补充 ({timeout}s)..."
        )

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        pending_key = f"{event_key}#{report_num}#{event.id}#{int(time.time() * 1000)}"

        self.cwa_eew_pending[pending_key] = {
            "event": event,
            "future": future,
            "event_key": event_key,
            "report_num": report_num,
            "created_at": time.time(),
        }

        async def wait_timeout():
            try:
                await asyncio.sleep(timeout)
                if not future.done():
                    future.set_result("timeout")
            except Exception as e:
                if not future.done():
                    future.set_exception(e)

        asyncio.create_task(wait_timeout())

        try:
            result = await future
            self.cwa_eew_pending.pop(pending_key, None)

            if result == "timeout":
                logger.info("[灾害预警] 融合策略: CWA EEW 等待超时，推送原始 Fan 事件")
                return await self._execute_push(
                    event,
                    target_sessions=target_sessions,
                    session_config_getter=session_config_getter,
                )
            if result == "fused":
                logger.info(
                    "[灾害预警] 融合策略: CWA EEW 融合完成，推送补充后的 Fan 事件"
                )
                return await self._execute_push(
                    event,
                    target_sessions=target_sessions,
                    session_config_getter=session_config_getter,
                )

        except Exception as e:
            logger.error(f"[灾害预警] CWA EEW 融合策略处理异常: {e}")
            return await self._execute_push(
                event,
                target_sessions=target_sessions,
                session_config_getter=session_config_getter,
            )

        return False

    def _extract_cwa_wolfx_impact_area(
        self, wolfx_earthquake: EarthquakeData
    ) -> str | None:
        """提取 Wolfx CWA EEW 影响区域字段。"""
        raw_data = getattr(wolfx_earthquake, "raw_data", {})
        if not isinstance(raw_data, dict):
            raw_data = {}

        def _normalize_area(value: Any) -> str:
            if isinstance(value, list):
                parts = [str(x).strip() for x in value if str(x).strip()]
                return "、".join(parts)
            if isinstance(value, str):
                return value.strip()
            return ""

        if getattr(wolfx_earthquake, "province", None):
            province_text = str(wolfx_earthquake.province).strip()
            if province_text:
                return province_text

        candidates: list[Any] = [
            raw_data.get("locationDesc"),
            raw_data.get("impactArea"),
            raw_data.get("ImpactArea"),
            raw_data.get("affectedArea"),
            raw_data.get("AffectedArea"),
            raw_data.get("area"),
            raw_data.get("Area"),
        ]

        warn_area = raw_data.get("WarnArea")
        if isinstance(warn_area, dict):
            candidates.extend(
                [
                    warn_area.get("Chiiki"),
                    warn_area.get("Area"),
                    warn_area.get("AreaName"),
                    warn_area.get("Name"),
                    warn_area.get("County"),
                ]
            )
        else:
            candidates.append(warn_area)

        for candidate in candidates:
            normalized = _normalize_area(candidate)
            if normalized:
                return normalized

        return None

    def _handle_cwa_wolfx_fusion(self, wolfx_event: DisasterEvent):
        """处理 Wolfx CWA EEW 消息融合（缓存优先 + 精确匹配）。"""
        if not isinstance(wolfx_event.data, EarthquakeData):
            return

        impact_area = self._extract_cwa_wolfx_impact_area(wolfx_event.data)
        if not impact_area:
            return

        self._prune_fusion_states()

        event_key = self._get_fusion_event_key(wolfx_event.data)
        report_num = self._get_fusion_report_num(wolfx_event.data)
        if not event_key:
            return

        event_cache = self.cwa_eew_wolfx_cache.setdefault(event_key, {})
        event_cache[report_num] = {
            "impact_area": impact_area,
            "created_at": time.time(),
        }

        pending_key = self._find_best_pending_key(
            self.cwa_eew_pending, event_key, report_num
        )
        if not pending_key:
            return

        try:
            item = self.cwa_eew_pending.get(pending_key)
            if not isinstance(item, dict):
                return

            fan_event = item.get("event")
            future = item.get("future")
            if not isinstance(fan_event, DisasterEvent) or not isinstance(
                fan_event.data, EarthquakeData
            ):
                return

            if not isinstance(fan_event.data.raw_data, dict):
                fan_event.data.raw_data = {}

            fan_event.data.raw_data["wolfx_impact_area"] = impact_area
            if not getattr(fan_event.data, "province", None):
                fan_event.data.province = impact_area

            logger.info(
                f"[灾害预警] 融合策略: 成功用 Wolfx 补充 Fan CWA EEW 事件 {pending_key} 的影响区域: {impact_area}"
            )

            if future is not None and hasattr(future, "done") and not future.done():
                future.set_result("fused")

            self.cwa_eew_pending.pop(pending_key, None)

        except Exception as e:
            logger.error(f"[灾害预警] CWA EEW 融合操作失败: {e}")

    async def _execute_push(
        self,
        event: DisasterEvent,
        target_sessions: list[str] | None = None,
        session_config_getter=None,
    ) -> bool:
        """执行实际的推送流程（原 push_event 逻辑）"""
        logger.debug(f"[灾害预警] 执行事件推送流程: {event.id}")
        source_id = self._get_source_id(event)

        # 1. 先去重检查 - 允许多数据源推送同一事件
        if not self.deduplicator.should_push_event(event):
            logger.debug(f"[灾害预警] 事件 {event.id} 被去重器过滤")
            return False

        try:
            self.last_success_sessions = []

            # 2. 获取目标会话
            sessions = (
                target_sessions
                if target_sessions is not None
                else self.config.get("target_sessions", [])
            )
            if not sessions:
                logger.warning("[灾害预警] 没有配置目标会话，无法推送消息")
                return False

            # 3. 推送消息
            push_success_count = 0
            passed_sessions: list[str] = []
            session_message_format_config: dict[str, dict[str, Any]] = {}
            filter_reason_stats: dict[str, int] = {}

            # 先做会话筛选（轻量，同步执行）
            push_candidates: list[tuple[str, dict[str, Any]]] = []
            for session in sessions:
                runtime_config = (
                    session_config_getter(session)
                    if callable(session_config_getter)
                    else self.config
                )
                if not isinstance(runtime_config, dict):
                    runtime_config = self.config

                if runtime_config.get("push_enabled", True) is False:
                    logger.debug(f"[灾害预警] 会话 {session} 推送开关关闭，跳过")
                    continue

                filter_reasons: list[str] = []
                if not self.should_push_event(
                    event,
                    runtime_config=runtime_config,
                    session_id=session,
                    filter_reason_out=filter_reasons,
                    emit_filter_log=False,
                ):
                    reason = filter_reasons[0] if filter_reasons else "未通过推送条件"
                    filter_reason_stats[reason] = filter_reason_stats.get(reason, 0) + 1
                    logger.debug(
                        f"[灾害预警] 事件 {event.id} 未通过会话 {session} 的推送条件检查: {reason}"
                    )
                    continue

                push_candidates.append((session, runtime_config))

            # 构建任务级消息缓存：同一个事件 + 同一渲染参数只构建一次消息
            message_task_cache: dict[str, asyncio.Task[MessageChain]] = {}
            message_task_lock = asyncio.Lock()

            async def get_or_build_message(
                runtime_config: dict[str, Any],
            ) -> MessageChain:
                cache_key = self._build_message_build_cache_key(event, runtime_config)
                task = message_task_cache.get(cache_key)
                if task is None:
                    async with message_task_lock:
                        task = message_task_cache.get(cache_key)
                        if task is None:
                            task = asyncio.create_task(
                                self.build_message_async(
                                    event, runtime_config=runtime_config
                                )
                            )
                            message_task_cache[cache_key] = task
                return await task

            async def push_to_session(
                session: str,
                runtime_config: dict[str, Any],
            ) -> tuple[bool, str, dict[str, Any] | None]:
                try:
                    message = await get_or_build_message(runtime_config)
                    await self._send_message(session, message)
                    logger.info(f"[灾害预警] 消息已推送到 {session}")
                    return True, session, runtime_config.get("message_format", {})
                except Exception as e:
                    logger.error(f"[灾害预警] 推送到 {session} 失败: {e}")
                    return False, session, None

            # 并发推送：不同会话互不阻塞
            if push_candidates:
                push_tasks = [
                    asyncio.create_task(push_to_session(session, runtime_config))
                    for session, runtime_config in push_candidates
                ]
                push_results = await asyncio.gather(*push_tasks, return_exceptions=True)

                for result in push_results:
                    if isinstance(result, Exception):
                        logger.error(f"[灾害预警] 会话推送任务异常: {result}")
                        continue

                    ok, session, msg_cfg = result
                    if ok:
                        push_success_count += 1
                        passed_sessions.append(session)
                        session_message_format_config[session] = msg_cfg or {}

            # 6. 异步处理分离的地图瓦片 (针对 EEW 数据源的优化)
            split_map_sources = set(get_eew_sources()) - {"global_quake"}
            if source_id in split_map_sources and isinstance(
                event.data, EarthquakeData
            ):
                # 频率控制逻辑：参考报数控制器，第1报必推，之后每5报推一次，最终报必推
                current_report = getattr(event.data, "updates", 1)
                is_final = getattr(event.data, "is_final", False)

                # 地图瓦片报数控制频率固定为 5 (暂时硬编码)
                map_push_n = 5

                should_gen_map = False
                if current_report == 1 or current_report % map_push_n == 0 or is_final:
                    should_gen_map = True

                if should_gen_map and passed_sessions:
                    logger.debug(
                        f"[灾害预警] 触发异步地图渲染 (第 {current_report} 报)"
                    )

                    # 按 message_format 配置分组发送地图
                    grouped_sessions: dict[str, list[str]] = {}
                    grouped_config: dict[str, dict[str, Any]] = {}
                    for session in passed_sessions:
                        msg_cfg = session_message_format_config.get(session, {})
                        include_map = msg_cfg.get("include_map", False)
                        if not include_map:
                            continue
                        k = json.dumps(msg_cfg, sort_keys=True, ensure_ascii=False)
                        if k not in grouped_sessions:
                            grouped_sessions[k] = []
                            grouped_config[k] = msg_cfg
                        grouped_sessions[k].append(session)

                    for k, grouped in grouped_sessions.items():
                        asyncio.create_task(
                            self._push_split_map(
                                event,
                                grouped,
                                grouped_config[k],
                            )
                        )

            # 7. 记录推送
            self.last_success_sessions = list(passed_sessions)
            if filter_reason_stats:
                summary = "，".join(
                    f"{reason}×{count}"
                    for reason, count in sorted(filter_reason_stats.items())
                )
                if push_success_count > 0:
                    logger.debug(
                        f"[灾害预警] 事件 {event.id} 部分会话被过滤: {summary}"
                    )
                else:
                    logger.info(
                        f"[灾害预警] 事件 {event.id} 已被会话过滤拦截: {summary}"
                    )
            if push_success_count > 0:
                logger.info(
                    f"[灾害预警] 事件 {event.id} 推送完成，成功推送到 {push_success_count} 个会话"
                )
            return push_success_count > 0

        except Exception as e:
            logger.error(f"[灾害预警] 推送事件失败: {e}")
            # 上报推送失败错误到遥测
            if self._telemetry and self._telemetry.enabled:
                await self._telemetry.track_error(
                    e, module="core.message_manager._execute_push"
                )
            return False

    async def _push_split_map(
        self, event: DisasterEvent, target_sessions: list[str], config: dict
    ):
        """后台渲染并发送分离的地图图片"""
        try:
            lat, lon = event.data.latitude, event.data.longitude
            # 再次检查坐标有效性
            if (
                lat is None
                or lon is None
                or not (-90 <= lat <= 90)
                or not (-180 <= lon <= 180)
            ):
                return

            # 开始渲染（可能耗时数秒）
            map_image_path = await self._render_map_image(lat, lon, config)
            if not map_image_path or not os.path.exists(map_image_path):
                return

            # 转为 Base64 并构建图片消息
            with open(map_image_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode()

            map_message = MessageChain([Comp.Image.fromBase64(b64_data)])

            # 发送到所有目标会话
            for session in target_sessions:
                try:
                    await self._send_message(session, map_message)
                    logger.debug(f"[灾害预警] 分离地图已发送到 {session}")
                except Exception as e:
                    logger.error(f"[灾害预警] 分离地图发送到 {session} 失败: {e}")

        except Exception as e:
            logger.error(f"[灾害预警] 异步地图渲染任务失败: {e}")

    def _build_message(self, event: DisasterEvent) -> MessageChain:
        """构建消息 - 使用格式化器并应用消息格式配置（向后兼容）"""
        source_id = self._get_source_id(event)
        message_format_config = self.config.get("message_format", {})

        # 获取基础文本消息
        chain = self._build_text_message(event, source_id, message_format_config)
        return chain

    async def build_message_async(
        self,
        event: DisasterEvent,
        runtime_config: dict[str, Any] | None = None,
    ) -> MessageChain:
        """构建消息 (异步版本) - 支持卡片渲染"""
        active_config = runtime_config or self.config
        source_id = self._get_source_id(event)
        message_format_config = active_config.get("message_format", {})

        # 1. Global Quake 卡片处理逻辑
        use_gq_card = message_format_config.get("use_global_quake_card", False)
        if (
            source_id == "global_quake"
            and use_gq_card
            and isinstance(event.data, EarthquakeData)
        ):
            try:
                # 渲染 Global Quake 卡片
                display_timezone = active_config.get("display_timezone", "UTC+8")
                options = {"timezone": display_timezone}
                context = GlobalQuakeFormatter.get_render_context(event.data, options)

                # 注入自定义缩放级别，默认设为 5
                zoom_level = message_format_config.get("map_zoom_level", 5)
                context["zoom_level"] = zoom_level

                # 注入地图源配置
                map_source = message_format_config.get("map_source", "PetalMap矢量图亮")
                context["map_source"] = map_source
                # 注入完整的瓦片URL（处理特殊格式）
                context["tile_url"] = get_tile_url_js(map_source)

                # 获取模板名称配置
                template_name = message_format_config.get(
                    "global_quake_template", "Aurora"
                )

                # 加载模板
                resources_dir = os.path.join(self.plugin_root, "resources")
                template_path = os.path.join(
                    resources_dir, "card_templates", template_name, "global_quake.html"
                )

                if not os.path.exists(template_path):
                    logger.error(f"[灾害预警] 找不到模板文件: {template_path}")
                else:
                    with open(template_path, encoding="utf-8") as f:
                        template_content = f.read()

                    # 根据 playwright 模式选择资源 URL
                    playwright_mode = active_config.get("message_format", {}).get(
                        "playwright_mode", "local"
                    )
                    if playwright_mode == "remote":
                        # 远程模式：使用 CDN
                        context["leaflet_js_url"] = (
                            "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
                        )
                        context["leaflet_css_url"] = (
                            "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
                        )
                    else:
                        # 本地模式：使用本地文件
                        leaflet_path = os.path.abspath(
                            os.path.join(resources_dir, "card_templates", "leaflet.js")
                        )
                        leaflet_css_path = os.path.abspath(
                            os.path.join(resources_dir, "card_templates", "leaflet.css")
                        )
                        context["leaflet_js_url"] = f"file://{leaflet_path}"
                        context["leaflet_css_url"] = f"file://{leaflet_css_path}"

                    # 共享渲染 helper 统一以内联脚本注入，避免远程模式下的静态资源可达性问题
                    map_helper_path = os.path.abspath(
                        os.path.join(
                            resources_dir, "card_templates", "map_render_helper.js"
                        )
                    )
                    with open(map_helper_path, encoding="utf-8") as helper_file:
                        context["map_render_helper_js"] = helper_file.read()

                    # Jinja2 渲染
                    template = Template(template_content)
                    html_content = template.render(**context)

                    # 准备临时文件路径
                    card_cache_key = self._build_global_quake_card_cache_key(
                        event.data,
                        message_format_config,
                        display_timezone,
                    )

                    async def render_gq_card() -> str | None:
                        image_filename = f"gq_card_{event.data.id}_{int(datetime.now().timestamp())}.png"
                        image_path = os.path.join(self.temp_dir, image_filename)
                        return await self.browser_manager.render_card(
                            html_content, image_path, selector="#card-wrapper"
                        )

                    result_path = await self._render_with_cache(
                        card_cache_key,
                        render_gq_card,
                    )

                    if result_path and os.path.exists(result_path):
                        # 核心修复点：将图片转换为 base64 避免路径兼容性问题
                        try:
                            with open(result_path, "rb") as f:
                                b64_data = base64.b64encode(f.read()).decode()
                            chain = [Comp.Image.fromBase64(b64_data)]
                            return MessageChain(chain)
                        except Exception as e:
                            logger.error(f"[灾害预警] 读取图片转换为Base64失败: {e}")
                    else:
                        logger.warning("[灾害预警] Global Quake 卡片渲染失败")

            except Exception as e:
                logger.error(
                    f"[灾害预警] Global Quake 卡片渲染失败: {e}，回退到文本模式"
                )

        # 2. 通用文本消息构建 (包含新的瓦片地图图片逻辑)

        # 获取基础文本消息
        chain = self._build_text_message(
            event,
            source_id,
            message_format_config,
            full_config=active_config,
        )

        # 3. 检查是否需要附加地图图片
        include_map = message_format_config.get("include_map", False)

        # 动态获取所有 EEW 数据源，但排除掉使用独立卡片渲染的 global_quake
        split_map_sources = set(get_eew_sources()) - {"global_quake"}

        if include_map and isinstance(event.data, EarthquakeData):
            # 如果是需要分离发送的数据源，则在此跳过同步附加图片，改为在 _execute_push 中后台处理
            if source_id in split_map_sources:
                logger.debug(
                    f"[灾害预警] 数据源 {source_id} 属于分离地图发送类型，跳过同步附加"
                )
            else:
                # 经纬度有效性检查：纬度 [-90, 90], 经度 [-180, 180]
                lat_valid = (
                    event.data.latitude is not None and -90 <= event.data.latitude <= 90
                )
                lon_valid = (
                    event.data.longitude is not None
                    and -180 <= event.data.longitude <= 180
                )

                if lat_valid and lon_valid:
                    try:
                        map_image_path = await self._render_map_image(
                            event.data.latitude,
                            event.data.longitude,
                            message_format_config,
                        )
                        if map_image_path:
                            # 核心修复点：使用 base64 替代文件路径，彻底解决 Windows 下 file:// 协议兼容性问题
                            try:
                                with open(map_image_path, "rb") as f:
                                    b64_data = base64.b64encode(f.read()).decode()
                                chain.chain.append(Comp.Image.fromBase64(b64_data))
                                logger.debug("[灾害预警] 已附加地图图片 (Base64模式)")
                            except Exception as b64_err:
                                logger.error(
                                    f"[灾害预警] 地图图片转Base64失败: {b64_err}"
                                )
                    except Exception as e:
                        logger.error(f"[灾害预警] 地图图片生成失败: {e}")

        # 4. 检查是否需要附加气象预警图标
        weather_config = active_config.get("weather_config", {})
        enable_weather_icon = weather_config.get("enable_weather_icon", True)
        if enable_weather_icon and isinstance(event.data, WeatherAlarmData):
            p_code = event.data.type
            if p_code:
                # 拼接中国气象局官方图标 URL
                icon_url = f"https://image.nmc.cn/assets/img/alarm/{p_code}.png"
                try:
                    chain.chain.append(Comp.Image.fromURL(icon_url))
                    logger.debug(f"[灾害预警] 已附加气象预警图标: {icon_url}")
                except Exception as e:
                    logger.error(f"[灾害预警] 附加气象预警图标失败: {e}")

        # 5. 海啸图件：优先尝试直接渲染 URL 图片（失败时文本消息中仍保留 URL 兜底）
        if isinstance(event.data, TsunamiData):
            map_urls = getattr(event.data, "map_urls", {}) or {}
            if isinstance(map_urls, dict):
                for map_key in ["earthquake", "amplitude", "coastal"]:
                    map_url = map_urls.get(map_key)
                    if isinstance(map_url, str) and map_url.strip():
                        try:
                            chain.chain.append(Comp.Image.fromURL(map_url.strip()))
                            logger.debug(
                                f"[灾害预警] 已附加海啸图件: {map_key} -> {map_url}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"[灾害预警] 附加海啸图件失败 ({map_key}): {e}"
                            )

        # 6. CWA 地震报告图件：优先尝试直接渲染 URL 图片（失败时文本消息中仍保留 URL 兜底）
        if source_id == "cwa_fanstudio_report" and isinstance(
            event.data, EarthquakeData
        ):
            report_image_urls: list[str] = []
            for image_url in [
                getattr(event.data, "image_uri", None),
                getattr(event.data, "shakemap_uri", None),
            ]:
                if isinstance(image_url, str):
                    normalized_url = image_url.strip()
                    if normalized_url and normalized_url not in report_image_urls:
                        report_image_urls.append(normalized_url)

            for image_url in report_image_urls:
                try:
                    chain.chain.append(Comp.Image.fromURL(image_url))
                    logger.debug(f"[灾害预警] 已附加 CWA 地震报告图件: {image_url}")
                except Exception as e:
                    logger.warning(f"[灾害预警] 附加 CWA 地震报告图件失败: {e}")

        return chain

    def _build_text_message(
        self,
        event,
        source_id,
        config,
        full_config: dict[str, Any] | None = None,
    ) -> MessageChain:
        """构建纯文本部分的消息"""
        active_config = full_config or self.config
        display_timezone = active_config.get("display_timezone", "UTC+8")
        detailed_jma = config.get("detailed_jma_intensity", False)

        if isinstance(event.data, WeatherAlarmData):
            weather_config = active_config.get("weather_config", {})
            options = {
                "max_description_length": weather_config.get(
                    "max_description_length", 384
                ),
                "timezone": display_timezone,
            }
            message_text = format_weather_message(source_id, event.data, options)
        elif isinstance(event.data, TsunamiData):
            options = {"timezone": display_timezone}
            message_text = format_tsunami_message(source_id, event.data, options)
        elif isinstance(event.data, EarthquakeData):
            options = {
                "detailed_jma_intensity": detailed_jma,
                "timezone": display_timezone,
            }
            # 特殊处理 CWA 报告格式化
            if source_id == "cwa_fanstudio_report":
                message_text = CWAReportFormatter.format_message(event.data, options)
            else:
                message_text = format_earthquake_message(source_id, event.data, options)
        else:
            logger.warning(f"[灾害预警] 未知事件类型: {type(event.data)}")
            message_text = f"🚨[未知事件]\n📋事件ID：{event.id}\n⏰时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return MessageChain([Comp.Plain(message_text)])

    async def render_earthquake_list_card(
        self, events: list[dict], source_name: str
    ) -> str | None:
        """渲染地震列表卡片"""
        try:
            # 加载模板
            template_path = os.path.join(
                self.plugin_root,
                "resources",
                "card_templates",
                "Base",
                "earthquake_list.html",
            )

            if not os.path.exists(template_path):
                logger.error(f"[灾害预警] 找不到地震列表模板: {template_path}")
                return None

            with open(template_path, encoding="utf-8") as f:
                template_content = f.read()

            # 准备上下文
            version = get_plugin_version()
            footer_text = (
                f"🔧 @DBJD-CR/astrbot_plugin_disaster_warning (灾害预警) {version}"
            )
            context = {
                "source_name": source_name,
                "events": events,
                "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "footer_text": footer_text,
            }

            # 渲染 HTML
            template = Template(template_content)
            html_content = template.render(**context)

            # 渲染图片
            image_filename = f"eq_list_{int(time.time())}.png"
            image_path = os.path.join(self.temp_dir, image_filename)

            # 使用 BrowserManager 渲染
            result_path = await self.browser_manager.render_card(
                html_content, image_path, selector="#card-wrapper"
            )

            return result_path

        except Exception as e:
            logger.error(f"[灾害预警] 渲染地震列表卡片失败: {e}")
            return None

    async def _render_map_image(
        self, lat: float, lon: float, config: dict
    ) -> str | None:
        """渲染通用地图图片（带缓存复用）。"""

        async def render_map() -> str | None:
            try:
                map_source = config.get("map_source", "PetalMap矢量图亮")
                zoom_level = config.get("map_zoom_level", 5)

                # 加载模板
                resources_dir = os.path.join(self.plugin_root, "resources")
                template_path = os.path.join(
                    resources_dir, "card_templates", "Base", "base_map.html"
                )

                if not os.path.exists(template_path):
                    logger.error(f"[灾害预警] 找不到通用地图模板: {template_path}")
                    return None

                with open(template_path, encoding="utf-8") as f:
                    template_content = f.read()

                # 准备上下文
                leaflet_path = os.path.abspath(
                    os.path.join(resources_dir, "card_templates", "leaflet.js")
                )
                leaflet_css_path = os.path.abspath(
                    os.path.join(resources_dir, "card_templates", "leaflet.css")
                )

                map_helper_path = os.path.abspath(
                    os.path.join(
                        resources_dir, "card_templates", "map_render_helper.js"
                    )
                )
                with open(map_helper_path, encoding="utf-8") as helper_file:
                    map_render_helper_js = helper_file.read()

                # 根据 playwright 模式选择资源 URL
                playwright_mode = config.get("playwright_mode") or self.config.get(
                    "message_format", {}
                ).get("playwright_mode", "local")
                if playwright_mode == "remote":
                    # 远程模式：使用 CDN
                    leaflet_js_url = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
                    leaflet_css_url = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
                else:
                    # 本地模式：使用本地文件
                    leaflet_js_url = f"file://{leaflet_path}"
                    leaflet_css_url = f"file://{leaflet_css_path}"

                context = {
                    "latitude": lat,
                    "longitude": lon,
                    "zoom_level": zoom_level,
                    "map_source": map_source,
                    "tile_url": get_tile_url_js(map_source),
                    "leaflet_js_url": leaflet_js_url,
                    "leaflet_css_url": leaflet_css_url,
                    "map_render_helper_js": map_render_helper_js,
                }

                # 渲染 HTML
                template = Template(template_content)
                html_content = template.render(**context)

                # 渲染图片
                image_filename = f"map_{lat}_{lon}_{int(time.time())}.png"
                image_path = os.path.join(self.temp_dir, image_filename)

                return await self.browser_manager.render_card(
                    html_content, image_path, selector="#card-wrapper"
                )

            except Exception as e:
                logger.error(f"[灾害预警] 渲染地图图片时出错: {e}")
                return None

        map_cache_key = self._build_map_cache_key(lat, lon, config)
        return await self._render_with_cache(map_cache_key, render_map)

    async def _send_message(self, session: str, message: MessageChain):
        """发送消息到指定会话"""
        await self.context.send_message(session, message)

    async def push_system_message(
        self, message: str, target_sessions: list[str] | None = None
    ) -> int:
        """推送系统提示消息（不走事件过滤）"""
        sessions = (
            target_sessions
            if target_sessions is not None
            else self.config.get("target_sessions", [])
        )
        if not sessions:
            logger.warning("[灾害预警] 没有配置目标会话，系统提示消息未发送")
            return 0

        msg_chain = MessageChain([Comp.Plain(message)])
        success_count = 0
        for session in sessions:
            try:
                await self._send_message(session, msg_chain)
                success_count += 1
            except Exception as e:
                logger.error(f"[灾害预警] 系统提示消息发送到 {session} 失败: {e}")

        if success_count > 0:
            logger.info(f"[灾害预警] 系统提示消息已发送到 {success_count} 个会话")
        return success_count

    async def cleanup_browser(self):
        """清理浏览器资源"""
        if self.browser_manager:
            try:
                await self.browser_manager.close()
                logger.debug("[灾害预警] 浏览器管理器已关闭")
            except Exception as e:
                logger.error(f"[灾害预警] 关闭浏览器管理器失败: {e}")

    def cleanup_old_records(self):
        """清理旧记录"""
        # 清理去重器
        self.deduplicator.cleanup_old_events()

        # 清理临时图片文件
        try:
            # 查找所有 PNG 文件
            pattern = os.path.join(self.temp_dir, "*.png")
            files = glob.glob(pattern)

            # 1. 按照修改时间排序
            files.sort(key=os.path.getmtime)

            # 2. 检查数量上限 (默认 256 张)
            max_files = self.config.get("message_format", {}).get(
                "max_temp_images", 256
            )
            if len(files) > max_files:
                to_delete = files[: len(files) - max_files]
                for f in to_delete:
                    try:
                        os.remove(f)
                    except Exception:
                        pass
                logger.info(
                    f"[灾害预警] 临时文件过多，已清理 {len(to_delete)} 个旧文件"
                )
                # 更新处理后的列表
                files = files[len(to_delete) :]

            # 3. 清理超过 3 小时的图片
            expire_time = time.time() - 10800
            for file_path in files:
                try:
                    if os.path.getmtime(file_path) < expire_time:
                        os.remove(file_path)
                        logger.debug(
                            f"[灾害预警] 已清理过期临时图片: {os.path.basename(file_path)}"
                        )
                except Exception as e:
                    logger.warning(f"[灾害预警] 清理文件失败 {file_path}: {e}")

        except Exception as e:
            logger.error(f"[灾害预警] 清理临时文件夹失败: {e}")
