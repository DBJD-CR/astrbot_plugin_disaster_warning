"""
数据处理器模块
提供所有数据源的统一入口

新模块已完全替代 data_handlers.py
"""

from .base import BaseDataHandler, _safe_float_convert
from .china_eew import CEAEEWHandler, CEAEEWWolfxHandler
from .china_earthquake import CENCEarthquakeHandler, CENCEarthquakeWolfxHandler
from .taiwan_eew import CWAEEWHandler, CWAEEWWolfxHandler
from .japan_eew import JMAEEWFanStudioHandler, JMAEEWP2PHandler, JMAEEWWolfxHandler
from .japan_earthquake import JMAEarthquakeP2PHandler, JMAEarthquakeWolfxHandler
from .global_sources import USGSEarthquakeHandler, GlobalQuakeHandler
from .weather import WeatherAlarmHandler
from .tsunami import TsunamiHandler, JMATsunamiP2PHandler

# Handler 注册表 - 映射 source_id 到对应的 Handler 类
DATA_HANDLERS = {
    # EEW 预警数据源
    "cea_fanstudio": CEAEEWHandler,
    "cea_wolfx": CEAEEWWolfxHandler,
    "cwa_fanstudio": CWAEEWHandler,
    "cwa_wolfx": CWAEEWWolfxHandler,
    "jma_fanstudio": JMAEEWFanStudioHandler,
    "jma_p2p": JMAEEWP2PHandler,
    "jma_wolfx": JMAEEWWolfxHandler,
    # 地震情报数据源
    "cenc_fanstudio": CENCEarthquakeHandler,
    "cenc_wolfx": CENCEarthquakeWolfxHandler,
    "jma_p2p_info": JMAEarthquakeP2PHandler,
    "jma_wolfx_info": JMAEarthquakeWolfxHandler,
    "usgs_fanstudio": USGSEarthquakeHandler,
    "global_quake": GlobalQuakeHandler,
    # 气象预警
    "china_weather_fanstudio": WeatherAlarmHandler,
    # 海啸预警
    "china_tsunami_fanstudio": TsunamiHandler,
    "jma_tsunami_p2p": JMATsunamiP2PHandler,
}

__all__ = [
    # 基类
    "BaseDataHandler",
    "_safe_float_convert",
    # 各种处理器
    "CEAEEWHandler",
    "CEAEEWWolfxHandler",
    "CENCEarthquakeHandler",
    "CENCEarthquakeWolfxHandler",
    "CWAEEWHandler",
    "CWAEEWWolfxHandler",
    "JMAEEWFanStudioHandler",
    "JMAEEWP2PHandler",
    "JMAEEWWolfxHandler",
    "JMAEarthquakeP2PHandler",
    "JMAEarthquakeWolfxHandler",
    "USGSEarthquakeHandler",
    "GlobalQuakeHandler",
    "WeatherAlarmHandler",
    "TsunamiHandler",
    "JMATsunamiP2PHandler",
    # 注册表
    "DATA_HANDLERS",
]
