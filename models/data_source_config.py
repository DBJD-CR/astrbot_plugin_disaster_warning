"""
根据数据源配置和分类管理
重新定义数据源分类和处理架构
"""

from dataclasses import dataclass
from enum import Enum


class DataSourceType(Enum):
    """数据源类型分类"""

    EEW_WARNING = "eew_warning"  # 紧急地震预警
    EARTHQUAKE_INFO = "earthquake_info"  # 地震情报
    TSUNAMI = "tsunami"  # 海啸预警
    WEATHER = "weather"  # 气象预警


class EEWDataSource(Enum):
    """EEW预警数据源"""

    # 中国地震预警网
    CEA_FANSTUDIO = "cea_fanstudio"
    CEA_WOLFX = "cea_wolfx"

    # 台湾中央气象署
    CWA_FANSTUDIO = "cwa_fanstudio"
    CWA_WOLFX = "cwa_wolfx"

    # 日本气象厅紧急地震速报
    JMA_P2P = "jma_p2p"
    JMA_WOLFX = "jma_wolfx"

    # Global Quake
    GLOBAL_QUAKE = "global_quake"


class EarthquakeInfoSource(Enum):
    """地震情报数据源"""

    # 中国地震台网
    CENC_FANSTUDIO = "cenc_fanstudio"
    CENC_WOLFX = "cenc_wolfx"

    # 日本气象厅地震情报
    JMA_P2P_INFO = "jma_p2p_info"
    JMA_WOLFX_INFO = "jma_wolfx_info"

    # 美国地质调查局
    USGS_FANSTUDIO = "usgs_fanstudio"


class TsunamiSource(Enum):
    """海啸预警数据源"""

    # 中国自然资源部海啸预警中心
    CHINA_TSUNAMI_FANSTUDIO = "china_tsunami_fanstudio"

    # 日本气象厅海啸预报
    JMA_TSUNAMI_P2P = "jma_tsunami_p2p"


class WeatherSource(Enum):
    """气象预警数据源"""

    # 中国气象局
    CHINA_WEATHER_FANSTUDIO = "china_weather_fanstudio"


@dataclass
class DataSourceConfig:
    """数据源配置"""

    source_id: str
    source_type: DataSourceType
    display_name: str
    description: str
    supports_report_count: bool  # 是否支持报数控制
    supports_final_report: bool  # 是否支持最终报
    uses_intensity: bool  # 是否使用烈度
    uses_scale: bool  # 是否使用震度
    priority: int  # 优先级（用于多数据源推送顺序）


