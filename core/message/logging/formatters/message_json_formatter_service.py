"""
消息 JSON 展示格式化服务。
负责键名翻译、值格式化与递归 JSON 文本渲染，
用于收缩 core/message/message_logger.py 中的展示规则实现。
"""

from __future__ import annotations

from typing import Any


class MessageJsonFormatterService:
    """消息 JSON 展示格式化服务。"""

    _KEY_MAPPINGS = {
        "id": "ID",
        "ID": "ID",
        "_id": "数据库ID",
        "type": "消息类型",
        "title": "标题",
        "key": "编号",
        "code": "消息代码",
        "source": "数据来源",
        "status": "状态",
        "action": "操作",
        "timestamp": "时间戳",
        "time": "发生时间",
        "createTime": "创建时间",
        "updateTime": "更新时间",
        "created_at": "创建时间",
        "updated_at": "更新时间",
        "started_at": "开始时间",
        "expire": "过期时间",
        "earthquake": "地震信息",
        "magnitude": "震级",
        "Magunitude": "震级",
        "depth": "深度(km)",
        "Depth": "深度(km)",
        "latitude": "纬度",
        "Latitude": "纬度",
        "longitude": "经度",
        "Longitude": "经度",
        "placeName": "地名",
        "name": "地点名称",
        "shockTime": "发震时间",
        "OriginTime": "发震时间",
        "place": "震中",
        "region": "震中",
        "hypocenter": "震源信息",
        "Hypocenter": "震源地名",
        "maxScale": "最大震度(原始)",
        "MaxIntensity": "最大烈度/震度",
        "maxIntensity": "最大烈度",
        "epiIntensity": "预估烈度",
        "intensity": "烈度",
        "shindo": "震度",
        "scale": "震度值",
        "domesticTsunami": "日本境内海啸",
        "foreignTsunami": "海外海啸",
        "tsunami": "海啸信息",
        "info": "海啸信息",
        "eventId": "事件ID",
        "EventID": "事件ID",
        "event_id": "事件ID",
        "EventId": "事件编码",
        "Serial": "报序号",
        "updates": "更新次数",
        "ReportNum": "发报数",
        "AnnouncedTime": "发布时间",
        "ReportTime": "发报时间",
        "time_full": "发报时间(完整)",
        "originTimeMs": "发震时间(MS)",
        "originTimeIso": "发震时间(ISO)",
        "lastUpdateMs": "最后更新(MS)",
        "effective": "生效时间",
        "issue_time": "发布时间",
        "arrivalTime": "到达时间",
        "isFinal": "最终报",
        "final": "最终报",
        "isCancel": "取消报",
        "cancel": "取消报",
        "is_final": "最终报",
        "is_cancel": "取消报",
        "cancelled": "取消标志",
        "fixedDepth": "固定深度",
        "is_training": "训练模式",
        "isTraining": "训练报",
        "isSea": "海域地震",
        "isAssumption": "推定震源",
        "isWarn": "警报标志",
        "immediate": "紧急标志",
        "headline": "预警标题",
        "description": "详细描述",
        "infoTypeName": "信息类型",
        "correct": "订正信息",
        "issue": "发布信息",
        "province": "省份",
        "pref": "都道府县",
        "addr": "观测点地址",
        "location": "震源地",
        "area": "区域代码",
        "isArea": "区域标志",
        "url": "官方链接",
        "OriginalText": "原电文",
        "Accuracy.Epicenter": "震中精度",
        "Accuracy.Depth": "深度精度",
        "Accuracy.Magnitude": "震级精度",
        "confidence": "可信度",
        "warningInfo": "警报核心信息",
        "timeInfo": "时间信息",
        "details": "详细信息",
        "forecasts": "沿海预报",
        "waterLevelMonitoring": "水位监测",
        "estimatedArrivalTime": "预计到达时间",
        "maxWaveHeight": "最大波高",
        "warningLevel": "警报级别",
        "stationName": "监测站名称",
        "firstHeight": "初波信息",
        "maxHeight": "最大波高",
        "condition": "状态描述",
        "grade": "预警级别",
        "points": "震度观测点",
        "comments": "附加评论",
        "freeFormComment": "自由附加文",
        "areas": "预警区域",
        "MaxIntChange.String": "震度变更说明",
        "MaxIntChange.Reason": "震度变更原因",
        "CodeType": "发报说明",
        "Title": "发报报头",
        "hop": "跳数(hop)",
        "uid": "用户ID",
        "ver": "版本号",
        "user-agent": "客户端标识",
        "count": "计数",
        "area_confidences": "区域置信度",
        "autoFlag": "自动标志",
        "earthtype": "地震类型",
        "md5": "校验码",
        "revisionId": "修订版本号",
        "maxPGA": "最大地表加速度",
        "cluster": "集群信息",
        "level": "级别",
        "quality": "质量指标",
        "errOrigin": "时间误差",
        "errDepth": "深度误差",
        "errNS": "南北向误差",
        "errEW": "东西向误差",
        "pct": "置信度百分比",
        "stations": "参与定位的台站数",
        "stationCount": "台站统计",
        "total": "总可用台站数",
        "selected": "被选中参与计算的台站数",
        "used": "实际用于定位的台站数",
        "matching": "匹配度高的台站数",
        "depthConfidence": "深度置信度",
        "minDepth": "最小深度",
        "maxDepth": "最大深度",
        "connection_type": "连接类型",
        "server": "服务器",
        "port": "端口",
        "status_code": "状态码",
    }

    _MAX_SCALE_MAP = {
        10: "震度1",
        20: "震度2",
        30: "震度3",
        40: "震度4",
        45: "震度5弱",
        50: "震度5強",
        55: "震度6弱",
        60: "震度6強",
        70: "震度7",
    }

    _LEVEL_MAP = {
        0: "0: 弱 (4+台站近距离触发)",
        1: "1: 中 (7+台站>64计数 或 4+台站>1,000计数)",
        2: "2: 强 (7+台站>1,000计数 或 3+台站>10,000计数)",
        3: "3: 极强 (5+台站>10,000计数 或 3+台站>50,000计数)",
        4: "4: 毁灭 (4+台站>50,000计数)",
    }

    def __init__(self, logger_instance):
        # 通过注入 logger_instance 复用区域映射等上下文，而不把这类只读数据再拷贝一份。
        self.logger = logger_instance

    def format_json_data(self, data: dict[str, Any], indent: int = 0) -> str:
        """递归格式化 JSON 数据，增加可读性。"""
        # 这里输出的是“人类可读日志文本”，因此优先追求字段可解释性而非 JSON 原样保真。
        result = ""
        indent_str = "  " * indent

        for key, value in data.items():
            key_display = self.get_display_key(key)

            if isinstance(value, dict):
                result += f"{indent_str}📋 {key_display}:\n"
                result += self.format_json_data(value, indent + 1)
            elif isinstance(value, list):
                if value:
                    result += f"{indent_str}📋 {key_display} ({len(value)}项):\n"
                    for i, item in enumerate(value[:5]):
                        if isinstance(item, dict):
                            result += f"{indent_str}  [{i + 1}]:\n"
                            result += self.format_json_data(item, indent + 2)
                        else:
                            result += f"{indent_str}  [{i + 1}]: {item}\n"
                    if len(value) > 5:
                        result += f"{indent_str}  ... 还有 {len(value) - 5} 项\n"
                else:
                    result += f"{indent_str}📋 {key_display}: []\n"
            else:
                result += (
                    f"{indent_str}📋 {key_display}: {self.format_value(key, value)}\n"
                )

        return result

    def get_display_key(self, key: str) -> str:
        """获取格式化后的键名显示。"""
        return self._KEY_MAPPINGS.get(key, key)

    def format_value(self, key: str, value: Any) -> str:
        """格式化具体值。"""
        if value is None:
            return "无数据"
        if value == "":
            return "空字符串"
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, (int, float)):
            return self._format_numeric_value(key, value)
        if isinstance(value, str):
            return f"{value[:47]}..." if len(value) > 50 else value
        return str(value)

    def _format_numeric_value(self, key: str, value: int | float) -> str:
        """格式化数值类型。"""
        if key == "maxScale" and isinstance(value, int):
            return f"{value} ({self._MAX_SCALE_MAP.get(value, '未知')})"
        if key in ["magnitude", "Magnitude", "Magunitude"]:
            return f"M{value:.2f}" if isinstance(value, float) else f"M{value}"
        if key in ["depth", "Depth"]:
            return f"{value:.2f}km" if isinstance(value, float) else f"{value}km"
        if key in ["latitude", "Latitude", "longitude", "Longitude"]:
            return f"{value:.5f}"
        if key in [
            "maxPGA",
            "errOrigin",
            "errDepth",
            "errNS",
            "errEW",
            "pct",
            "minDepth",
            "maxDepth",
        ] and isinstance(value, float):
            return f"{value:.3f}"
        if key == "area" and isinstance(value, int):
            region_name = self.logger.p2p_area_mapping.get(value, f"区域代码{value}")
            return f"{value} ({region_name})"
        if key == "level" and isinstance(value, int):
            return f"{value} ({self._LEVEL_MAP.get(value, '未知级别')})"
        return str(value)
