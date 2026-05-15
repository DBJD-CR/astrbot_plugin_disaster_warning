"""
气象地区解析服务。
负责从标题、头条和外部行政区划接口中推断气象预警所属省份。
"""

from __future__ import annotations

import re
import time

import aiohttp

from astrbot.api import logger

CHINA_PROVINCES = [
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "台湾",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
]


class WeatherRegionResolver:
    """气象预警地区解析器。

    负责综合标题文本、本地规则与外部区划查询结果来确定省份归属。
    """

    def __init__(self):
        self._location_province_cache: dict[str, str | None] = {}
        self._cache_expire: dict[str, float] = {}
        self._failure_ttl = 60.0
        self._session: aiohttp.ClientSession | None = None

    def extract_province(self, title_text: str) -> str | None:
        """直接从标题中提取省级行政区名称。"""
        for province in CHINA_PROVINCES:
            if province in title_text:
                return province
        return None

    def _normalize_province_name(self, province_name: str) -> str | None:
        """把外部接口返回的省名归一化为标准名称。"""
        normalized = province_name.strip()
        if not normalized:
            return None
        for province in CHINA_PROVINCES:
            if province in normalized:
                return province
        return None

    def _extract_place_from_headline(self, headline_text: str) -> str | None:
        """从头条文本中尽量提取市县级地名。"""
        if not headline_text:
            return None
        matches = re.findall(
            r"([\u4e00-\u9fa5]{2,30}(?:特别行政区|自治州|自治县|自治旗|地区|盟|市|区|县|旗))",
            headline_text,
        )
        for place in matches:
            if "气象台" in place:
                continue
            return place

        fallback_text = re.split(r"气象(?:站|台)", headline_text, maxsplit=1)[0].strip()
        if fallback_text:
            fallback_text = re.sub(r"^[^\u4e00-\u9fa5]+", "", fallback_text)
            fallback_text = re.sub(r"[^\u4e00-\u9fa5]+$", "", fallback_text)
            if fallback_text:
                return fallback_text
        return None

    def _get_session(self) -> aiohttp.ClientSession:
        """获取内部复用的网络会话。"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"})
        return self._session

    async def close(self) -> None:
        """关闭内部网络会话。"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _query_province_by_place_name(self, place_name: str) -> str | None:
        """通过行政区划接口按地名反查所属省份。"""
        now = time.monotonic()
        # 成功结果直接缓存，失败结果短时缓存，减少重复网络查询。
        if place_name in self._location_province_cache:
            cached = self._location_province_cache[place_name]
            if cached is not None:
                return cached
            if now < self._cache_expire.get(place_name, 0):
                return None

        params = {
            "stName": place_name,
            "searchType": "模糊",
            "page": "1",
            "size": "10",
        }
        url = "https://dmfw.mca.gov.cn/9095/stname/listPub"
        try:
            session = self._get_session()
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                payload = await resp.json(content_type=None)
        except Exception as exc:
            logger.debug(
                f"[灾害预警] 行政区划查询失败，地点为 {place_name}，错误为 {exc}"
            )
            self._location_province_cache[place_name] = None
            self._cache_expire[place_name] = now + self._failure_ttl
            return None

        for record in payload.get("records", []):
            province_name = record.get("province_name", "")
            province = self._normalize_province_name(province_name)
            if province:
                self._location_province_cache[place_name] = province
                return province

        self._location_province_cache[place_name] = None
        self._cache_expire[place_name] = now + self._failure_ttl
        return None

    async def extract_province_with_fallback(
        self, title_text: str, headline_text: str = ""
    ) -> str | None:
        """按“标题直取 -> 头条提取 -> 外部查询”顺序解析省份。"""
        province = self.extract_province(title_text)
        if province is not None:
            return province
        place_name = self._extract_place_from_headline(headline_text)
        if not place_name:
            return None
        return await self._query_province_by_place_name(place_name)
