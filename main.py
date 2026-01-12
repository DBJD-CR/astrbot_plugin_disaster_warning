import asyncio
import json
import os
import traceback
from datetime import datetime

# [已移除] Windows平台WebSocket兼容性修复
# 采用 aiohttp 替代 websockets 库，原生支持 Windows EventLoop，无需修改全局策略
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .core.disaster_service import get_disaster_service, stop_disaster_service
from .core.web_server import WebAdminServer
from .models.models import (
    DATA_SOURCE_MAPPING,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
    get_data_source_from_id,
)
from .utils.fe_regions import translate_place_name


class DisasterWarningPlugin(Star):
    """多数据源灾害预警插件，支持地震、海啸、气象预警"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.disaster_service = None
        self._service_task = None
        self.web_server = None

    async def initialize(self):
        """初始化插件"""
        try:
            logger.info("[灾害预警] 正在初始化灾害预警插件...")

            # 检查插件是否启用
            if not self.config.get("enabled", True):
                logger.info("[灾害预警] 插件已禁用，跳过初始化")
                return

            # 获取灾害预警服务
            self.disaster_service = await get_disaster_service(
                self.config, self.context
            )

            # 启动服务
            self._service_task = asyncio.create_task(self.disaster_service.start())

            # 启动 Web 管理端
            if self.config.get("web_admin", {}).get("enabled", False):
                self.web_server = WebAdminServer(self.disaster_service, self.config)
                await self.web_server.start()

        except Exception as e:
            logger.error(f"[灾害预警] 插件初始化失败: {e}")
            raise

    async def terminate(self):
        """插件销毁时调用"""
        try:
            logger.info("[灾害预警] 正在停止灾害预警插件...")

            # 停止服务任务
            if self._service_task:
                self._service_task.cancel()
                try:
                    await self._service_task
                except asyncio.CancelledError:
                    pass

            # 停止灾害预警服务
            await stop_disaster_service()

            # 停止 Web 管理端
            if self.web_server:
                await self.web_server.stop()

            logger.info("[灾害预警] 灾害预警插件已停止")

        except Exception as e:
            logger.error(f"[灾害预警] 插件停止时出错: {e}")

    @filter.command("灾害预警")
    async def disaster_warning_help(self, event: AstrMessageEvent):
        """灾害预警插件帮助"""
        help_text = """🚨 灾害预警插件使用说明

📋 可用命令：
• /灾害预警 - 显示此帮助信息
• /灾害预警状态 - 查看服务运行状态
• /灾害预警统计 - 查看详细的事件统计报告
• /灾害预警统计清除 - 清除所有统计信息
• /灾害预警测试 [群号] [灾害类型] [格式] - 测试推送功能
• /灾害预警模拟 <纬度> <经度> <震级> [深度] [数据源] - 模拟地震事件
• /灾害预警配置 查看 - 查看当前配置摘要
• /灾害预警日志 - 查看原始消息日志统计摘要
• /灾害预警日志开关 - 开关原始消息日志记录
• /灾害预警日志清除 - 清除所有原始消息日志

