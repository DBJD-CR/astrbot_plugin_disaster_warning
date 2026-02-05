"""
数据转换工具类
提供震度/烈度转换、数值转换等通用功能
"""

import re
from typing import Any


def safe_float_convert(value: Any) -> float | None:
    """
    安全地将值转换为浮点数
    :param value: 输入值 (int, float, str, None)
    :return: float 或 None
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except (ValueError, TypeError):
            return None
    return None


class ScaleConverter:
    """震度/烈度转换工具类"""

    # 罗马数字到阿拉伯数字的映射 (用于 Global Quake 等数据源)
    ROMAN_TO_INT = {
        "I": 1,
        "II": 2,
        "III": 3,
        "IV": 4,
        "V": 5,
        "VI": 6,
        "VII": 7,
        "VIII": 8,
        "IX": 9,
        "X": 10,
        "XI": 11,
        "XII": 12,
    }

    @staticmethod
    def parse_jma_cwa_scale(scale_str: str | int | float) -> float | None:
        """
        解析日本(JMA)或台湾(CWA)震度字符串
        支持格式: '5-', '5+', '5弱', '5強', '5', '6.5'(作为字符串)

        映射规则 (基于项目现有逻辑):
        X弱 / X- -> X - 0.5
        X強 / X+ -> X + 0.5
        X        -> X.0

        例如:
        5弱 -> 4.5
        5強 -> 5.5
        """
        if scale_str is None:
            return None

        # 如果已经是数字，直接返回
        if isinstance(scale_str, (int, float)):
            return float(scale_str)

        scale_str = str(scale_str).strip()
        if not scale_str:
            return None

        # 支持 5+, 5-, 5弱, 5強 等多种格式
        match = re.search(r"(\d+)(弱|強|\+|\-)?", scale_str)
        if match:
            base = int(match.group(1))
            suffix = match.group(2)

            if suffix in ["弱", "-"]:
                return base - 0.5
            elif suffix in ["強", "+"]:
                return base + 0.5
            else:
                return float(base)

        return None

    @staticmethod
    def convert_p2p_scale(p2p_scale: int) -> float | None:
        """
        将P2P震度值转换为标准震度

        映射表:
        10 -> 1.0
        20 -> 2.0
        30 -> 3.0
        40 -> 4.0
        45 -> 4.5 (5弱)
        46 -> 4.6 (5弱以上推测)
        50 -> 5.0 (5強)
        55 -> 5.5 (6弱)
        60 -> 6.0 (6強)
        70 -> 7.0 (7)
        """
        scale_mapping = {
            -1: None,  # 震度情報不存在
            0: 0.0,  # 震度0
            10: 1.0,  # 震度1
            20: 2.0,  # 震度2
            30: 3.0,  # 震度3
            40: 4.0,  # 震度4
            45: 4.5,  # 震度5弱
            46: 4.6,  # 震度5弱以上と推定されるが震度情報を入手していない
            50: 5.0,  # 震度5強
            55: 5.5,  # 震度6弱
            60: 6.0,  # 震度6強
            70: 7.0,  # 震度7
        }
        return scale_mapping.get(p2p_scale)

    @classmethod
    def convert_roman_intensity(cls, intensity_str: str) -> float | None:
        """
        将罗马数字烈度转换为浮点数
        :param intensity_str: 罗马数字字符串 (如 "IV", "V")
        :return: 对应的数值 (如 4.0, 5.0)
        """
        if not intensity_str:
            return None

        if intensity_str in cls.ROMAN_TO_INT:
            return float(cls.ROMAN_TO_INT[intensity_str])

        return None
