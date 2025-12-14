"""
灾害预警数据模型
适配数据源架构
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from astrbot.api import logger


class DisasterType(Enum):
    """灾害类型"""

    EARTHQUAKE = "earthquake"
    EARTHQUAKE_WARNING = "earthquake_warning"
    TSUNAMI = "tsunami"
    WEATHER_ALARM = "weather_alarm"


class DataSource(Enum):
    """数据源类型 - 适配架构"""

    # FAN Studio 数据源
    FAN_STUDIO_CENC = "fan_studio_cenc"  # 中国地震台网
    FAN_STUDIO_CEA = "fan_studio_cea"  # 中国地震预警网
    FAN_STUDIO_CWA = "fan_studio_cwa"  # 台湾中央气象署
    FAN_STUDIO_USGS = "fan_studio_usgs"  # USGS
    FAN_STUDIO_WEATHER = "fan_studio_weather"  # 中国气象局气象预警
    FAN_STUDIO_TSUNAMI = "fan_studio_tsunami"  # 海啸预警

    # P2P 数据源
    P2P_EEW = "p2p_eew"  # P2P地震情報緊急地震速報
    P2P_EARTHQUAKE = "p2p_earthquake"  # P2P地震情報
    P2P_TSUNAMI = "p2p_tsunami"  # P2P海啸预报

    # Wolfx 数据源
    WOLFX_JMA_EEW = "wolfx_jma_eew"  # Wolfx日本气象厅紧急地震速报
    WOLFX_CENC_EEW = "wolfx_cenc_eew"  # Wolfx中国地震台网预警
    WOLFX_CWA_EEW = "wolfx_cwa_eew"  # Wolfx台湾地震预警
    WOLFX_CENC_EQ = "wolfx_cenc_eq"  # Wolfx中国地震台网地震测定
    WOLFX_JMA_EQ = "wolfx_jma_eq"  # Wolfx日本气象厅地震情报

    # Global Quake 数据源
    GLOBAL_QUAKE = "global_quake"  # Global Quake服务器


# 数据源ID映射
DATA_SOURCE_MAPPING = {
    # EEW预警数据源
    "cea_fanstudio": DataSource.FAN_STUDIO_CEA,
    "cea_wolfx": DataSource.WOLFX_CENC_EEW,
    "cwa_fanstudio": DataSource.FAN_STUDIO_CWA,
    "cwa_wolfx": DataSource.WOLFX_CWA_EEW,
    "jma_p2p": DataSource.P2P_EEW,
    "jma_wolfx": DataSource.WOLFX_JMA_EEW,
    "global_quake": DataSource.GLOBAL_QUAKE,
    # 地震情报数据源
    "cenc_fanstudio": DataSource.FAN_STUDIO_CENC,
    "cenc_wolfx": DataSource.WOLFX_CENC_EQ,
    "jma_p2p_info": DataSource.P2P_EARTHQUAKE,
    "jma_wolfx_info": DataSource.WOLFX_JMA_EQ,
    "usgs_fanstudio": DataSource.FAN_STUDIO_USGS,
    # 其他数据源
    "china_weather_fanstudio": DataSource.FAN_STUDIO_WEATHER,
    "china_tsunami_fanstudio": DataSource.FAN_STUDIO_TSUNAMI,
    "jma_tsunami_p2p": DataSource.P2P_TSUNAMI,
}


def get_data_source_from_id(new_id: str) -> DataSource | None:
    """从数据源ID获取DataSource枚举值"""
    return DATA_SOURCE_MAPPING.get(new_id)


@dataclass
class EarthquakeData:
    """地震数据 - 增强版本"""

    id: str
    event_id: str
    source: DataSource
    disaster_type: DisasterType

    # 基本信息
    shock_time: datetime
    latitude: float
    longitude: float

    # 位置信息
    place_name: str

    # 有默认值的字段（必须放在后面）
    depth: float | None = None
    magnitude: float | None = None

    # 烈度/震度信息
    intensity: float | None = None  # 中国烈度
    scale: float | None = None  # 日本震度
    max_intensity: float | None = None  # 最大烈度/震度
    max_scale: float | None = None  # P2P数据源的最大震度值

    # 位置信息
    province: str | None = None

    # 更新信息
    updates: int = 1
    is_final: bool = False
    is_cancel: bool = False

    # 其他信息
    info_type: str = ""  # 测定类型：自动/正式等
    domestic_tsunami: str | None = None
    foreign_tsunami: str | None = None

    # 时间信息（用于不同数据源）
    update_time: datetime | None = None  # 更新时间（USGS等数据源）
    create_time: datetime | None = None  # 创建时间（CWA等数据源）

    # 新增字段 - 适配架构
    source_id: str = ""  # 数据源ID，如"cea_fanstudio"
    report_num: int | None = None  # 报数（某些数据源使用）
    serial: str | None = None  # 序列号（P2P数据源）
    is_training: bool = False  # 是否为训练模式
    revision: int | None = None  # 修订版本（Global Quake等）

    # 原始数据
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.shock_time, str):
            self.shock_time = datetime.fromisoformat(
                self.shock_time.replace("Z", "+00:00")
            )

        # 如果提供了新的source_id，自动映射到DataSource枚举
        if self.source_id and not isinstance(self.source, DataSource):
            mapped_source = get_data_source_from_id(self.source_id)
            if mapped_source:
                self.source = mapped_source


@dataclass
class TsunamiData:
    """海啸数据 - 增强版本"""

    id: str
    code: str
    source: DataSource
    title: str
    level: str  # 黄色、橙色、红色、解除

    # 默认值的字段（必须放在后面）
    disaster_type: DisasterType = DisasterType.TSUNAMI
    subtitle: str | None = None
    org_unit: str = ""

    # 时间信息
    issue_time: datetime | None = None

    # 预报区域
    forecasts: list[dict[str, Any]] = field(default_factory=list)

    # 监测站信息
    monitoring_stations: list[dict[str, Any]] = field(default_factory=list)

    # 新增字段
    source_id: str = ""  # 数据源ID
    estimated_arrival_time: str | None = None  # 预计到达时间
    max_wave_height: str | None = None  # 最大波高

    # 原始数据
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class WeatherAlarmData:
    """气象预警数据 - 增强版本"""

    id: str
    source: DataSource
    headline: str
    title: str
    description: str
    type: str  # 预警类型编码
    effective_time: datetime

    # 默认值的字段
    disaster_type: DisasterType = DisasterType.WEATHER_ALARM
    issue_time: datetime | None = None
    longitude: float | None = None
    latitude: float | None = None

    # 新增字段
    source_id: str = ""  # 数据源ID
    alert_level: str | None = None  # 警报级别
    affected_areas: list[str] = field(default_factory=list)  # 受影响区域

    # 原始数据
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class DisasterEvent:
    """统一灾害事件格式 - 增强版本"""

    id: str
    data: Any  # EarthquakeData, TsunamiData, WeatherAlarmData
    source: DataSource
    disaster_type: DisasterType
    receive_time: datetime = field(default_factory=datetime.now)

    # 新增字段
    source_id: str = ""  # 数据源ID
    processing_time: datetime | None = None  # 处理时间
    is_filtered: bool = False  # 是否被过滤
    filter_reason: str = ""  # 过滤原因
    push_count: int = 0  # 推送次数
    
    # 原始数据
    raw_data: dict[str, Any] = field(default_factory=dict)


# 辅助函数
def create_earthquake_data(
    source_id: str, event_data: dict[str, Any], **kwargs
) -> EarthquakeData:
    """创建地震数据的便捷函数"""

    # 获取数据源枚举
    data_source = get_data_source_from_id(source_id)
    if not data_source:
        raise ValueError(f"未知的数据源ID: {source_id}")

    # 确定灾害类型
    if "eew" in source_id or source_id in ["jma_p2p", "jma_wolfx", "global_quake"]:
        disaster_type = DisasterType.EARTHQUAKE_WARNING
    else:
        disaster_type = DisasterType.EARTHQUAKE

    # 创建基础数据
    earthquake_data = EarthquakeData(
        id=event_data.get("id", ""),
        event_id=event_data.get("event_id", event_data.get("id", "")),
        source=data_source,
        disaster_type=disaster_type,
        shock_time=kwargs.get("shock_time", datetime.now()),
        latitude=kwargs.get("latitude", 0.0),
        longitude=kwargs.get("longitude", 0.0),
        place_name=kwargs.get("place_name", ""),
        source_id=source_id,
        **kwargs,
    )

    return earthquake_data


def validate_earthquake_data(earthquake: EarthquakeData) -> bool:
    """验证地震数据的有效性"""

    # 检查必需字段
    if not earthquake.id or not earthquake.event_id:
        return False

    if earthquake.latitude is None or earthquake.longitude is None:
        return False

    if not earthquake.place_name:
        return False

    # 检查数值范围
    if earthquake.magnitude is not None:
        if earthquake.magnitude < 0 or earthquake.magnitude > 10:
            return False

    if earthquake.depth is not None:
        if earthquake.depth < 0 or earthquake.depth > 800:
            return False

    if earthquake.intensity is not None:
        if earthquake.intensity < 1 or earthquake.intensity > 12:
            return False

    if earthquake.scale is not None:
        if earthquake.scale < 0 or earthquake.scale > 7:
            return False

    return True


# 向后兼容的函数
def convert_old_model(old_model) -> DisasterEvent | None:
    """将旧模型转换"""
    try:
        if hasattr(old_model, "source") and isinstance(old_model.source, Enum):
            # 已经是新的模型格式
            return old_model

        # 转换逻辑（根据实际需求实现）
        # 这里需要根据具体的旧模型结构来实现转换
        return None

    except Exception as e:
        logger.error(f"模型转换失败: {e}")
        return None