更多信息可参考 README 文档"""

        yield event.plain_result(help_text)

    @filter.command("灾害预警状态")
    async def disaster_status(self, event: AstrMessageEvent):
        """查看灾害预警服务状态"""
        if not self.disaster_service:
            yield event.plain_result("❌ 灾害预警服务未启动")
            return

        try:
            status = self.disaster_service.get_service_status()

            # --- 基础状态 ---
            running_state = "🟢 运行中" if status["running"] else "🔴 已停止"
            uptime = status.get("uptime", "未知")

            status_text = [
                "📊 灾害预警服务状态\n",
                "\n",
                f"🔄 运行状态：{running_state} (已运行 {uptime})\n",
                f"🔗 活跃连接：{status['active_websocket_connections']} / {status['total_connections']}\n",
            ]

            # --- 连接详情 ---
            conn_details = status.get("connection_details", {})
            if conn_details:
                status_text.append("\n")
                status_text.append("📡 连接详情：\n")
                for name, detail in conn_details.items():
                    state_icon = "🟢" if detail.get("connected") else "🔴"
                    uri = detail.get("uri", "未知地址")
                    # 简化URI显示
                    if len(uri) > 30:
                        uri = uri[:27] + "..."
                    retry = detail.get("retry_count", 0)
                    retry_text = f" (重试: {retry})" if retry > 0 else ""

                    status_text.append(f"  {state_icon} `{name}`: {uri}{retry_text}\n")

            # --- 活跃数据源 ---
            active_sources = status.get("data_sources", [])
            if active_sources:
                status_text.append("\n")
                status_text.append("📡 数据源详情：\n")

                # 按照服务分组
                service_groups = {}
                for source in active_sources:
                    parts = source.split(".", 1)
                    service = parts[0]
                    name = parts[1] if len(parts) > 1 else source
                    if service not in service_groups:
                        service_groups[service] = []
                    service_groups[service].append(name)

                # 映射服务名称为中文
                service_names = {
                    "fan_studio": "FAN Studio",
                    "p2p_earthquake": "P2P地震情报",
                    "wolfx": "Wolfx",
                    "global_quake": "Global Quake",
                }

                # 格式化输出
                for service, sources in service_groups.items():
                    display_name = service_names.get(service, service)
                    sources_str = ", ".join(sources)
                    status_text.append(f"  • {display_name}: {sources_str}\n")

            yield event.plain_result("".join(status_text))

        except Exception as e:
            logger.error(f"[灾害预警] 获取服务状态失败: {e}")
            yield event.plain_result(f"❌ 获取服务状态失败: {str(e)}")

    @filter.command("灾害预警统计")
    async def disaster_stats(self, event: AstrMessageEvent):
        """查看灾害预警详细统计"""
        if not self.disaster_service:
            yield event.plain_result("❌ 灾害预警服务未启动")
            return

        try:
            status = self.disaster_service.get_service_status()
            stats_summary = status.get("statistics_summary", "❌ 暂无统计数据")

            # 附加过滤统计信息
            if self.disaster_service and self.disaster_service.message_logger:
                filter_stats = self.disaster_service.message_logger.filter_stats
                if filter_stats and filter_stats["total_filtered"] > 0:
                    stats_summary += "\n\n🛡️ 日志过滤拦截统计:\n"
                    stats_summary += f"重复数据拦截: {filter_stats.get('duplicate_events_filtered', 0)}\n"
                    stats_summary += f"心跳包/连接状态拦截: {filter_stats.get('heartbeat_filtered', 0) + filter_stats.get('p2p_areas_filtered', 0) + filter_stats.get('connection_status_filtered', 0)}\n"
                    stats_summary += (
                        f"总计拦截: {filter_stats.get('total_filtered', 0)}"
                    )

            yield event.plain_result(stats_summary)
        except Exception as e:
            logger.error(f"[灾害预警] 获取统计信息失败: {e}")
            yield event.plain_result(f"❌ 获取统计信息失败: {str(e)}")

    @filter.command("灾害预警测试")
    async def disaster_test(
        self,
        event: AstrMessageEvent,
        target_group: str = None,
        disaster_type: str = None,
        test_type: str = None,
    ):
        """测试灾害预警推送功能 - 支持多种灾害类型和测试格式"""
        if not self.disaster_service:
            yield event.plain_result("❌ 灾害预警服务未启动")
            return

        try:
            # 解析参数 - 支持多种参数组合
            target_session = None
            disaster_test_type = "earthquake"  # 默认测试地震
            format_test_type = None  # 默认使用推荐格式

            # 中文参数映射
            type_mapping = {
                "地震": "earthquake",
                "海啸": "tsunami",
                "气象": "weather",
                "earthquake": "earthquake",
                "tsunami": "tsunami",
                "weather": "weather",
            }

            format_mapping = {
                "中国": "china",
                "日本": "japan",
                "美国": "usgs",
                "china": "china",
                "japan": "japan",
                "usgs": "usgs",
            }

            # 获取平台名称配置
            platform_name = self.config.get("platform_name", "aiocqhttp")

            # 辅助函数：判断字符串是否为灾害类型
            def is_disaster_type(s):
                return s in type_mapping

            # 辅助函数：判断字符串是否为测试格式
            def is_format_type(s):
                return s in format_mapping

            # 参数解析逻辑 - 支持最多3个参数
            if target_group and disaster_type and test_type:
                # 三个参数：群号 + 灾害类型 + 测试格式
                target_session = f"{platform_name}:GroupMessage:{target_group}"
                disaster_test_type = type_mapping.get(disaster_type, disaster_type)
                format_test_type = format_mapping.get(test_type, test_type)

            elif target_group and disaster_type:
                # 两个参数：需要判断第二个是灾害类型还是测试格式
                if is_disaster_type(disaster_type):
                    # 情况1: 群号 + 灾害类型 (例如: 123456 earthquake)
                    target_session = f"{platform_name}:GroupMessage:{target_group}"
                    disaster_test_type = type_mapping.get(disaster_type)
                    # test_type 保持 None，使用默认格式
                elif is_format_type(disaster_type):
                    # 第二个是格式，需要判断第一个是群号还是灾害类型
                    if is_disaster_type(target_group):
                        # 情况2: 灾害类型 + 格式 (例如: earthquake japan) -> 使用当前群
                        target_session = event.unified_msg_origin
                        disaster_test_type = type_mapping.get(target_group)
                        format_test_type = format_mapping.get(disaster_type)
                    else:
                        # 情况3: 群号 + 格式 (例如: 123456 japan) -> 默认地震
                        target_session = f"{platform_name}:GroupMessage:{target_group}"
                        disaster_test_type = "earthquake"
                        format_test_type = format_mapping.get(disaster_type)
                else:
                    # 其他情况，尝试智能匹配
                    if is_disaster_type(target_group) and is_format_type(disaster_type):
                        target_session = event.unified_msg_origin
                        disaster_test_type = type_mapping.get(target_group)
                        format_test_type = format_mapping.get(disaster_type)
                    else:
                        # 默认处理
                        target_session = f"{platform_name}:GroupMessage:{target_group}"
                        disaster_test_type = type_mapping.get(
                            disaster_type, disaster_type
                        )

            elif target_group:
                # 只提供一个参数：需要判断是群号还是灾害类型/测试格式
                if is_disaster_type(target_group):
                    # 是灾害类型，使用当前群
                    target_session = event.unified_msg_origin
                    disaster_test_type = type_mapping.get(target_group)
                elif is_format_type(target_group):
                    # 是测试格式，使用当前群，默认地震
                    target_session = event.unified_msg_origin
                    disaster_test_type = "earthquake"
                    format_test_type = format_mapping.get(target_group)
                else:
                    # 是群号，默认测试地震
                    target_session = f"{platform_name}:GroupMessage:{target_group}"
                    disaster_test_type = "earthquake"
            else:
                # 没有额外参数：使用当前群，默认测试地震
                target_session = event.unified_msg_origin
                disaster_test_type = "earthquake"

            # 验证灾害类型
            valid_types = ["earthquake", "tsunami", "weather"]
            if disaster_test_type not in valid_types:
                yield event.plain_result(
                    f"❌ 未知的灾害类型 '{disaster_test_type}'\n\n支持的类型：地震(earthquake), 海啸(tsunami), 气象(weather)"
                )
                return

            # 验证测试格式
            valid_formats = {
                "earthquake": ["china", "japan", "usgs"],
                "tsunami": ["china", "japan"],
                "weather": ["china"],  # 气象只有中国格式
            }

            if format_test_type:
                allowed_formats = valid_formats.get(disaster_test_type, [])
                if format_test_type not in allowed_formats:
                    yield event.plain_result(
                        f"❌ 灾害类型 '{disaster_test_type}' 不支持测试格式 '{format_test_type}'\n\n"
                        f"支持的格式：{', '.join(allowed_formats)}"
                    )
                    return

            # 执行测试
            logger.info(
                f"[灾害预警] 开始{disaster_test_type}测试推送到 {target_session} (格式: {format_test_type or '默认'})"
            )
            test_result = await self.disaster_service.test_push(
                target_session, disaster_test_type, format_test_type
            )

            if test_result and "✅" in test_result:
                # 测试成功，直接返回测试结果
                yield event.plain_result(test_result)
            else:
                yield event.plain_result(test_result or "❌ 测试推送失败，请检查日志")

        except Exception as e:
            logger.error(f"[灾害预警] 测试推送失败: {e}")
            yield event.plain_result(f"❌ 测试推送失败: {str(e)}")

    @filter.command("灾害预警日志")
    async def disaster_logs(self, event: AstrMessageEvent):
        """查看原始消息日志信息"""
        if not self.disaster_service or not self.disaster_service.message_logger:
            yield event.plain_result("❌ 日志功能不可用")
            return

        try:
            log_summary = self.disaster_service.message_logger.get_log_summary()

            if not log_summary["enabled"]:
                yield event.plain_result(
                    "📋 原始消息日志功能未启用\n\n使用 /灾害预警日志开关 启用日志记录"
                )
                return

            if not log_summary["log_exists"]:
                yield event.plain_result(
                    "📋 暂无日志记录\n\n当日志功能启用后，所有接收到的原始消息将被记录。"
                )
                return

            log_info = f"""📊 原始消息日志统计