# 数据源配置映射
DATA_SOURCE_CONFIGS: dict[str, DataSourceConfig] = {
    # EEW预警数据源
    EEWDataSource.CEA_FANSTUDIO.value: DataSourceConfig(
        source_id=EEWDataSource.CEA_FANSTUDIO.value,
        source_type=DataSourceType.EEW_WARNING,
        display_name="中国地震预警网",
        description="中国地震预警网（CEA）- FAN Studio WebSocket",
        supports_report_count=True,
        supports_final_report=True,
        uses_intensity=True,
        uses_scale=False,
        priority=1,
    ),
    EEWDataSource.CEA_WOLFX.value: DataSourceConfig(
        source_id=EEWDataSource.CEA_WOLFX.value,
        source_type=DataSourceType.EEW_WARNING,
        display_name="中国地震预警网",
        description="中国地震预警网（CEA）- Wolfx API",
        supports_report_count=True,
        supports_final_report=True,
        uses_intensity=True,
        uses_scale=False,
        priority=2,
    ),
    EEWDataSource.CWA_FANSTUDIO.value: DataSourceConfig(
        source_id=EEWDataSource.CWA_FANSTUDIO.value,
        source_type=DataSourceType.EEW_WARNING,
        display_name="台湾中央气象署",
        description="台湾中央气象署地震预警（CWA）- FAN Studio WebSocket",
        supports_report_count=True,
        supports_final_report=True,
        uses_intensity=False,
        uses_scale=True,
        priority=1,
    ),
    EEWDataSource.CWA_WOLFX.value: DataSourceConfig(
        source_id=EEWDataSource.CWA_WOLFX.value,
        source_type=DataSourceType.EEW_WARNING,
        display_name="台湾中央气象署",
        description="台湾中央气象署地震预警（CWA）- Wolfx API",
        supports_report_count=True,
        supports_final_report=True,
        uses_intensity=False,
        uses_scale=True,
        priority=2,
    ),
    EEWDataSource.JMA_P2P.value: DataSourceConfig(
        source_id=EEWDataSource.JMA_P2P.value,
        source_type=DataSourceType.EEW_WARNING,
        display_name="日本气象厅",
        description="日本气象厅：紧急地震速报 - P2P地震情报 WebSocket",
        supports_report_count=True,
        supports_final_report=True,
        uses_intensity=False,
        uses_scale=True,
        priority=1,
    ),
    EEWDataSource.JMA_WOLFX.value: DataSourceConfig(
        source_id=EEWDataSource.JMA_WOLFX.value,
        source_type=DataSourceType.EEW_WARNING,
        display_name="日本气象厅",
        description="日本气象厅：紧急地震速报 - Wolfx API",
        supports_report_count=True,
        supports_final_report=True,
        uses_intensity=False,
        uses_scale=True,
        priority=2,
    ),
    EEWDataSource.GLOBAL_QUAKE.value: DataSourceConfig(
        source_id=EEWDataSource.GLOBAL_QUAKE.value,
        source_type=DataSourceType.EEW_WARNING,
        display_name="Global Quake",
        description="Global Quake 服务器推送 - 自定义TCP连接",
        supports_report_count=True,
        supports_final_report=False,  # 没有明确的最终报标识
        uses_intensity=True,
        uses_scale=False,
        priority=3,
    ),
    # 地震情报数据源
    EarthquakeInfoSource.CENC_FANSTUDIO.value: DataSourceConfig(
        source_id=EarthquakeInfoSource.CENC_FANSTUDIO.value,
        source_type=DataSourceType.EARTHQUAKE_INFO,
        display_name="中国地震台网",
        description="中国地震台网（CENC）：地震测定 - FAN Studio WebSocket",
        supports_report_count=False,  # 最多自动+正式两次
        supports_final_report=False,
        uses_intensity=True,
        uses_scale=False,
        priority=1,
    ),
    EarthquakeInfoSource.CENC_WOLFX.value: DataSourceConfig(
        source_id=EarthquakeInfoSource.CENC_WOLFX.value,
        source_type=DataSourceType.EARTHQUAKE_INFO,
        display_name="中国地震台网",
        description="中国地震台网（CENC）：地震测定 - Wolfx API",
        supports_report_count=False,
        supports_final_report=False,
        uses_intensity=True,
        uses_scale=False,
        priority=2,
    ),
    EarthquakeInfoSource.JMA_P2P_INFO.value: DataSourceConfig(
        source_id=EarthquakeInfoSource.JMA_P2P_INFO.value,
        source_type=DataSourceType.EARTHQUAKE_INFO,
        display_name="日本气象厅",
        description="日本气象厅（JMA）：地震情报 - P2P地震情报 WebSocket",
        supports_report_count=False,  # 最多三次：震度速报、震源相关、震源・震度
        supports_final_report=False,
        uses_intensity=False,
        uses_scale=True,
        priority=1,
    ),
    EarthquakeInfoSource.JMA_WOLFX_INFO.value: DataSourceConfig(
        source_id=EarthquakeInfoSource.JMA_WOLFX_INFO.value,
        source_type=DataSourceType.EARTHQUAKE_INFO,
        display_name="日本气象厅",
        description="日本气象厅（JMA）：地震情报 - Wolfx API",
        supports_report_count=False,
        supports_final_report=False,
        uses_intensity=False,
        uses_scale=True,
        priority=2,
    ),
    EarthquakeInfoSource.USGS_FANSTUDIO.value: DataSourceConfig(
        source_id=EarthquakeInfoSource.USGS_FANSTUDIO.value,
        source_type=DataSourceType.EARTHQUAKE_INFO,
        display_name="美国地质调查局",
        description="美国地质调查局（USGS）：地震测定 - FAN Studio WebSocket",
        supports_report_count=False,
        supports_final_report=False,
        uses_intensity=False,  # USGS数据不包含烈度
        uses_scale=False,
        priority=1,
    ),
    # 海啸预警数据源
    TsunamiSource.CHINA_TSUNAMI_FANSTUDIO.value: DataSourceConfig(
        source_id=TsunamiSource.CHINA_TSUNAMI_FANSTUDIO.value,
        source_type=DataSourceType.TSUNAMI,
        display_name="中国海啸预警中心",
        description="自然资源部海啸预警中心海啸预警信息 - FAN Studio WebSocket",
        supports_report_count=False,
        supports_final_report=False,
        uses_intensity=False,
        uses_scale=False,
        priority=1,
    ),
    TsunamiSource.JMA_TSUNAMI_P2P.value: DataSourceConfig(
        source_id=TsunamiSource.JMA_TSUNAMI_P2P.value,
        source_type=DataSourceType.TSUNAMI,
        display_name="日本气象厅",
        description="日本气象厅：津波予報 - P2P地震情報 WebSocket",
        supports_report_count=False,
        supports_final_report=False,
        uses_intensity=False,
        uses_scale=False,
        priority=1,
    ),
    # 气象预警数据源
    WeatherSource.CHINA_WEATHER_FANSTUDIO.value: DataSourceConfig(
        source_id=WeatherSource.CHINA_WEATHER_FANSTUDIO.value,
        source_type=DataSourceType.WEATHER,
        display_name="中国气象局",
        description="中国气象局气象预警 - FAN Studio WebSocket",
        supports_report_count=False,
        supports_final_report=False,
        uses_intensity=False,
        uses_scale=False,
        priority=1,
    ),
}


