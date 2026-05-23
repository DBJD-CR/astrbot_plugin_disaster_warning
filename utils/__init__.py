"""
插件辅助工具子包。
包含 IP 物理定位（GeoIP）、地图瓦片 URL 映射、时区转换格式化、版本识别探测以及烈度制式转换等基础通用库。
"""

from .converters import ScaleConverter
from .geolocation import close_geoip_session, fetch_location_from_ip, get_geoip_session
from .map_tile_sources import get_tile_url, get_tile_url_js, normalize_map_source
from .time_converter import TimeConverter
from .version import get_astrbot_version, get_astrbot_version_info, get_plugin_version

__all__ = [
    "ScaleConverter",
    "close_geoip_session",
    "fetch_location_from_ip",
    "get_geoip_session",
    "get_tile_url",
    "get_tile_url_js",
    "normalize_map_source",
    "TimeConverter",
    "get_astrbot_version",
    "get_astrbot_version_info",
    "get_plugin_version",
]
