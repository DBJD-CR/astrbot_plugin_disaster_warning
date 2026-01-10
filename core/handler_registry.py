"""
WebSocket消息处理器注册中心
负责创建和注册各种数据源的WebSocket消息处理器
"""

import json

from astrbot.api import logger

from .websocket_manager import WebSocketManager


class WebSocketHandlerRegistry:
    """WebSocket消息处理器注册中心"""

    def __init__(self, service):
        """
        初始化注册中心
        :param service: DisasterWarningService 实例，用于访问 handlers 和处理事件
        """
        self.service = service

    def register_all(self, ws_manager: WebSocketManager):
        """注册所有处理器"""
        ws_manager.register_handler("fan_studio", self._create_fan_studio_handler())
        ws_manager.register_handler("p2p", self._create_p2p_handler())
        ws_manager.register_handler("wolfx", self._create_wolfx_handler())
        ws_manager.register_handler("global_quake", self._create_global_quake_handler())

    def _create_fan_studio_handler(self):
        """创建 FAN Studio WebSocket 处理器"""

        async def fan_studio_handler(
            message, connection_name=None, connection_info=None
        ):
            # 利用connection_info增强日志记录
            if connection_info:
                logger.debug(
                    f"[灾害预警] FAN Studio处理器收到消息 - 连接: {connection_name}, URI: {connection_info.get('uri', 'unknown')}"
                )
                # 记录连接建立时间（如果可用）
                established_time = connection_info.get("established_time")
                if established_time:
                    logger.debug(f"[灾害预警] 连接建立时间: {established_time}")
            else:
                logger.debug(
                    f"[灾害预警] FAN Studio处理器收到消息 - 连接: {connection_name}"
                )

            try:
                # 尝试解析JSON
                try:
                    data = json.loads(message)
                except json.JSONDecodeError as e:
                    logger.error(f"[灾害预警] JSON解析失败: {e}")
                    return None

                # 定义源映射关系 (source_name -> (config_key, handler_id))
                source_map = {
                    "weatheralarm": ("china_weather_alarm", "china_weather_fanstudio"),
                    "tsunami": ("china_tsunami", "china_tsunami_fanstudio"),
                    "cenc": ("china_cenc_earthquake", "cenc_fanstudio"),
                    "cea": ("china_earthquake_warning", "cea_fanstudio"),
                    "jma": ("japan_jma_eew", "jma_fanstudio"),
                    "cwa": ("taiwan_cwa_earthquake", "cwa_fanstudio"),
                    "usgs": ("usgs_earthquake", "usgs_fanstudio"),
                }

                # 待处理的消息列表 [(source, msg_payload)]
                messages_to_process = []
                msg_type = data.get("type")

                # 1. 处理 initial_all (全量初始消息)
                if msg_type == "initial_all":
                    for key, value in data.items():
                        if key in source_map and isinstance(value, dict):
                            messages_to_process.append((key, value))

                # 2. 处理 update (单条更新消息)
                elif msg_type == "update":
                    source = data.get("source")
                    if source and source in source_map:
                        messages_to_process.append((source, data))

                # 3. 兜底：尝试特征识别 (兼容旧格式或无 source 的情况)
                # 只有当消息中没有明确的 source 字段时才进行猜测
                # 如果有 source 但不在 source_map 中（如 kma），说明是未知源，不应强行识别为其他源
                source_id = data.get("source")
                if not messages_to_process and not source_id:
                    # 提取核心数据用于特征识别
                    msg_data = data
                    depth = 0
                    while (
                        isinstance(msg_data, dict)
                        and ("Data" in msg_data or "data" in msg_data)
                        and depth < 3
                    ):
                        msg_data = msg_data.get("Data") or msg_data.get("data")
                        depth += 1

                    if isinstance(msg_data, dict):
                        # 特征识别逻辑
                        detected_source = None
                        if "headline" in msg_data and "type" in msg_data:
                            detected_source = "weatheralarm"
                        elif "warningInfo" in msg_data and "code" in msg_data:
                            detected_source = "tsunami"
                        elif "infoTypeName" in msg_data and (
                            "[正式测定]" in msg_data.get("infoTypeName", "")
                            or "[自动测定]" in msg_data.get("infoTypeName", "")
                        ):
                            detected_source = "cenc"
                        elif (
                            "infoTypeName" in msg_data
                            and "final" in msg_data
                            and isinstance(msg_data.get("epiIntensity"), str)
                        ):
                            detected_source = "jma"
                        elif (
                            "epiIntensity" in msg_data
                            and "createTime" in msg_data
                            and "shockTime" in msg_data
                            and "infoTypeName" not in msg_data
                        ):
                            detected_source = "cwa"
                        elif (
                            "epiIntensity" in msg_data
                            and "eventId" in msg_data
                            and "updates" in msg_data
                        ):
                            detected_source = "cea"
                        elif "url" in msg_data and "usgs.gov" in msg_data.get(
                            "url", ""
                        ):
                            detected_source = "usgs"

                        if detected_source:
                            messages_to_process.append((detected_source, data))

                # 4. 遍历处理所有识别出的消息
                processed_count = 0
                for source, payload in messages_to_process:
                    config_key, handler_id = source_map[source]

                    # 检查是否启用
                    if not self.service.is_fan_studio_source_enabled(config_key):
                        logger.debug(
                            f"[灾害预警] 数据源 {config_key} ({source}) 未启用，忽略"
                        )
                        continue

                    handler = self.service.handlers.get(handler_id)
                    if handler:
                        logger.debug(f"[灾害预警] 处理 {source} 数据 ({config_key})")
                        # 注意：这里我们需要传递原始 payload，因为 Handler 内部会再次提取 Data
                        # 如果 payload 已经是提取过的 Data (initial_all 的情况)，Handler 需要能处理
                        # 现有的 Handler 通常支持 {"Data": ...} 或直接的 Data 字典
                        event = handler.parse_message(json.dumps(payload))

                        if event:
                            # 增强事件信息
                            if (
                                connection_info
                                and hasattr(event, "raw_data")
                                and isinstance(event.raw_data, dict)
                            ):
                                event.raw_data["connection_info"] = {
                                    "connection_name": connection_name,
                                    "uri": connection_info.get("uri"),
                                    "connection_type": connection_info.get(
                                        "connection_type"
                                    ),
                                    "established_time": connection_info.get(
                                        "established_time"
                                    ),
                                    "source_channel": source,
                                }

                            logger.debug(f"[灾害预警] {source} 解析成功: {event.id}")
                            await self.service._handle_disaster_event(event)
                            processed_count += 1
                    else:
                        logger.warning(f"[灾害预警] 未找到处理器: {handler_id}")

                # 5. 如果没有处理任何消息，且不是心跳包，记录日志
                if processed_count == 0 and not messages_to_process:
                    is_heartbeat = (
                        data.get("type") in ["heartbeat", "ping", "pong"]
                        or "timestamp" in data
                        and len(data) <= 3
                    )
                    if not is_heartbeat:
                        # 检查是否包含 Data 但未被识别
                        has_data = "Data" in data or "data" in data
                        # 或者是 initial_all 但没有匹配的源
                        is_unhandled_initial = msg_type == "initial_all"

                        if has_data or is_unhandled_initial:
                            logger.debug(
                                f"[灾害预警] 未处理的消息，连接: {connection_name}, "
                                f"类型: {msg_type}, "
                                f"源: {data.get('source', 'unknown')}, "
                                f"数据摘要: {str(data)[:100]}"
                            )

                # 这里的返回值仅用于旧逻辑兼容，现在主要逻辑都在上面处理了
                # 返回 None 即可，因为我们已经直接调用了 _handle_disaster_event
                return None

            except Exception as e:
                logger.error(
                    f"[灾害预警] FAN Studio处理器解析消息失败 - 连接: {connection_name}, 错误: {e}"
                )
                if connection_info:
                    logger.error(
                        f"[灾害预警] 连接信息 - URI: {connection_info.get('uri')}, 类型: {connection_info.get('connection_type')}"
                    )
                raise

        return fan_studio_handler

    def _create_p2p_handler(self):
        """创建 P2P Quake WebSocket 处理器"""

        async def p2p_handler(message, connection_name=None, connection_info=None):
            # 利用connection_info增强日志记录
            if connection_info:
                logger.debug(
                    f"[灾害预警] P2P处理器收到消息 - 连接: {connection_name}, URI: {connection_info.get('uri', 'unknown')}, 长度: {len(message)}"
                )
            else:
                logger.debug(
                    f"[灾害预警] P2P处理器收到消息 - 连接: {connection_name}, 长度: {len(message)}"
                )

            # 调试：检查消息类型
            try:
                data = json.loads(message)
                code = data.get("code")
                if code == 556:
                    logger.info(
                        "[灾害预警] P2P处理器收到紧急地震速报(code:556)，准备解析..."
                    )
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass

            # 尝试EEW处理器
            eew_handler = self.service.handlers.get("jma_p2p")
            if eew_handler:
                try:
                    event = eew_handler.parse_message(message)
                    if event:
                        # 利用connection_info增强事件信息
                        if (
                            connection_info
                            and hasattr(event, "raw_data")
                            and isinstance(event.raw_data, dict)
                        ):
                            event.raw_data["connection_info"] = {
                                "connection_name": connection_name,
                                "uri": connection_info.get("uri"),
                                "connection_type": connection_info.get(
                                    "connection_type"
                                ),
                                "established_time": connection_info.get(
                                    "established_time"
                                ),
                            }

                        logger.debug(f"[灾害预警] P2P EEW处理器解析成功: {event.id}")
                        await self.service._handle_disaster_event(event)
                        return
                except Exception as e:
                    logger.error(
                        f"[灾害预警] P2P EEW处理器解析失败 - 连接: {connection_name}, 错误: {e}"
                    )
                    if connection_info:
                        logger.error(
                            f"[灾害预警] 连接信息 - URI: {connection_info.get('uri')}"
                        )

            # 尝试地震情報处理器
            info_handler = self.service.handlers.get("jma_p2p_info")
            if info_handler:
                try:
                    event = info_handler.parse_message(message)
                    if event:
                        # 利用connection_info增强事件信息
                        if (
                            connection_info
                            and hasattr(event, "raw_data")
                            and isinstance(event.raw_data, dict)
                        ):
                            event.raw_data["connection_info"] = {
                                "connection_name": connection_name,
                                "uri": connection_info.get("uri"),
                                "connection_type": connection_info.get(
                                    "connection_type"
                                ),
                                "established_time": connection_info.get(
                                    "established_time"
                                ),
                            }

                        logger.debug(
                            f"[灾害预警] P2P地震情報处理器解析成功: {event.id}"
                        )
                        await self.service._handle_disaster_event(event)
                        return
                except Exception as e:
                    logger.error(
                        f"[灾害预警] P2P地震情報处理器解析失败 - 连接: {connection_name}, 错误: {e}"
                    )
                    if connection_info:
                        logger.error(
                            f"[灾害预警] 连接信息 - URI: {connection_info.get('uri')}"
                        )

            logger.debug("[灾害预警] P2P处理器返回None，无有效事件")

        return p2p_handler

    def _create_wolfx_handler(self):
        """创建 Wolfx WebSocket 处理器"""

        async def wolfx_handler(message, connection_name=None, connection_info=None):
            # 利用connection_info增强日志记录
            if connection_info:
                logger.debug(
                    f"[灾害预警] Wolfx处理器收到消息 - 连接: {connection_name}, URI: {connection_info.get('uri', 'unknown')}"
                )
            else:
                logger.debug(
                    f"[灾害预警] Wolfx处理器收到消息 - 连接: {connection_name}"
                )

            # 根据连接名称选择具体的处理器
            if connection_name:
                source_mapping = {
                    "wolfx_japan_jma_eew": "jma_wolfx",
                    "wolfx_china_cenc_eew": "cea_wolfx",
                    "wolfx_taiwan_cwa_eew": "cwa_wolfx",
                    "wolfx_china_cenc_earthquake": "cenc_wolfx",
                    "wolfx_japan_jma_earthquake": "jma_wolfx_info",
                }

                target_source = source_mapping.get(connection_name)
                if target_source and target_source in self.service.handlers:
                    handler = self.service.handlers[target_source]
                    logger.debug(f"[灾害预警] 使用Wolfx处理器: {target_source}")

                    try:
                        event = handler.parse_message(message)
                        if event:
                            # 利用connection_info增强事件信息
                            if (
                                connection_info
                                and hasattr(event, "raw_data")
                                and isinstance(event.raw_data, dict)
                            ):
                                event.raw_data["connection_info"] = {
                                    "connection_name": connection_name,
                                    "uri": connection_info.get("uri"),
                                    "connection_type": connection_info.get(
                                        "connection_type"
                                    ),
                                    "established_time": connection_info.get(
                                        "established_time"
                                    ),
                                }

                            logger.debug(f"[灾害预警] Wolfx处理器解析成功: {event.id}")
                            await self.service._handle_disaster_event(event)
                            return
                    except Exception as e:
                        logger.error(
                            f"[灾害预警] Wolfx处理器解析消息失败 - 连接: {connection_name}, 错误: {e}"
                        )
                        if connection_info:
                            logger.error(
                                f"[灾害预警] 连接信息 - URI: {connection_info.get('uri')}"
                            )
                        return
                else:
                    logger.warning(
                        f"[灾害预警] 无法识别Wolfx连接名称: {connection_name}"
                    )
                    return
            else:
                logger.warning("[灾害预警] Wolfx处理器未收到连接名称")
                return

        return wolfx_handler

    def _create_global_quake_handler(self):
        """创建 Global Quake WebSocket 处理器"""

        async def global_quake_handler(
            message, connection_name=None, connection_info=None
        ):
            # 利用connection_info增强日志记录
            if connection_info:
                logger.debug(
                    f"[灾害预警] Global Quake处理器收到消息 - 连接: {connection_name}, URI: {connection_info.get('uri', 'unknown')}"
                )
            else:
                logger.debug(
                    f"[灾害预警] Global Quake处理器收到消息 - 连接: {connection_name}"
                )

            handler = self.service.handlers.get("global_quake")
            if handler:
                try:
                    event = handler.parse_message(message)
                    if event:
                        # 利用connection_info增强事件信息
                        if (
                            connection_info
                            and hasattr(event, "raw_data")
                            and isinstance(event.raw_data, dict)
                        ):
                            event.raw_data["connection_info"] = {
                                "connection_name": connection_name,
                                "uri": connection_info.get("uri"),
                                "connection_type": connection_info.get(
                                    "connection_type"
                                ),
                                "established_time": connection_info.get(
                                    "established_time"
                                ),
                            }

                        logger.debug(
                            f"[灾害预警] Global Quake处理器解析成功: {event.id}"
                        )
                        await self.service._handle_disaster_event(event)
                except Exception as e:
                    logger.error(
                        f"[灾害预警] Global Quake处理器解析消息失败 - 连接: {connection_name}, 错误: {e}"
                    )
                    if connection_info:
                        logger.error(
                            f"[灾害预警] 连接信息 - URI: {connection_info.get('uri')}"
                        )
            else:
                logger.warning("[灾害预警] 未找到Global Quake处理器")

        return global_quake_handler
