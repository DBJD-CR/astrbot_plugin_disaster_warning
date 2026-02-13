"""
消息推送管理器
实现优化的报数控制、拆分过滤器和改进的去重逻辑
"""

import asyncio
import base64
import glob
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from jinja2 import Template

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.star import StarTools

from ..models.data_source_config import (
    get_eew_sources,
    get_intensity_based_sources,
    get_scale_based_sources,
)
from ..models.models import (
    DATA_SOURCE_MAPPING,
    DisasterEvent,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from ..utils.formatters import (
    CWAReportFormatter,
    GlobalQuakeFormatter,
    format_earthquake_message,
    format_tsunami_message,
    format_weather_message,
)
from ..utils.version import get_plugin_version
from .browser_manager import BrowserManager
from .event_deduplicator import EventDeduplicator
from .filters import (
    GlobalQuakeFilter,
    IntensityFilter,
    KeywordFilter,
    LocalIntensityFilter,
    ReportCountController,
    ScaleFilter,
    USGSFilter,
    WeatherFilter,
)


class MessagePushManager:
    """消息推送管理器"""

    def __init__(self, config: dict[str, Any], context, telemetry=None):
        self.config = config
        self.context = context
        self._telemetry = telemetry
        # 初始化插件根目录 (用于访问 resources)
        self.plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
        msg_config = config.get("message_format", {})
        if msg_config.get("include_map", False) or msg_config.get(
            "use_global_quake_card", False
        ):
            logger.debug("[灾害预警] 检测到已启用卡片渲染功能，正在后台预热浏览器...")
            asyncio.create_task(self.browser_manager.initialize())

        # CENC 融合策略 Pending 列表
        # key: event_id (Fan), value: {'event': event, 'task': asyncio.Task}
        self.cenc_pending = {}

    def should_push_event(self, event: DisasterEvent) -> bool:
        """判断是否应该推送事件"""
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
                logger.info(f"[灾害预警] 事件时间过早（{time_diff:.1f}小时前），过滤")
                return False

        # 2. 非地震事件检查
        if not isinstance(event.data, EarthquakeData):
            # 气象预警事件需要进行过滤
            if isinstance(event.data, WeatherAlarmData):
                headline = event.data.headline or event.data.title or ""
                if self.weather_filter.should_filter(headline):
                    return False
            # 海啸和气象事件通过了过滤，可以推送
            return True

        # 3. 地震事件专用过滤逻辑
        earthquake = event.data
        source_id = self._get_source_id(event)

        # 通用关键词过滤 (适用于所有地震事件)
        if self.keyword_filter.should_filter(earthquake):
            logger.info(f"[灾害预警] 事件被关键词过滤器过滤: {source_id}")
            return False

        # 数据源专用过滤器
        if source_id == "global_quake":
            # Global Quake专用过滤器
            if self.global_quake_filter.should_filter(earthquake):
                logger.info("[灾害预警] 事件被Global Quake过滤器过滤")
                return False
        elif source_id in get_intensity_based_sources():
            # 使用烈度过滤器
            if self.intensity_filter.should_filter(earthquake):
                logger.info(f"[灾害预警] 事件被烈度过滤器过滤: {source_id}")
                return False
        elif source_id in get_scale_based_sources():
            # 使用震度过滤器
            if self.scale_filter.should_filter(earthquake):
                logger.info(f"[灾害预警] 事件被震度过滤器过滤: {source_id}")
                return False
        elif source_id == "usgs_fanstudio":
            # USGS专用过滤器
            if self.usgs_filter.should_filter(earthquake):
                logger.info("[灾害预警] 事件被USGS过滤器过滤")
                return False

        # 报数控制（仅EEW数据源）
        if not self.report_controller.should_push_report(event):
            logger.info(f"[灾害预警] 事件被报数控制器过滤: {source_id}")
            return False

        # 本地烈度过滤与注入（使用统一的辅助方法）
        result = self.local_monitor.inject_local_estimation(earthquake)
        # result 为 None 表示未启用，否则检查 is_allowed
        if result is not None and not result.get("is_allowed", True):
            return False

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

    async def push_event(self, event: DisasterEvent) -> bool:
        """推送事件入口"""
        source_id = self._get_source_id(event)

        # 检查是否启用了 CENC 融合策略
        fusion_config = self.config.get("strategies", {}).get("cenc_fusion", {})
        fusion_enabled = fusion_config.get("enabled", False)

        # 策略分支 1: Fan CENC 消息 -> 拦截并等待
        if fusion_enabled and source_id == "cenc_fanstudio":
            return await self._handle_cenc_fan_interception(
                event, fusion_config.get("timeout", 10)
            )

        # 策略分支 2: Wolfx CENC 消息 -> 尝试融合
        if fusion_enabled and source_id == "cenc_wolfx":
            self._handle_cenc_wolfx_fusion(event)
            # 无论是否融合成功，Wolfx 消息本身不再推送（因为它只作为补充数据或被视为重复）
            return False

        # 默认流程
        return await self._execute_push(event)

    async def _handle_cenc_fan_interception(
        self, event: DisasterEvent, timeout: int
    ) -> bool:
        """处理 Fan CENC 消息拦截"""
        logger.info(
            f"[灾害预警] 融合策略: 拦截 Fan CENC 事件 {event.id}，等待 Wolfx 补充 ({timeout}s)..."
        )

        # 创建 Future 以便在融合成功时手动 set_result
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        # 存储到 pending
        self.cenc_pending[event.id] = {"event": event, "future": future}

        async def wait_timeout():
            try:
                await asyncio.sleep(timeout)
                if not future.done():
                    future.set_result("timeout")
            except Exception as e:
                if not future.done():
                    future.set_exception(e)

        # 启动超时计时器
        asyncio.create_task(wait_timeout())

        try:
            # 等待结果（超时或被融合唤醒）
            result = await future

            # 从 pending 移除（如果是超时的情况）
            if event.id in self.cenc_pending:
                del self.cenc_pending[event.id]

            if result == "timeout":
                logger.info("[灾害预警] 融合策略: 等待超时，推送原始 Fan 事件")
                return await self._execute_push(event)
            elif result == "fused":
                logger.info("[灾害预警] 融合策略: 融合完成，推送补充后的 Fan 事件")
                # event 已经在 _handle_cenc_wolfx_fusion 中被修改了
                return await self._execute_push(event)

        except Exception as e:
            logger.error(f"[灾害预警] 融合策略处理异常: {e}")
            # 出错时保底推送
            return await self._execute_push(event)

        return False

    def _handle_cenc_wolfx_fusion(self, wolfx_event: DisasterEvent):
        """处理 Wolfx CENC 消息融合"""
        if not self.cenc_pending:
            return

        if (
            not isinstance(wolfx_event.data, EarthquakeData)
            or wolfx_event.data.intensity is None
        ):
            return

        # 简单策略：取第一个 pending 的 Fan 事件进行融合
        try:
            target_id, item = next(iter(self.cenc_pending.items()))
            fan_event = item["event"]
            future = item["future"]

            # 补充数据
            fan_event.data.intensity = wolfx_event.data.intensity
            logger.info(
                f"[灾害预警] 融合策略: 成功用 Wolfx 补充 Fan 事件 {target_id} 的烈度: {wolfx_event.data.intensity}"
            )

            # 标记 Future 完成，唤醒 _handle_cenc_fan_interception
            if not future.done():
                future.set_result("fused")

            # 从 pending 移除
            del self.cenc_pending[target_id]

        except Exception as e:
            logger.error(f"[灾害预警] 融合操作失败: {e}")

    async def _execute_push(self, event: DisasterEvent) -> bool:
        """执行实际的推送流程（原 push_event 逻辑）"""
        logger.debug(f"[灾害预警] 执行事件推送流程: {event.id}")
        source_id = self._get_source_id(event)

        # 1. 先去重检查 - 允许多数据源推送同一事件
        if not self.deduplicator.should_push_event(event):
            logger.debug(f"[灾害预警] 事件 {event.id} 被去重器过滤")
            return False

        # 2. 推送条件检查
        if not self.should_push_event(event):
            logger.debug(f"[灾害预警] 事件 {event.id} 未通过推送条件检查")
            return False

        try:
            # 3. 构建消息 (使用异步构建以支持卡片渲染)
            message = await self.build_message_async(event)
            logger.debug("[灾害预警] 消息构建完成")

            # 4. 获取目标会话
            target_sessions = self.config.get("target_sessions", [])
            if not target_sessions:
                logger.warning("[灾害预警] 没有配置目标会话，无法推送消息")
                return False

            # 5. 推送消息
            push_success_count = 0
            for session in target_sessions:
                try:
                    await self._send_message(session, message)
                    logger.info(f"[灾害预警] 消息已推送到 {session}")
                    push_success_count += 1
                except Exception as e:
                    logger.error(f"[灾害预警] 推送到 {session} 失败: {e}")

            # 6. 异步处理分离的地图瓦片 (针对 EEW 数据源的优化)
            message_format_config = self.config.get("message_format", {})
            include_map = message_format_config.get("include_map", False)
            # 动态获取所有 EEW 数据源，但排除掉使用独立卡片渲染的 global_quake
            split_map_sources = set(get_eew_sources()) - {"global_quake"}
            if (
                include_map
                and source_id in split_map_sources
                and isinstance(event.data, EarthquakeData)
            ):
                # 频率控制逻辑：参考报数控制器，第1报必推，之后每5报推一次，最终报必推
                current_report = getattr(event.data, "updates", 1)
                is_final = getattr(event.data, "is_final", False)

                # 地图瓦片报数控制频率固定为 5 (暂时硬编码)
                map_push_n = 5

                should_gen_map = False
                if current_report == 1 or current_report % map_push_n == 0 or is_final:
                    should_gen_map = True

                if should_gen_map:
                    logger.debug(
                        f"[灾害预警] 触发异步地图渲染 (第 {current_report} 报)"
                    )
                    asyncio.create_task(
                        self._push_split_map(
                            event, target_sessions, message_format_config
                        )
                    )

            # 7. 记录推送
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

    async def build_message_async(self, event: DisasterEvent) -> MessageChain:
        """构建消息 (异步版本) - 支持卡片渲染"""
        source_id = self._get_source_id(event)
        message_format_config = self.config.get("message_format", {})

        # 1. Global Quake 卡片处理逻辑
        use_gq_card = message_format_config.get("use_global_quake_card", False)
        if (
            source_id == "global_quake"
            and use_gq_card
            and isinstance(event.data, EarthquakeData)
        ):
            try:
                # 渲染 Global Quake 卡片
                display_timezone = self.config.get("display_timezone", "UTC+8")
                options = {"timezone": display_timezone}
                context = GlobalQuakeFormatter.get_render_context(event.data, options)

                # 注入自定义缩放级别，默认设为 5
                zoom_level = message_format_config.get("map_zoom_level", 5)
                context["zoom_level"] = zoom_level

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

                    # 计算 Leaflet.js 的绝对路径
                    leaflet_path = os.path.abspath(
                        os.path.join(resources_dir, "card_templates", "leaflet.js")
                    )
                    leaflet_css_path = os.path.abspath(
                        os.path.join(resources_dir, "card_templates", "leaflet.css")
                    )
                    context["leaflet_js_url"] = f"file://{leaflet_path}"
                    context["leaflet_css_url"] = f"file://{leaflet_css_path}"

                    # Jinja2 渲染
                    template = Template(template_content)
                    html_content = template.render(**context)

                    # 准备临时文件路径
                    image_filename = (
                        f"gq_card_{event.data.id}_{int(datetime.now().timestamp())}.png"
                    )
                    image_path = os.path.join(self.temp_dir, image_filename)

                    # 使用 BrowserManager 渲染卡片
                    result_path = await self.browser_manager.render_card(
                        html_content, image_path, selector="#card-wrapper"
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
        chain = self._build_text_message(event, source_id, message_format_config)

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
        weather_config = self.config.get("weather_config", {})
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

        return chain

    def _build_text_message(self, event, source_id, config) -> MessageChain:
        """构建纯文本部分的消息"""
        display_timezone = self.config.get("display_timezone", "UTC+8")
        detailed_jma = config.get("detailed_jma_intensity", False)

        if isinstance(event.data, WeatherAlarmData):
            weather_config = self.config.get("weather_config", {})
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
        """渲染通用地图图片"""
        try:
            map_source = config.get("map_source", "petallight")
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

            context = {
                "latitude": lat,
                "longitude": lon,
                "zoom_level": zoom_level,
                "map_source": map_source,
                "leaflet_js_url": f"file://{leaflet_path}",
                "leaflet_css_url": f"file://{leaflet_css_path}",
            }

            # 渲染 HTML
            template = Template(template_content)
            html_content = template.render(**context)

            # 渲染图片
            image_filename = f"map_{lat}_{lon}_{int(time.time())}.png"
            image_path = os.path.join(self.temp_dir, image_filename)

            result_path = await self.browser_manager.render_card(
                html_content, image_path, selector="#card-wrapper"
            )

            return result_path

        except Exception as e:
            logger.error(f"[灾害预警] 渲染地图图片时出错: {e}")
            return None

    async def _send_message(self, session: str, message: MessageChain):
        """发送消息到指定会话"""
        await self.context.send_message(session, message)

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
