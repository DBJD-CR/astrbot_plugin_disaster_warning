"""台风编号格式转换与规范化。"""

from __future__ import annotations


def _clean_id(typhoon_id: object) -> str:
    return str(typhoon_id or "").strip()


def to_eqsc_id(typhoon_id: object) -> str:
    """将 4/6 位编号转换为 EQSC 4 位形式。"""
    text = _clean_id(typhoon_id)
    if not text:
        return ""
    if len(text) >= 4 and text.isdigit():
        return text[-4:]
    return text


def to_fan_id(typhoon_id: object) -> str:
    """将 4 位 EQSC 编号转换为 Fan 6 位形式。"""
    text = _clean_id(typhoon_id)
    if not text:
        return ""
    if len(text) == 4 and text.isdigit():
        return f"20{text}"
    return text


def normalize_typhoon_id(typhoon_id: object) -> str:
    """返回用于缓存、去重和跨来源匹配的稳定 4 位编号。"""
    raw = _clean_id(typhoon_id)
    if not raw:
        return ""
    digits = "".join(char for char in raw if char.isdigit())
    return digits[-4:] if len(digits) >= 4 else raw
