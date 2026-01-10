"""
消息推送管理器
实现优化的报数控制、拆分过滤器和改进的去重逻辑
"""

import os
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any
import tempfile
from jinja2 import Template
from playwright.async_api import async_playwright

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.core.utils.t2i.renderer import HtmlRenderer

from ..models.data_source_config import (
    get_intensity_based_sources,
    get_scale_based_sources,
)
from ..models.models import (
    DataSource,
    DisasterEvent,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from ..utils.formatters import (
    BaseMessageFormatter,
    GlobalQuakeFormatter,
    format_earthquake_message,
    format_tsunami_message,
    format_weather_message,
)
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

    def __init__(self, config: dict[str, Any], context):
        self.config = config
        self.context = context
        # 初始化数据目录 (插件根目录)
        self.data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # 初始化过滤器 - 使用新的配置路径
        earthquake_filters = config.get("earthquake_filters", {})

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

        # 目标会话
        self.target_sessions = self._parse_target_sessions()

        # 初始化本地监控过滤器
        self.local_monitor = LocalIntensityFilter(config.get("local_monitoring", {}))

        # 初始化气象预警过滤器（支持省份、级别和关键词过滤）
        weather_config = config.get("weather_config", {})
        weather_filter_config = weather_config.get("weather_filter", {})
        self.weather_filter = WeatherFilter(weather_filter_config)

        # 初始化关键词过滤器
        keyword_config = (
            config.get("earthquake_filters", {}).get("keyword_filter", {})
        )
        self.keyword_filter = KeywordFilter(keyword_config)

    def _parse_target_sessions(self) -> list[str]:
        """解析目标会话 - 使用正确的配置键名"""
        target_groups = self.config.get("target_groups", [])
        sessions = []

        for group_id in target_groups:
            if group_id:
                # 使用正确的会话ID格式
                platform_name = self.config.get("platform_name", "aiocqhttp")
                session = f"{platform_name}:GroupMessage:{group_id}"
                sessions.append(session)

        return sessions

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
                logger.debug(f"[灾害预警] 事件时间过早（{time_diff:.1f}小时前），过滤")
                return False

        # 2. 非地震事件检查
        if not isinstance(event.data, EarthquakeData):
            # 气象预警事件需要进行过滤（支持省份、级别和关键词过滤）
            if isinstance(event.data, WeatherAlarmData):
                headline = event.data.headline or event.data.title or ""
                if self.weather_filter.should_filter(headline):
                    return False
            # 海啸和气象事件通过了过滤，可以推送
            return True

        # 3. 地震事件专用过滤逻辑
        earthquake = event.data
        source_id = self._get_source_id(event)

        # 关键词过滤（优先应用，适用于所有地震数据源）
        if self.keyword_filter.should_filter(earthquake):
            logger.debug(f"[灾害预警] 事件被关键词过滤器过滤: {source_id}")
            return False

        # 数据源专用过滤器
        if source_id == "global_quake":
            # Global Quake专用过滤器
            if self.global_quake_filter.should_filter(earthquake):
                logger.info(f"[灾害预警] 事件被Global Quake过滤器过滤: {source_id}")
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
                logger.info(f"[灾害预警] 事件被USGS过滤器过滤: {source_id}")
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
        source_mapping = {
            # EEW预警数据源
            DataSource.FAN_STUDIO_CEA.value: "cea_fanstudio",
            DataSource.WOLFX_CENC_EEW.value: "cea_wolfx",
            DataSource.FAN_STUDIO_CWA.value: "cwa_fanstudio",
            DataSource.WOLFX_CWA_EEW.value: "cwa_wolfx",
            DataSource.FAN_STUDIO_JMA.value: "jma_fanstudio",
            DataSource.P2P_EEW.value: "jma_p2p",
            DataSource.WOLFX_JMA_EEW.value: "jma_wolfx",
            # 地震情报数据源
            DataSource.FAN_STUDIO_CENC.value: "cenc_fanstudio",
            DataSource.WOLFX_CENC_EQ.value: "cenc_wolfx",
            DataSource.P2P_EARTHQUAKE.value: "jma_p2p_info",
            DataSource.WOLFX_JMA_EQ.value: "jma_wolfx_info",
            DataSource.FAN_STUDIO_USGS.value: "usgs_fanstudio",
            DataSource.GLOBAL_QUAKE.value: "global_quake",
            # 气象和海啸预警数据源
            DataSource.FAN_STUDIO_WEATHER.value: "china_weather_fanstudio",
            DataSource.FAN_STUDIO_TSUNAMI.value: "china_tsunami_fanstudio",
            DataSource.P2P_TSUNAMI.value: "jma_tsunami_p2p",
        }

        return source_mapping.get(event.source.value, event.source.value)

    async def push_event(self, event: DisasterEvent) -> bool:
        """推送事件"""
        logger.debug(f"[灾害预警] 处理事件推送: {event.id}")

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
            message = await self._build_message_async(event)
            logger.debug("[灾害预警] 消息构建完成")

            # 4. 获取目标会话
            target_sessions = self.target_sessions
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

            # 6. 记录推送
            logger.info(
                f"[灾害预警] 事件 {event.id} 推送完成，成功推送到 {push_success_count} 个会话"
            )
            return push_success_count > 0

        except Exception as e:
            logger.error(f"[灾害预警] 推送事件失败: {e}")
            return False

    def _build_message(self, event: DisasterEvent) -> MessageChain:
        """构建消息 - 使用格式化器并应用消息格式配置（向后兼容，仅调用同步逻辑）"""
        source_id = self._get_source_id(event)
        message_format_config = self.config.get("message_format", {})
        return self._build_message_sync(
            event,
            source_id,
            message_format_config.get("include_map", True),
            message_format_config.get("map_provider", "baidu"),
            message_format_config.get("map_zoom_level", 5),
            message_format_config.get("detailed_jma_intensity", False),
        )

    async def _build_message_async(self, event: DisasterEvent) -> MessageChain:
        """构建消息 (异步版本) - 支持卡片渲染"""
        source_id = self._get_source_id(event)
        message_format_config = self.config.get("message_format", {})
        use_gq_card = message_format_config.get("use_global_quake_card", False)

        if (
            source_id == "global_quake"
            and use_gq_card
            and isinstance(event.data, EarthquakeData)
        ):
            try:
                # 渲染 Global Quake 卡片
                context = GlobalQuakeFormatter.get_render_context(event.data)

                
                # 获取模板名称配置
                template_name = message_format_config.get("global_quake_template", "Aurora")

                # 加载模板 (使用 self.data_dir 即插件根目录)
                resources_dir = os.path.join(self.data_dir, "resources")
                
                # 构建模板路径: resources/card_templates/{template_name}/global_quake.html
                template_path = os.path.join(resources_dir, "card_templates", template_name, "global_quake.html")
                
                # 兼容旧逻辑：如果配置了 'default' 但 card_templates 下没有，或者为了防止路径错误，可以增加一些容错
                # 但根据重构计划，我们优先相信 card_templates 下的结构


                if not os.path.exists(template_path):
                    logger.error(f"[灾害预警] 找不到模板文件: {template_path}")
                    # 回退到同步构建
                    return self._build_message_sync(
                        event,
                        source_id,
                        message_format_config.get("include_map", True),
                        message_format_config.get("map_provider", "baidu"),
                        message_format_config.get("map_zoom_level", 5),
                        message_format_config.get("detailed_jma_intensity", False),
                    )

                with open(template_path, encoding="utf-8") as f:
                    template_content = f.read()
                
                # Jinja2 渲染
                template = Template(template_content)
                html_content = template.render(**context)

                # 使用 Playwright 渲染
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        args=['--no-sandbox', '--disable-setuid-sandbox']
                    )
                    
                    # 创建新页面，视口设置大一点均可，因为我们只截取元素
                    # 关键修复：设置 device_scale_factor=3 提高渲染DPI，解决图片模糊问题
                    page = await browser.new_page(
                        viewport={"width": 800, "height": 800},
                        device_scale_factor=3
                    )
                    
                    await page.set_content(html_content)

                    # 等待元素加载
                    await page.wait_for_load_state("networkidle")
                    
                    # 关键修复：等待 D3 渲染完成标记
                    try:
                        await page.wait_for_selector(".d3-ready", state="attached", timeout=5000)
                    except Exception:
                        # 如果超时（例如JS报错），也不要崩溃，尽力而为截图
                        pass

                    # 统一使用 ID 选择器，这在所有模板中都将通用
                    selector = "#card-wrapper"
                    try:
                        await page.wait_for_selector(selector, state="visible", timeout=5000)
                    except Exception:
                        # 兜底：尝试找常见的类名
                        selector = ".quake-card"
                        await page.wait_for_selector(selector, state="visible", timeout=2000)
                    
                    # 定位卡片元素
                    card = page.locator(selector)
                    
                    # 准备临时文件路径 (使用 AstrBot 数据目录的 temp)
                    # self.data_dir = plugins/astrbot_plugin_disaster_warning
                    # 上两级 = data/temp
                    astrbot_data_dir = os.path.dirname(os.path.dirname(self.data_dir))
                    temp_dir = os.path.join(astrbot_data_dir, "temp")
                    if not os.path.exists(temp_dir):
                        os.makedirs(temp_dir, exist_ok=True)
                    
                    image_filename = f"gq_card_{event.data.id}_{int(datetime.now().timestamp())}.png"
                    image_path = os.path.join(temp_dir, image_filename)
                    
                    # 截图：只截取元素，背景透明
                    await card.screenshot(path=image_path, omit_background=True)
                    
                    await browser.close()

                    if os.path.exists(image_path):
                        logger.info(
                            f"[灾害预警] Global Quake 卡片渲染成功: {image_path}"
                        )
                        chain = [Comp.Image.fromFileSystem(image_path)]
                        return MessageChain(chain)
                    else:
                        logger.warning(
                            "[灾害预警] Global Quake 卡片渲染未生成文件"
                        )

            except Exception as e:
                logger.error(
                    f"[灾害预警] Global Quake 卡片渲染失败: {e}，回退到文本模式"
                )

        # 默认回退到同步构建逻辑
        return self._build_message_sync(
            event,
            source_id,
            message_format_config.get("include_map", True),
            message_format_config.get("map_provider", "baidu"),
            message_format_config.get("map_zoom_level", 5),
            message_format_config.get("detailed_jma_intensity", False),
        )

    def _build_message_sync(
        self, event, source_id, include_map, map_provider, map_zoom_level, detailed_jma
    ) -> MessageChain:
        """同步构建消息逻辑（原 _build_message 内容）"""
        if isinstance(event.data, WeatherAlarmData):
            weather_config = self.config.get("weather_config", {})
            options = {
                "max_description_length": weather_config.get(
                    "max_description_length", 384
                )
            }
            message_text = format_weather_message(source_id, event.data, options)
        elif isinstance(event.data, TsunamiData):
            message_text = format_tsunami_message(source_id, event.data)
        elif isinstance(event.data, EarthquakeData):
            # 传递配置选项
            options = {"detailed_jma_intensity": detailed_jma}
            message_text = format_earthquake_message(source_id, event.data, options)
        else:
            # 未知事件类型，使用基础格式化
            logger.warning(f"[灾害预警] 未知事件类型: {type(event.data)}")
            message_text = f"🚨[未知事件]\n📋事件ID：{event.id}\n⏰时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # 构建消息链
        if include_map and isinstance(event.data, EarthquakeData):
            if event.data.latitude is not None and event.data.longitude is not None:
                # 使用消息格式化器中的优化地图链接生成
                map_url = BaseMessageFormatter.get_map_link(
                    event.data.latitude,
                    event.data.longitude,
                    map_provider,
                    map_zoom_level,
                    magnitude=event.data.magnitude,
                    place_name=event.data.place_name,
                )
                if map_url:
                    # 关键修复：绕过AstrBot的strip()问题
                    # 使用零宽空格保护换行，URL编码确保特殊字符处理
                    zero_width_space = "\u200b"
                    encoded_map_url = urllib.parse.quote(map_url, safe=":/?&=+")

                    # 直接合并到消息文本中
                    message_text += f"{zero_width_space}\n🗺️地图链接:{zero_width_space} {encoded_map_url}"

        # 构建消息链
        chain = [Comp.Plain(message_text)]
        return MessageChain(chain)

    async def _send_message(self, session: str, message: MessageChain):
        """发送消息到指定会话"""
        await self.context.send_message(session, message)

    def cleanup_old_records(self):
        """清理旧记录"""
        # 清理去重器
        self.deduplicator.cleanup_old_events()
