"""模拟预警服务：集中管理模拟参数与地震模拟流程。"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ...models.models import (
    DATA_SOURCE_MAPPING,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
    get_data_source_from_id,
)
from ...utils.fe_regions import translate_place_name


@dataclass(slots=True)
class SimulationBuildResult:
    """地震模拟构建结果。"""

    earthquake: EarthquakeData
    disaster_event: DisasterEvent
    report_lines: list[str]
    global_pass: bool
    local_pass: bool


@dataclass(slots=True)
class SimulationParamsDefaults:
    """前后端统一使用的默认模拟参数。"""

    latitude: float = 39.9
    longitude: float = 116.4
    magnitude: float = 5.5
    depth: float = 10.0
    source: str = "cea_fanstudio"


# 进程内模拟事件递增计数器：用于避免同秒多次触发时 ID 冲突
_sim_event_sequence = 0
_sim_event_sequence_lock = threading.Lock()


def _next_sim_event_sequence() -> int:
    """获取下一个模拟事件序号（线程安全，单调递增）。"""
    global _sim_event_sequence
    with _sim_event_sequence_lock:
        _sim_event_sequence += 1
        return _sim_event_sequence


def get_simulation_params(config: dict[str, Any]) -> dict[str, Any]:
    """获取模拟预警可用参数（集中管理，供 Web API 使用）。"""
    raw_target_sessions = config.get("target_sessions", [])
    target_sessions = [str(item) for item in raw_target_sessions]

    defaults = SimulationParamsDefaults()

    # 当前版本仅开放 earthquake，避免前端额外硬编码过滤。
    disaster_types = {
        "earthquake": {
            "label": "地震",
            "icon": "🌍",
            "formats": [
                {
                    "value": "cea_fanstudio",
                    "label": "FAN Studio - 中国地震预警网 (CEA)",
                },
                {
                    "value": "cea_pr_fanstudio",
                    "label": "FAN Studio - 中国地震预警网 (省级)",
                },
                {
                    "value": "cenc_fanstudio",
                    "label": "FAN Studio - 中国地震台网 (CENC)",
                },
                {
                    "value": "cwa_fanstudio",
                    "label": "FAN Studio - 台湾中央气象署 (强震即时警报)",
                },
                {
                    "value": "cwa_fanstudio_report",
                    "label": "FAN Studio - 台湾中央气象署 (地震报告)",
                },
                {"value": "jma_fanstudio", "label": "FAN Studio - 日本气象厅 (JMA)"},
                {"value": "usgs_fanstudio", "label": "FAN Studio - USGS"},
                {"value": "jma_wolfx", "label": "Wolfx - 日本 JMA 紧急地震速报"},
                {"value": "cea_wolfx", "label": "Wolfx - 中国 CENC 地震预警"},
                {"value": "cwa_wolfx", "label": "Wolfx - 台湾 CWA 地震预警"},
                {"value": "cenc_wolfx", "label": "Wolfx - 中国 CENC 地震情报"},
                {"value": "jma_wolfx_info", "label": "Wolfx - 日本 JMA 地震情报"},
                {"value": "jma_p2p", "label": "P2P - 日本 JMA 紧急地震速报"},
                {"value": "jma_p2p_info", "label": "P2P - 日本 JMA 地震情报"},
                {"value": "global_quake", "label": "Global Quake"},
            ],
            "defaults": {
                "latitude": defaults.latitude,
                "longitude": defaults.longitude,
                "magnitude": defaults.magnitude,
                "depth": defaults.depth,
                "source": defaults.source,
            },
        }
    }

    return {
        "target_sessions": target_sessions,
        "disaster_types": disaster_types,
        "timestamp": datetime.now().isoformat(),
    }


def resolve_target_session(
    config: dict[str, Any], target_session: str = ""
) -> str | None:
    """解析模拟发送目标会话。"""
    if target_session:
        return target_session

    target_sessions = config.get("target_sessions", [])
    if target_sessions:
        return target_sessions[0]
    return None


def build_earthquake_simulation(
    manager: Any,
    *,
    lat: float,
    lon: float,
    magnitude: float,
    depth: float,
    source: str,
) -> SimulationBuildResult:
    """构建地震模拟数据并执行过滤器测试。"""
    data_source = get_data_source_from_id(source)
    if not data_source:
        valid_sources = ", ".join(DATA_SOURCE_MAPPING.keys())
        raise ValueError(f"无效的数据源: {source}，可用数据源: {valid_sources}")

    now = datetime.now()
    ts = int(now.timestamp())
    seq = _next_sim_event_sequence()
    sim_id_suffix = f"{ts}_{seq}"
    final_place_name = translate_place_name("模拟震中", lat, lon)

    earthquake = EarthquakeData(
        id=f"sim_{sim_id_suffix}",
        event_id=f"sim_{sim_id_suffix}",
        source=data_source,
        disaster_type=DisasterType.EARTHQUAKE,
        shock_time=now,
        latitude=lat,
        longitude=lon,
        depth=depth,
        magnitude=magnitude,
        place_name=final_place_name,
        source_id=source,
        raw_data={"test": True, "source_id": source},
    )

    if source == "usgs_fanstudio":
        earthquake.update_time = datetime.now()

    if source in ["jma_p2p", "jma_wolfx", "jma_p2p_info"]:
        earthquake.max_scale = max(0, min(7, int(magnitude - 2)))
        earthquake.scale = earthquake.max_scale

    disaster_event = DisasterEvent(
        id=f"sim_evt_{sim_id_suffix}",
        data=earthquake,
        source=data_source,
        disaster_type=DisasterType.EARTHQUAKE,
        source_id=source,
    )

    report_lines = [
        "🧪 灾害预警模拟报告",
        f"Input: M{magnitude} @ ({lat}, {lon}), Depth {depth}km\n",
    ]

    global_pass = True
    if manager.intensity_filter:
        if manager.intensity_filter.should_filter(earthquake):
            global_pass = False
            report_lines.append("❌ 全局过滤: 拦截 (不满足最小震级/烈度要求)")
        else:
            report_lines.append("✅ 全局过滤: 通过")

    local_pass = True
    if manager.local_monitor:
        result = manager.local_monitor.inject_local_estimation(earthquake)

        if result is None:
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

    return SimulationBuildResult(
        earthquake=earthquake,
        disaster_event=disaster_event,
        report_lines=report_lines,
        global_pass=global_pass,
        local_pass=local_pass,
    )
