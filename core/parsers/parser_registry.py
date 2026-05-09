"""
统一解析器注册入口。
负责根据数据源目录解析解析器类型，并集中维护解析器名称到解析器类的静态映射。
"""

from __future__ import annotations

from ..sources.source_catalog import SOURCE_CATALOG, get_source_entry
from .china_earthquake_parser import CencEarthquakeParser, CencEarthquakeWolfxParser
from .china_eew_parser import CEAEEWParser, CEAEEWPRParser, CEAEEWWolfxParser
from .global_sources_parser import GlobalQuakeParser, UsgsEarthquakeParser
from .japan_earthquake_parser import JmaEarthquakeP2PParser, JmaEarthquakeWolfxParser
from .japan_eew_parser import JmaEewFanStudioParser, JmaEewP2PParser, JmaEewWolfxParser
from .taiwan_earthquake_parser import CwaReportParser
from .taiwan_eew_parser import CwaEewParser, CwaEewWolfxParser
from .tsunami_parser import JmaTsunamiP2PParser, TsunamiParser
from .weather_parser import WeatherAlarmParser

PARSER_CLASS_BY_NAME = {
    "china_eew_parser": CEAEEWParser,
    "china_report_parser": CencEarthquakeParser,
    "taiwan_eew_parser": CwaEewParser,
    "taiwan_report_parser": CwaReportParser,
    "japan_eew_parser": JmaEewFanStudioParser,
    "japan_report_parser": JmaEarthquakeP2PParser,
    "china_tsunami_parser": TsunamiParser,
    "japan_tsunami_parser": JmaTsunamiP2PParser,
    "weather_alarm_parser": WeatherAlarmParser,
    "global_report_parser": UsgsEarthquakeParser,
    "global_quake_parser": GlobalQuakeParser,
}


def resolve_parser_class(parser_name: str):
    """按解析器名称解析对应的解析器类。"""
    normalized_name = (parser_name or "").strip()
    if not normalized_name:
        return None
    return PARSER_CLASS_BY_NAME.get(normalized_name)


def create_parser_for_source(source_id: str, *args, **kwargs):
    """按数据源标识创建解析器实例。"""
    entry = get_source_entry(source_id)
    if entry is None:
        return None

    # 同名 parser 可能对应多个具体来源实现，这里按 source_id 再做一次细分分派。
    if entry.parser_name == "china_eew_parser":
        parser_class = {
            "cea_fanstudio": CEAEEWParser,
            "cea_pr_fanstudio": CEAEEWPRParser,
            "cea_wolfx": CEAEEWWolfxParser,
        }.get(source_id)
        if parser_class is None:
            return None
        return parser_class(*args, **kwargs)

    # 日本预警与日本地震情报会按具体来源拆成多个解析器实现，因此这里再做一次细分分派。
    if entry.parser_name == "japan_eew_parser":
        parser_class = {
            "jma_fanstudio": JmaEewFanStudioParser,
            "jma_p2p": JmaEewP2PParser,
            "jma_wolfx": JmaEewWolfxParser,
        }.get(source_id)
        if parser_class is None:
            return None
        return parser_class(*args, **kwargs)

    if entry.parser_name == "japan_report_parser":
        parser_class = {
            "jma_p2p_info": JmaEarthquakeP2PParser,
            "jma_wolfx_info": JmaEarthquakeWolfxParser,
        }.get(source_id)
        if parser_class is None:
            return None
        return parser_class(*args, **kwargs)

    if entry.parser_name == "china_report_parser":
        parser_class = {
            "cenc_fanstudio": CencEarthquakeParser,
            "cenc_wolfx": CencEarthquakeWolfxParser,
        }.get(source_id)
        if parser_class is None:
            return None
        return parser_class(*args, **kwargs)

    if entry.parser_name == "taiwan_eew_parser":
        parser_class = {
            "cwa_fanstudio": CwaEewParser,
            "cwa_wolfx": CwaEewWolfxParser,
        }.get(source_id)
        if parser_class is None:
            return None
        return parser_class(*args, **kwargs)

    parser_class = resolve_parser_class(entry.parser_name)
    if parser_class is None:
        return None
    return parser_class(*args, **kwargs)


def validate_catalog_parser_names() -> None:
    """校验数据源目录中引用的解析器名称都能被解析。"""
    missing_names = {
        entry.parser_name
        for entry in SOURCE_CATALOG.values()
        if entry.parser_name not in PARSER_CLASS_BY_NAME
    }
    if missing_names:
        missing_text = ", ".join(sorted(missing_names))
        raise RuntimeError(
            f"未注册的 parser_name: {missing_text}；请检查 source_catalog 与 parser_registry 的一致性"
        )
