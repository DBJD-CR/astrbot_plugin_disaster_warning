"""
气象预警过滤器
支持按关键词白名单和颜色级别过滤气象预警
"""

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from astrbot.api import logger

from ...models.models import CHINA_PROVINCES

# 颜色级别映射
COLOR_LEVELS = {
    "白色": 0,
    "蓝色": 1,
    "黄色": 2,
    "橙色": 3,
    "红色": 4,
}


class WeatherFilter:
    """气象预警过滤器"""

    def __init__(self, config: dict[str, Any], emit_enable_log: bool = True):
        self.enabled = config.get("enabled", False)
        self.min_color_level = config.get("min_color_level", "白色")
        self.min_level_value = COLOR_LEVELS.get(self.min_color_level, 0)

        # 关键词白名单：优先读取 keywords，兼容旧配置 provinces
        raw_keywords = config.get("keywords")
        if not isinstance(raw_keywords, list):
            raw_keywords = config.get("provinces", [])
        self.keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]

        self._location_province_cache: dict[str, str | None] = {}

        if self.enabled and emit_enable_log:
            filter_info = []
            if self.keywords:
                filter_info.append(f"关键词白名单: {', '.join(self.keywords)}")
            filter_info.append(f"最低级别: {self.min_color_level}")
            logger.info(f"[灾害预警] 气象预警过滤器已启用，{', '.join(filter_info)}")

    def extract_province(self, title_text: str) -> str | None:
        """从预警标题文本中提取省份名称"""
        for province in CHINA_PROVINCES:
            if province in title_text:
                return province
        return None

    def _normalize_province_name(self, province_name: str) -> str | None:
        """将API返回省份名称归一为项目内省份简称"""
        normalized = province_name.strip()
        if not normalized:
            return None
        for province in CHINA_PROVINCES:
            if province in normalized:
                return province
        return None

    def _extract_place_from_headline(self, headline_text: str) -> str | None:
        """从副标题中提取地名关键词"""
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

        # 兜底：未匹配到标准行政区后缀时，截取“气象站/气象台”前文本用于API模糊搜索
        fallback_text = re.split(r"气象(?:站|台)", headline_text, maxsplit=1)[0].strip()
        if fallback_text:
            fallback_text = re.sub(r"^[^\u4e00-\u9fa5]+", "", fallback_text)
            fallback_text = re.sub(r"[^\u4e00-\u9fa5]+$", "", fallback_text)
            if fallback_text:
                return fallback_text
        return None

    def _query_province_by_place_name(self, place_name: str) -> str | None:
        """通过行政区划查询API获取省份"""
        if place_name in self._location_province_cache:
            return self._location_province_cache[place_name]

        params = urlencode(
            {
                "stName": place_name,
                "searchType": "模糊",
                "page": "1",
                "size": "10",
            }
        )
        request = Request(
            f"https://dmfw.mca.gov.cn/9095/stname/listPub?{params}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        try:
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            logger.debug(f"[灾害预警] 行政区划查询失败: {place_name}, 错误: {exc}")
            return None

        for record in payload.get("records", []):
            province_name = record.get("province_name", "")
            province = self._normalize_province_name(province_name)
            if province:
                self._location_province_cache[place_name] = province
                return province

        self._location_province_cache[place_name] = None
        return None

    def extract_province_with_fallback(
        self, title_text: str, headline_text: str = ""
    ) -> str | None:
        """优先从title提取省份，失败后回退到headline地名查询"""
        province = self.extract_province(title_text)
        if province is not None:
            return province
        place_name = self._extract_place_from_headline(headline_text)
        if not place_name:
            return None
        return self._query_province_by_place_name(place_name)

    def extract_color_level(self, title_text: str) -> str:
        """从预警标题文本中提取颜色级别"""
        # 预处理：去除无效上下文中的颜色引用
        # 1. 去除括号内的内容 (通常是 "原...已失效" 等)
        # 兼容全角和半角括号
        cleaned = re.sub(r"[（\(].*?[）\)]", "", title_text)

        # 2. 去除 "解除...预警" (通常是 "解除...预警，发布..." 或单纯解除)
        # 这里的非贪婪匹配 .*? 会匹配到最近的 "预警"
        cleaned = re.sub(r"解除[^，。,]*?预警", "", cleaned)

        # 3. 去除 "将...预警" (通常是 "将...预警降级为...")
        cleaned = re.sub(r"将[^，。,]*?预警", "", cleaned)

        # 4. 去除 "原...预警" (如果没有被括号包裹)
        cleaned = re.sub(r"原[^，。,]*?预警", "", cleaned)

        if cleaned != title_text:
            logger.debug(f"[灾害预警] 标题清洗: '{title_text}' -> '{cleaned}'")

        # 匹配颜色 - 优先匹配剩下的文本
        for color in ["红色", "橙色", "黄色", "蓝色", "白色"]:
            if color in cleaned:
                return color

        # 如果清洗后没有颜色了（比如只有“解除暴雨红色预警”），
        # 则说明这可能是一条解除通知，或者不包含有效的新增预警级别。
        # 这种情况下返回“白色”作为最低级别，通常会被过滤器拦截（除非用户设置阈值为白色）。
        return "白色"

    def should_filter(self, title_text: str, headline_text: str = "") -> bool:
        """
        判断是否应过滤该预警
        返回 True 表示应过滤（不推送），False 表示不过滤（推送）
        """
        if not self.enabled:
            return False

        # 1. 级别过滤
        current_color = self.extract_color_level(title_text)
        current_level_value = COLOR_LEVELS.get(current_color, 0)

        if current_level_value < self.min_level_value:
            logger.info(
                f"[灾害预警] 气象预警被级别过滤器过滤: {current_color} 低于最低要求 {self.min_color_level}"
            )
            return True

        # 2. 关键词白名单过滤（title 优先，title 未命中再检查 headline）
        if self.keywords:
            title_hit = any(
                keyword in title_text for keyword in self.keywords if keyword
            )
            if not title_hit:
                headline_hit = any(
                    keyword in headline_text for keyword in self.keywords if keyword
                )
                if not headline_hit:
                    logger.info("[灾害预警] 气象预警被关键词过滤器过滤")
                    return True

        return False
