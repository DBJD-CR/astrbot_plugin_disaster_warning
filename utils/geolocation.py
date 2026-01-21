"""
IP地理定位工具
通过 Wolfx API 获取 IP 地址的地理位置信息
"""

import aiohttp
from astrbot.api import logger


_geoip_session: aiohttp.ClientSession | None = None


async def get_geoip_session() -> aiohttp.ClientSession:
    """
    获取用于 GeoIP 查询的共享 aiohttp.ClientSession 实例。
    如果尚未创建或已关闭，则会创建一个新的会话。
    """
    global _geoip_session
    if _geoip_session is None or _geoip_session.closed:
        _geoip_session = aiohttp.ClientSession()
    return _geoip_session


async def close_geoip_session() -> None:
    """
    关闭用于 GeoIP 查询的共享 aiohttp.ClientSession 实例。
    应在应用关闭时被调用，以避免资源泄漏。
    """
    global _geoip_session
    if _geoip_session is not None and not _geoip_session.closed:
        await _geoip_session.close()
    _geoip_session = None


async def fetch_location_from_ip(ip: str = None, session: aiohttp.ClientSession = None) -> dict:
    """
    通过 IP 地址获取地理位置信息
    
    :param ip: IP 地址，如果为 None 则自动使用请求者的 IP
    :param session: 可选的 aiohttp.ClientSession 实例；如果为 None，则使用模块级共享会话以复用连接
    :return: 包含经纬度和地址信息的字典
    :raises: Exception 如果请求失败
    """
    api_url = "https://api.wolfx.jp/geoip.php"
    params = {}
    if ip:
        params['ip'] = ip
    
    # 如果外部未提供 session，则使用模块级共享 session 以避免每次请求都新建连接
    if session is None:
        session = await get_geoip_session()
    
    try:
        async with session.get(api_url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as response:
            if response.status != 200:
                error_msg = f"GeoIP API 返回错误状态码: {response.status}"
                logger.error(f"[灾害预警] {error_msg}")
                raise Exception(error_msg)
            
            data = await response.json()
            
            # 提取需要的字段
            result = {
                "ip": data.get("ip", ""),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "country_name_zh": data.get("country_name_zh", ""),
                "province_name_zh": data.get("province_name_zh", ""),
                "city_zh": data.get("city_zh", ""),
            }
            
            # 验证经纬度是否有效
            if result["latitude"] is None or result["longitude"] is None:
                error_msg = "API 返回的数据中缺少经纬度信息"
                logger.warning(f"[灾害预警] {error_msg}")
                raise Exception(error_msg)
            
            logger.info(
                f"[灾害预警] 成功获取位置: {result['province_name_zh']} {result['city_zh']} "
                f"({result['latitude']}, {result['longitude']})"
            )
            
            return result
            
    except aiohttp.ClientError as e:
        error_msg = f"网络请求失败: {str(e)}"
        logger.error(f"[灾害预警] {error_msg}")
        raise Exception(error_msg)
    except Exception as e:
        logger.error(f"[灾害预警] 获取位置信息失败: {str(e)}")
        raise