def get_data_source_config(source_id: str) -> DataSourceConfig | None:
    """获取数据源配置"""
    return DATA_SOURCE_CONFIGS.get(source_id)


def get_eew_sources() -> list[str]:
    """获取所有EEW预警数据源"""
    return [source.value for source in EEWDataSource]


def get_earthquake_info_sources() -> list[str]:
    """获取所有地震情报数据源"""
    return [source.value for source in EarthquakeInfoSource]


def get_tsunami_sources() -> list[str]:
    """获取所有海啸预警数据源"""
    return [source.value for source in TsunamiSource]


def get_weather_sources() -> list[str]:
    """获取所有气象预警数据源"""
    return [source.value for source in WeatherSource]


def get_sources_by_type(source_type: DataSourceType) -> list[str]:
    """按类型获取数据源"""
    return [
        config.source_id
        for config in DATA_SOURCE_CONFIGS.values()
        if config.source_type == source_type
    ]


def get_sources_needing_report_control() -> list[str]:
    """获取需要报数控制的数据源"""
    return [
        config.source_id
        for config in DATA_SOURCE_CONFIGS.values()
        if config.supports_report_count
    ]


def get_sources_needing_final_report() -> list[str]:
    """获取支持最终报的数据源"""
    return [
        config.source_id
        for config in DATA_SOURCE_CONFIGS.values()
        if config.supports_final_report
    ]


def get_intensity_based_sources() -> list[str]:
    """获取基于烈度的数据源"""
    return [
        config.source_id
        for config in DATA_SOURCE_CONFIGS.values()
        if config.uses_intensity
    ]


def get_scale_based_sources() -> list[str]:
    """获取基于震度的数据源"""
    return [
        config.source_id for config in DATA_SOURCE_CONFIGS.values() if config.uses_scale
    ]