📁 日志文件：{log_summary["log_file"]}
📈 总条目数：{log_summary["total_entries"]}
📦 文件大小：{log_summary.get("file_size_mb", 0):.2f} MB
📅 时间范围：{log_summary["date_range"]["start"]} 至 {log_summary["date_range"]["end"]}

📡 数据源统计："""

            for source in log_summary["data_sources"]:
                log_info += f"\n  • {source}"

            log_info += "\n\n💡 提示：使用 /灾害预警日志开关 可以关闭日志记录"

            yield event.plain_result(log_info)

        except Exception as e:
            logger.error(f"[灾害预警] 获取日志信息失败: {e}")
            yield event.plain_result(f"❌ 获取日志信息失败: {str(e)}")

    @filter.command("灾害预警日志开关")
    async def toggle_message_logging(self, event: AstrMessageEvent):
        """开关原始消息日志记录"""
        if not self.disaster_service or not self.disaster_service.message_logger:
            yield event.plain_result("❌ 日志功能不可用")
            return

        try:
            current_state = self.disaster_service.message_logger.enabled
            new_state = not current_state

            # 更新配置
            self.config["debug_config"]["enable_raw_message_logging"] = new_state
            self.disaster_service.message_logger.enabled = new_state

            # 保存配置
            self.config.save_config()

            status = "启用" if new_state else "禁用"
            action = "开始" if new_state else "停止"

            yield event.plain_result(
                f"✅ 原始消息日志记录已{status}\n\n插件将{action}记录所有数据源的原始消息格式。"
            )

        except Exception as e:
            logger.error(f"[灾害预警] 切换日志状态失败: {e}")
            yield event.plain_result(f"❌ 切换日志状态失败: {str(e)}")

    @filter.command("灾害预警日志清除")
    async def clear_message_logs(self, event: AstrMessageEvent):
        """清除所有原始消息日志"""
        if not self.disaster_service or not self.disaster_service.message_logger:
            yield event.plain_result("❌ 日志功能不可用")
            return

        try:
            self.disaster_service.message_logger.clear_logs()
            yield event.plain_result(
                "✅ 所有原始消息日志已清除\n\n日志文件已被删除，新的消息记录将重新开始。"
            )

        except Exception as e:
            logger.error(f"[灾害预警] 清除日志失败: {e}")
            yield event.plain_result(f"❌ 清除日志失败: {str(e)}")

    @filter.command("灾害预警统计清除")
    async def clear_statistics(self, event: AstrMessageEvent):
        """清除统计数据"""
        if not self.disaster_service or not self.disaster_service.statistics_manager:
            yield event.plain_result("❌ 统计功能不可用")
            return

        try:
            self.disaster_service.statistics_manager.reset_stats()
            yield event.plain_result(
                "✅ 统计数据已重置\n\n所有历史统计记录已被清除，新的统计将重新开始。"
            )

        except Exception as e:
            logger.error(f"[灾害预警] 清除统计失败: {e}")
            yield event.plain_result(f"❌ 清除统计失败: {str(e)}")

    @filter.command("灾害预警配置")
    async def disaster_config(self, event: AstrMessageEvent, action: str = None):
        """查看当前配置信息"""
        if action != "查看":
            yield event.plain_result("❓ 请使用格式：/灾害预警配置 查看")
            return

        try:
            # 加载 schema 文件以获取中文描述
            schema_path = os.path.join(os.path.dirname(__file__), "_conf_schema.json")
            if os.path.exists(schema_path):
                with open(schema_path, encoding="utf-8") as f:
                    schema = json.load(f)
            else:
                schema = {}

            def _translate_recursive(config_item, schema_item):
                """递归将配置键名转换为中文描述"""
                if not isinstance(config_item, dict):
                    return config_item

                translated = {}
                for key, value in config_item.items():
                    # 获取当前键的 schema 定义
                    item_schema = schema_item.get(key, {}) if schema_item else {}

                    # 获取中文描述，如果没有则使用原键名
                    # 格式：中文描述
                    description = item_schema.get("description", key)

                    # 处理嵌套结构
                    if isinstance(value, dict):
                        # 如果 schema 中有 items 定义（通常用于嵌套对象），则传入子 schema
                        sub_schema = item_schema.get("items", {})
                        translated[description] = _translate_recursive(
                            value, sub_schema
                        )
                    else:
                        translated[description] = value

                return translated

            # 将配置转换为字典并进行翻译
            config_data = dict(self.config)
            translated_config = _translate_recursive(config_data, schema)

            # 转换为格式化的 JSON 字符串
            config_str = json.dumps(translated_config, indent=2, ensure_ascii=False)

            # 构造返回消息
            yield event.plain_result(f"🔧 当前配置详情：{config_str}")

        except Exception as e:
            logger.error(f"[灾害预警] 获取配置详情失败: {e}")
            yield event.plain_result(f"❌ 获取配置详情失败: {str(e)}")

    def _format_source_name(self, source_key: str) -> str:
        """格式化数据源名称 - 细粒度配置结构"""
        # 配置格式：service.source (如：fan_studio.china_earthquake_warning)
        service, source = source_key.split(".", 1)
        source_names = {
            "fan_studio": {
                "china_earthquake_warning": "中国地震网地震预警",
                "taiwan_cwa_earthquake": "台湾中央气象署强震即时警报",
                "china_cenc_earthquake": "中国地震台网地震测定",
                "japan_jma_eew": "日本气象厅紧急地震速报",
                "usgs_earthquake": "USGS地震测定",
                "china_weather_alarm": "中国气象局气象预警",
                "china_tsunami": "自然资源部海啸预警",
            },
            "p2p_earthquake": {
                "japan_jma_eew": "P2P-日本气象厅紧急地震速报",
                "japan_jma_earthquake": "P2P-日本气象厅地震情报",
                "japan_jma_tsunami": "P2P-日本气象厅海啸预报",
            },
            "wolfx": {
                "japan_jma_eew": "Wolfx-日本气象厅紧急地震速报",
                "china_cenc_eew": "Wolfx-中国地震台网预警",
                "taiwan_cwa_eew": "Wolfx-台湾地震预警",
                "japan_jma_earthquake": "Wolfx-日本气象厅地震情报",
                "china_cenc_earthquake": "Wolfx-中国地震台网地震测定",
            },
            "global_quake": {
                "enabled": "Global Quake",
            },
        }
        return source_names.get(service, {}).get(source, source_key)

    @filter.command("灾害预警模拟")
    async def simulate_earthquake(
        self,
        event: AstrMessageEvent,
        lat: float,
        lon: float,
        magnitude: float,
        depth: float = 10.0,
        source: str = "cea_fanstudio",
    ):
        """模拟地震事件测试预警响应
        格式：/灾害预警模拟 <纬度> <经度> <震级> [深度] [数据源]

        常用数据源ID：
        • cea_fanstudio (中国地震预警网 - 默认)
        • jma_p2p (日本气象厅P2P)
        • usgs_fanstudio (USGS)
        • cwa_fanstudio (台湾中央气象署)
        """
        if not self.disaster_service or not self.disaster_service.message_manager:
            yield event.plain_result("❌ 服务未启动")
            return

        try:
            # 获取数据源
            data_source = get_data_source_from_id(source)
            if not data_source:
                valid_sources = ", ".join(DATA_SOURCE_MAPPING.keys())
                yield event.plain_result(
                    f"❌ 无效的数据源: {source}\n可用数据源: {valid_sources}"
                )
                return

            # 1. 构造模拟数据
            # 自动根据传入的经纬度生成地名
            final_place_name = translate_place_name("模拟震中", lat, lon)

            earthquake = EarthquakeData(
                id=f"sim_{int(datetime.now().timestamp())}",
                event_id=f"sim_{int(datetime.now().timestamp())}",
                source=data_source,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=datetime.now(),
                latitude=lat,
                longitude=lon,
                depth=depth,
                magnitude=magnitude,
                place_name=final_place_name,
                source_id=source,
                raw_data={"test": True, "source_id": source},
            )

            # 针对USGS等特定数据源的特殊处理
            if source == "usgs_fanstudio":
                earthquake.update_time = datetime.now()

            # P2P数据源需要最大震度
            if source in ["jma_p2p", "jma_wolfx", "jma_p2p_info"]:
                # 简单估算一个震度用于测试
                earthquake.max_scale = max(0, min(7, int(magnitude - 2)))
                earthquake.scale = earthquake.max_scale

            disaster_event = DisasterEvent(
                id=f"sim_evt_{int(datetime.now().timestamp())}",
                data=earthquake,
                source=data_source,
                disaster_type=DisasterType.EARTHQUAKE,
                source_id=source,
            )

            manager = self.disaster_service.message_manager

            # 分开的消息构建
            report_lines = [
                "🧪 **灾害预警模拟报告**",
                f"Input: M{magnitude} @ ({lat}, {lon}), Depth {depth}km\n",
            ]

            # 2. 检查全局过滤器 (Global Filters)
            global_pass = True
            if manager.intensity_filter:
                if manager.intensity_filter.should_filter(earthquake):
                    global_pass = False
                    report_lines.append("❌ 全局过滤: 拦截 (不满足最小震级/烈度要求)")
                else:
                    report_lines.append("✅ 全局过滤: 通过")

            # 3. 检查本地监控 (Local Monitor)
            local_pass = True
            if manager.local_monitor:
                # 使用统一的辅助方法，返回 None 表示未启用，返回 dict 表示启用
                result = manager.local_monitor.inject_local_estimation(earthquake)

                if result is None:
                    # 未启用
                    report_lines.append("ℹ️ 本地监控: 未启用")
                else:
                    allowed = result.get("is_allowed", True)
                    dist = result.get("distance")
                    inte = result.get("intensity")

                    if allowed:
                        report_lines.append("✅ 本地监控: 触发")
                    else:
                        local_pass = False
                        report_lines.append("❌ 本地监控: 拦截 (严格模式生效中)")

                    report_lines.append(
                        f"   ⦁ 严格模式: {'开启' if manager.local_monitor.strict_mode else '关闭 (仅计算不拦截)'}"
                    )

                    # 安全格式化，处理可能的 None 值
                    dist_str = f"{dist:.1f} km" if dist is not None else "未知"
                    inte_str = f"{inte:.1f}" if inte is not None else "未知"
                    report_lines.extend(
                        [
                            f"   ⦁ 距本地: {dist_str}",
                            f"   ⦁ 预估最大本地烈度: {inte_str}",
                            f"   ⦁ 本地烈度阈值: {manager.local_monitor.threshold}",
                        ]
                    )
            else:
                report_lines.append("ℹ️ 本地监控: 未配置")

            # 发送报告
            yield event.plain_result("\n".join(report_lines))

            # 稍作等待，确保第一条消息发出
            await asyncio.sleep(1)

            # 4. 模拟消息构建
            if global_pass and local_pass:
                try:
                    logger.info("[灾害预警] 开始构建模拟预警消息...")
                    # 使用异步版本以支持卡片渲染
                    msg_chain = await manager._build_message_async(disaster_event)
                    logger.info(
                        f"[灾害预警] 消息构建成功，链长度: {len(msg_chain.chain)}"
                    )

                    # 直接使用context发送消息，绕过command generator
                    await self.context.send_message(event.unified_msg_origin, msg_chain)
                except Exception as build_e:
                    logger.error(
                        f"[灾害预警] 消息构建失败: {build_e}\n{traceback.format_exc()}"
                    )
                    yield event.plain_result(f"❌ 消息构建失败: {build_e}")
            else:
                yield event.plain_result("\n⛔ 结论: 该事件不会触发预警推送。")

        except Exception as e:
            error_trace = traceback.format_exc()
            logger.error(f"[灾害预警] 模拟测试失败: {e}\n{error_trace}")
            yield event.plain_result(f"❌ 模拟失败: {e}")

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        """AstrBot加载完成时的钩子"""
        logger.info("[灾害预警] AstrBot已加载完成，灾害预警插件准备就绪")

 
