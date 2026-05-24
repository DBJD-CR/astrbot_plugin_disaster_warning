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
        # 🌍 基础信息字段 (所有数据源通用)
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
        # 🏔️ 地震核心信息
        "earthquake": "地震信息",
        "magnitude": "震级",
        "Magunitude": "震级",  # Wolfx拼写
        "depth": "深度(km)",
        "Depth": "深度(km)",  # 大写版本
        "latitude": "纬度",
        "Latitude": "纬度",  # 大写版本
        "longitude": "经度",
        "Longitude": "经度",  # 大写版本
        "placeName": "地名",
        "name": "地点名称",
        "shockTime": "发震时间",
        "OriginTime": "发震时间",  # JMA格式
        "place": "震中",
        "region": "震中",  # Global Quake格式
        "hypocenter": "震源信息",
        "Hypocenter": "震源地名",  # JMA格式
        # 📍 震度/烈度信息
        "maxScale": "最大震度(原始)",
        "MaxIntensity": "最大烈度/震度",  # JMA/Wolfx格式
        "maxIntensity": "最大烈度",  # Wolfx格式
        "epiIntensity": "预估烈度",  # FAN Studio格式
        "intensity": "烈度",
        "shindo": "震度",  # JMA格式
        "scale": "震度值",  # P2P格式
        # 🌊 海啸相关信息
        "domesticTsunami": "日本境内海啸",
        "foreignTsunami": "海外海啸",
        "tsunami": "海啸信息",
        "info": "海啸信息",  # Wolfx格式
        # 📋 事件标识信息
        "eventId": "事件ID",
        "EventID": "事件ID",  # JMA格式
        "event_id": "事件ID",  # 下划线版本
        "EventId": "事件编码",  # FAN Studio格式
        "Serial": "报序号",  # JMA格式
        "updates": "更新次数",
        "ReportNum": "发报数",  # Wolfx格式
        # ⏰ 时间相关
        "AnnouncedTime": "发布时间",  # JMA格式
        "ReportTime": "发报时间",  # Wolfx格式
        "time_full": "发报时间(完整)",
        "originTimeMs": "发震时间(MS)",
        "originTimeIso": "发震时间(ISO)",
        "lastUpdateMs": "最后更新(MS)",
        "effective": "生效时间",  # FAN Studio格式
        "issue_time": "发布时间",
        "arrivalTime": "到达时间",  # 海啸
        # 🎯 状态标志
        "isFinal": "最终报",
        "final": "最终报",  # FAN Studio格式
        "isCancel": "取消报",
        "cancel": "取消报",  # FAN Studio格式
        "is_final": "最终报",
        "is_cancel": "取消报",
        "cancelled": "取消标志",  # P2P格式
        "fixedDepth": "固定深度",
        "is_training": "训练模式",
        "isTraining": "训练报",  # Wolfx格式
        "isSea": "海域地震",  # Wolfx格式
        "isAssumption": "推定震源",  # Wolfx格式
        "isWarn": "警报标志",  # Wolfx格式
        "immediate": "紧急标志",  # 海啸
        # 📰 内容描述
        "headline": "预警标题",  # FAN Studio格式
        "description": "详细描述",  # FAN Studio格式
        "infoTypeName": "信息类型",  # FAN Studio格式
        "correct": "订正信息",
        "issue": "发布信息",
        # 🗺️ 地理区域
        "province": "省份",  # FAN Studio格式
        "pref": "都道府县",  # P2P格式
        "addr": "观测点地址",  # P2P格式
        "location": "震源地",  # Wolfx格式
        "area": "区域代码",  # P2P格式
        "isArea": "区域标志",  # P2P格式
        # 🔗 链接和参考
        "url": "官方链接",
        "OriginalText": "原电文",  # Wolfx格式
        # 📊 精度和可信度
        "Accuracy.Epicenter": "震中精度",  # Wolfx格式
        "Accuracy.Depth": "深度精度",  # Wolfx格式
        "Accuracy.Magnitude": "震级精度",  # Wolfx格式
        "confidence": "可信度",  # P2P格式
        # 🌊 海啸详细信息
        "warningInfo": "警报核心信息",
        "timeInfo": "时间信息",
        "details": "详细信息",
        "forecasts": "沿海预报",
        "waterLevelMonitoring": "水位监测",
        "estimatedArrivalTime": "预计到达时间",
        "maxWaveHeight": "最大波高",
        "warningLevel": "警报级别",
        "stationName": "监测站名称",
        "firstHeight": "初波信息",  # 海啸
        "maxHeight": "最大波高",  # 海啸
        "condition": "状态描述",  # 海啸
        "grade": "预警级别",  # 海啸
        # 📍 观测点信息 (P2P)
        "points": "震度观测点",
        "comments": "附加评论",
        "freeFormComment": "自由附加文",
        "areas": "预警区域",  # 海啸和P2P
        # ⚠️ 变更和警报信息
        "MaxIntChange.String": "震度变更说明",  # Wolfx格式
        "MaxIntChange.Reason": "震度变更原因",  # Wolfx格式
        "CodeType": "发报说明",  # Wolfx格式
        "Title": "发报报头",  # Wolfx格式
        # 🔧 技术字段
        "hop": "跳数(hop)",
        "uid": "用户ID",
        "ver": "版本号",
        "user-agent": "客户端标识",
        "count": "计数",
        "area_confidences": "区域置信度",
        "autoFlag": "自动标志",  # FAN Studio格式
        "earthtype": "地震类型",  # FAN Studio格式
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
        # 🔌 连接信息 (保留原有)
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
        # 通过注入记录器实例复用区域映射等只读上下文，避免重复持有同类数据。
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
        """按字段语义格式化数值类型。"""
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
