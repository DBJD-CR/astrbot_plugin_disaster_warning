"""
WebSocket消息处理器注册中心
负责创建和注册各种数据源的WebSocket消息处理器
"""
import json
from typing import Optional, Dict, Any

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
        
        async def fan_studio_handler(message, connection_name=None, connection_info=None):
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
                # 首先尝试通过连接名称直接识别数据源
                if connection_name:
                    direct_source_mapping = {
                        "fan_studio_cea": "cea_fanstudio",
                        "fan_studio_cwa": "cwa_fanstudio",
                        "fan_studio_cenc": "cenc_fanstudio",
                        "fan_studio_usgs": "usgs_fanstudio",
                        "fan_studio_jma": "jma_fanstudio",
                        "fan_studio_weather": "china_weather_fanstudio",
                        "fan_studio_tsunami": "china_tsunami_fanstudio",
                    }

                    target_source = direct_source_mapping.get(connection_name)
                    if target_source and target_source in self.service.handlers:
                        handler = self.service.handlers[target_source]
                        logger.debug(
                            f"[灾害预警] 通过连接名称使用处理器: {target_source} (连接: {connection_name})"
                        )

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
                                f"[灾害预警] FAN Studio处理器解析成功: {event.id}"
                            )
                            await self.service._handle_disaster_event(event)
                            return
                        else:
                            logger.debug(
                                "[灾害预警] FAN Studio处理器返回None，无有效事件"
                            )
                            return

                # 如果直接映射失败，尝试智能识别（类似v1.0.0的机制）
                logger.debug(f"[灾害预警] 开始智能识别数据源，连接: {connection_name}")

                # 尝试解析JSON来识别数据源类型
                try:
                    data = json.loads(message)

                    # 获取实际数据 - 注意FAN Studio使用大写D的Data字段
                    msg_data = data.get("Data", {}) or data.get("data", {})
                    if not msg_data:
                        logger.warning(
                            f"[灾害预警] 消息中没有Data/data字段，连接: {connection_name}"
                        )
                        # 尝试直接处理原始数据
                        msg_data = data

                    # 根据消息内容特征识别数据源
                    if "epiIntensity" in msg_data:
                        # 中国地震预警网格式
                        handler = self.service.handlers.get("cea_fanstudio")
                        if handler:
                            logger.debug("[灾害预警] 智能识别为CEA预警数据")
                            event = handler.parse_message(message)
                        else:
                            logger.warning("[灾害预警] 未找到CEA处理器")
                            return None
                    elif "maxIntensity" in msg_data and "createTime" in msg_data:
                        # 台湾中央气象署格式
                        handler = self.service.handlers.get("cwa_fanstudio")
                        if handler:
                            logger.debug("[灾害预警] 智能识别为CWA数据")
                            event = handler.parse_message(message)
                        else:
                            logger.warning("[灾害预警] 未找到CWA处理器")
                            return None
                    elif "infoTypeName" in msg_data and (
                        "[正式测定]" in message or "[自动测定]" in message
                    ):
                        # 中国地震台网格式
                        handler = self.service.handlers.get("cenc_fanstudio")
                        if handler:
                            logger.debug("[灾害预警] 智能识别为CENC数据")
                            event = handler.parse_message(message)
                        else:
                            logger.warning("[灾害预警] 未找到CENC处理器")
                            return None
                    elif "headline" in msg_data and "预警信号" in message:
                        # 气象预警
                        handler = self.service.handlers.get("china_weather_fanstudio")
                        if handler:
                            logger.debug("[灾害预警] 智能识别为气象预警数据")
                            event = handler.parse_message(message)
                        else:
                            logger.warning("[灾害预警] 未找到气象预警处理器")
                            return None
                    elif "warningInfo" in msg_data and "title" in msg_data:
                        # 海啸预警
                        handler = self.service.handlers.get("china_tsunami_fanstudio")
                        if handler:
                            logger.debug("[灾害预警] 智能识别为海啸预警数据")
                            event = handler.parse_message(message)
                        else:
                            logger.warning("[灾害预警] 未找到海啸预警处理器")
                            return None
                    elif "usgs" in message or (
                        "placeName" in msg_data and "updateTime" in msg_data
                    ):
                        # USGS
                        handler = self.service.handlers.get("usgs_fanstudio")
                        if handler:
                            logger.debug("[灾害预警] 智能识别为USGS数据")
                            event = handler.parse_message(message)
                        else:
                            logger.warning("[灾害预警] 未找到USGS处理器")
                            return None
                    else:
                        # 默认使用CEA处理器
                        handler = self.service.handlers.get("cea_fanstudio")
                        if handler:
                            logger.debug(
                                f"[灾害预警] 无法识别数据源，默认使用CEA处理器，连接: {connection_name}"
                            )
                            event = handler.parse_message(message)
                        else:
                            logger.warning("[灾害预警] 未找到默认CEA处理器")
                            return None

                except json.JSONDecodeError as e:
                    logger.error(f"[灾害预警] JSON解析失败: {e}")
                    return None
                except Exception as e:
                    logger.error(f"[灾害预警] 智能识别过程失败: {e}")
                    return None

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
                            "connection_type": connection_info.get("connection_type"),
                            "established_time": connection_info.get("established_time"),
                        }

                    logger.debug(f"[灾害预警] FAN Studio处理器解析成功: {event.id}")
                    await self.service._handle_disaster_event(event)
                else:
                    logger.debug("[灾害预警] FAN Studio处理器返回None，无有效事件")

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
        
        async def global_quake_handler(message, connection_name=None, connection_info=None):
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
                                "connection_type": connection_info.get("connection_type"),
                                "established_time": connection_info.get("established_time"),
                            }

                        logger.debug(f"[灾害预警] Global Quake处理器解析成功: {event.id}")
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
