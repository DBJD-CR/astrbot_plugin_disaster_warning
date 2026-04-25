"""
数据源历史兼容工具。

职责：
- 统一 source/source_id 的历史别名到规范 key
- 生成前端展示标签
- 为数据库筛选展开同义别名集合

这是一个临时兼容层，用于避免将大量历史兼容逻辑堆进 core/storage/database_manager.py 本体。
"""

from __future__ import annotations

from collections.abc import Iterable

# 历史别名映射表：把旧来源名、展示名和外部兼容名统一折叠到规范 source_id。
_ALIAS_MAP: dict[str, str] = {
    "fan_studio_cenc": "cenc_fanstudio",
    "fan_studio_cea": "cea_fanstudio",
    "fan_studio_cea_pr": "cea_pr_fanstudio",
    "fan_studio_cwa": "cwa_fanstudio",
    "fan_studio_cwa_report": "cwa_fanstudio_report",
    "fan_studio_usgs": "usgs_fanstudio",
    "fan_studio_jma": "jma_fanstudio",
    "fan_studio_weather": "china_weather_fanstudio",
    "fan_studio_tsunami": "china_tsunami_fanstudio",
    "p2p_eew": "jma_p2p",
    "p2p_earthquake": "jma_p2p_info",
    "p2p_tsunami": "jma_tsunami_p2p",
    "wolfx_jma_eew": "jma_wolfx",
    "wolfx_cenc_eew": "cea_wolfx",
    "wolfx_cwa_eew": "cwa_wolfx",
    "wolfx_cenc_eq": "cenc_wolfx",
    "wolfx_jma_eq": "jma_wolfx_info",
    "china_earthquake_warning": "cea_fanstudio",
    "china_earthquake_warning_provincial": "cea_pr_fanstudio",
    "taiwan_cwa_earthquake": "cwa_fanstudio",
    "taiwan_cwa_report": "cwa_fanstudio_report",
    "china_cenc_earthquake": "cenc_fanstudio",
    "usgs_earthquake": "usgs_fanstudio",
    "china_weather_alarm": "china_weather_fanstudio",
    "china_tsunami": "china_tsunami_fanstudio",
    "japan_jma_eew": "jma_p2p",
    "japan_jma_earthquake": "jma_p2p_info",
    "japan_jma_tsunami": "jma_tsunami_p2p",
    "china_cenc_eew": "cea_wolfx",
    "taiwan_cwa_eew": "cwa_wolfx",
    "中国气象局：气象预警": "china_weather_fanstudio",
    "中国气象局: 气象预警": "china_weather_fanstudio",
    "台湾中央气象署：强震即时警报": "cwa_fanstudio",
    "台湾中央气象署: 强震即时警报": "cwa_fanstudio",
    "台湾中央气象署：地震报告": "cwa_fanstudio_report",
    "台湾中央气象署: 地震报告": "cwa_fanstudio_report",
    "中国地震台网（cenc）": "cenc_fanstudio",
    "中国地震台网(cenc)": "cenc_fanstudio",
    "中国地震台网（cenc）：地震测定": "cenc_fanstudio",
    "中国地震台网(cenc)：地震测定": "cenc_fanstudio",
    "中国地震预警网（cea）": "cea_fanstudio",
    "中国地震预警网(cea)": "cea_fanstudio",
    "中国地震预警网（省级）": "cea_pr_fanstudio",
    "中国地震预警网(省级)": "cea_pr_fanstudio",
    "日本气象厅：紧急地震速报": "jma_fanstudio",
    "日本气象厅: 紧急地震速报": "jma_fanstudio",
    "日本气象厅：地震情报": "jma_p2p_info",
    "日本气象厅: 地震情报": "jma_p2p_info",
    "日本气象厅：海啸预报": "jma_tsunami_p2p",
    "日本气象厅: 海啸预报": "jma_tsunami_p2p",
}

