"""
GlobalQuake protobuf 解析服务。
负责将 models/websocket_message_pb2.py 二进制载荷转换为结构化字典，
减少 core/message/message_logger.py 中的协议解析职责。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ....models.websocket_message_pb2 import MessageAction, MessageType, WsMessage


class GlobalQuakeProtobufParser:
    """GlobalQuake protobuf 解析器。"""

    _TYPE_MAPPING = {
        MessageType.EARTHQUAKE: "earthquake",
        MessageType.STATUS: "status",
        MessageType.HEARTBEAT: "heartbeat",
    }

    _ACTION_MAPPING = {
        MessageAction.UPDATE: "update",
        MessageAction.CONNECTED: "connected",
        MessageAction.DISCONNECTED: "disconnected",
        MessageAction.PING: "ping",
        MessageAction.PONG: "pong",
    }

    def __init__(self, timestamp_formatter: Callable[[int], str]):
        self._timestamp_formatter = timestamp_formatter

    def parse(self, binary_data: bytes) -> dict[str, Any] | None:
        """解析 GlobalQuake protobuf 二进制数据为可读字典。"""
        # 先解析 protobuf，再统一投影成普通 dict，便于日志系统与 JSON 格式化器复用。
        ws_msg = WsMessage()
        ws_msg.ParseFromString(binary_data)

        parsed: dict[str, Any] = {
            "type": self._TYPE_MAPPING.get(ws_msg.type, "unknown"),
            "action": self._ACTION_MAPPING.get(ws_msg.action, "unspecified"),
            "timestamp": self._timestamp_formatter(ws_msg.timestamp_ms),
            "protobuf": True,
        }

        if ws_msg.type == MessageType.EARTHQUAKE:
            parsed["data"] = self._build_earthquake_payload(ws_msg)
        elif ws_msg.type == MessageType.STATUS:
            parsed["data"] = {
                "status": ws_msg.status_data.server_status,
            }
        elif ws_msg.type == MessageType.HEARTBEAT:
            parsed["data"] = {
                "serverTime": self._timestamp_formatter(
                    ws_msg.heartbeat_data.server_time
                ),
            }
        else:
            return None

        return parsed

    def _build_earthquake_payload(self, ws_msg: WsMessage) -> dict[str, Any]:
        """构建地震消息数据载荷。"""
        eq = ws_msg.earthquake_data
        data: dict[str, Any] = {
            "id": eq.id,
            "latitude": eq.latitude,
            "longitude": eq.longitude,
            "depth": eq.depth,
            "magnitude": eq.magnitude,
            "originTimeMs": eq.origin_time_ms,
            "originTimeIso": eq.origin_time_iso,
            "lastUpdateMs": eq.last_update_ms,
            "revisionId": eq.revision_id,
            "region": eq.region,
            "fixedDepth": eq.fixed_depth,
            "maxPGA": eq.max_pga,
            "intensity": eq.intensity,
        }

        if eq.HasField("cluster"):
            data["cluster"] = {
                "id": eq.cluster.id,
                "latitude": eq.cluster.latitude,
                "longitude": eq.cluster.longitude,
                "level": eq.cluster.level,
            }

        if eq.HasField("quality"):
            data["quality"] = {
                "errOrigin": eq.quality.err_origin,
                "errDepth": eq.quality.err_depth,
                "errNS": eq.quality.err_ns,
                "errEW": eq.quality.err_ew,
                "pct": eq.quality.pct,
                "stations": eq.quality.stations,
            }

        if eq.HasField("station_count"):
            data["stationCount"] = {
                "total": eq.station_count.total,
                "selected": eq.station_count.selected,
                "used": eq.station_count.used,
                "matching": eq.station_count.matching,
            }

        if eq.HasField("depth_confidence"):
            data["depthConfidence"] = {
                "minDepth": eq.depth_confidence.min_depth,
                "maxDepth": eq.depth_confidence.max_depth,
            }

        return data