# 展示名称映射表：用于把内部规范 key 转回更友好的前端展示标签。
_DISPLAY_MAP: dict[str, str] = {
    "cenc_fanstudio": "中国地震台网 (CENC) - Fan",
    "cea_fanstudio": "中国地震预警网 (CEA)",
    "cea_pr_fanstudio": "中国地震预警网 (省级)",
    "cwa_fanstudio": "台湾中央气象署: 强震即时警报 - Fan",
    "cwa_fanstudio_report": "台湾中央气象署: 地震报告",
    "usgs_fanstudio": "美国地质调查局 (USGS)",
    "jma_fanstudio": "日本气象厅: 紧急地震速报 - Fan",
    "china_weather_fanstudio": "中国气象局: 气象预警",
    "china_tsunami_fanstudio": "自然资源部海啸预警中心",
    "jma_p2p": "日本气象厅: 紧急地震速报 - P2P",
    "jma_p2p_info": "日本气象厅: 地震情报 - P2P",
    "jma_tsunami_p2p": "日本气象厅: 海啸予报",
    "jma_wolfx": "日本气象厅: 紧急地震速报 - Wolfx",
    "cea_wolfx": "中国地震预警网 (CEA) - Wolfx",
    "cwa_wolfx": "台湾中央气象署: 强震即时警报 - Wolfx",
    "cenc_wolfx": "中国地震台网地震测定 - Wolfx",
    "jma_wolfx_info": "日本气象厅地震情报 - Wolfx",
    "global_quake": "Global Quake",
    "sc_eew": "四川地震局",
    "fj_eew": "福建地震局",
    "kma_earthquake": "韩国气象厅 (KMA)",
    "emsc_earthquake": "欧洲地中海地震中心 (EMSC)",
    "gfz_earthquake": "德国地学研究中心 (GFZ)",
    "enabled": "实时数据流",
    "unknown": "未知来源",
}


def normalize_source_name(source: str) -> str:
    """把任意来源名归一化为稳定的内部 key。"""
    raw_source = str(source or "").strip()
    if not raw_source:
        # 空来源统一折叠为 unknown，避免后续展示与筛选阶段出现空字符串分支。
        return "unknown"
    lower_source = raw_source.lower()
    # 先按原值匹配，再按小写匹配历史别名；若都未命中，则回退为小写标准形态。
    return _ALIAS_MAP.get(raw_source) or _ALIAS_MAP.get(lower_source) or lower_source


def format_source_name(source: str) -> str:
    """把来源标识格式化为更适合展示的中文标签。"""
    normalized = normalize_source_name(source)
    return _DISPLAY_MAP.get(normalized) or str(source or "").strip() or "未知来源"


def expand_source_aliases(sources: Iterable[str]) -> list[str]:
    """展开一组来源名对应的全部别名与展示名。

    这样数据库查询时可以同时兼容旧字段值、规范 key 与展示标签，
    降低历史数据格式不统一带来的筛选遗漏。
    """
    # canonical_keys 保存规范来源标识，expanded 保存可用于查询兼容的全部候选值。
    canonical_keys: set[str] = set()
    expanded: set[str] = set()

    for source in sources:
        # 第一轮先把原始输入、规范标识和展示名称都纳入候选集合。
        raw = str(source or "").strip()
        if not raw:
            continue
        canonical = normalize_source_name(raw)
        canonical_keys.add(canonical)
        expanded.add(raw)
        expanded.add(canonical)
        expanded.add(format_source_name(raw))

    for alias, canonical in _ALIAS_MAP.items():
        # 第二轮反向补全所有历史别名，尽量覆盖旧数据库中的遗留写法。
        if canonical in canonical_keys:
            expanded.add(alias)
            expanded.add(alias.lower())

    for canonical in canonical_keys:
        # 最后补回规范标识本身及其展示名，避免结果集合缺项。
        expanded.add(canonical)
        expanded.add(format_source_name(canonical))

    return sorted(item for item in expanded if item)
