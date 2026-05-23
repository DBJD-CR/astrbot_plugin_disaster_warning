"""
数据转换工具。
提供震度、烈度与数值转换等通用能力。
"""

import math
import re
from typing import Any


def safe_float_convert(value: Any) -> float | None:
    """安全地将输入值转换为浮点数。"""
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
    """震度与烈度转换工具类。"""

    # 罗马数字到阿拉伯数字的映射，用于兼容 Global Quake 等数据源的烈度表示。
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
        解析日本或台湾震度字符串。
        支持格式：'5-'、'5+'、'5弱'、'5強'、'5'、'6.5' 等。

        映射规则如下：
        X弱 / X- -> X - 0.5
        X強 / X+ -> X + 0.5
        X        -> X.0

        例如：
        5弱 -> 4.5
        5強 -> 5.5
        """
        if scale_str is None:
            return None

        # 若输入本身已经是数值，则直接返回。
        if isinstance(scale_str, (int, float)):
            return float(scale_str)

        scale_str = str(scale_str).strip()
        if not scale_str:
            return None

        # 支持 5+、5-、5弱、5強 等多种格式。
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
        将 P2P 震度值转换为标准震度。

        映射表：
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
            -1: None,  # 震度信息不存在
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

    @staticmethod
    def normalize_p2p_scale_value(value: Any) -> int | None:
        """把 P2P 震度业务值安全规整为整数。"""
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def format_p2p_scale_display(value: Any) -> str:
        """把 P2P 震度业务值转换为用户可读展示值。"""
        raw_value = ScaleConverter.normalize_p2p_scale_value(value)
        if raw_value is None:
            return ""
        if raw_value == 99:
            return "以上"
        converted = ScaleConverter.convert_p2p_scale(raw_value)
        if converted is not None:
            return ScaleConverter.format_jma_cwa_scale_display(converted)
        return ScaleConverter.format_jma_cwa_scale_display(raw_value)

    @staticmethod
    def format_p2p_scale_range(scale_from: Any, scale_to: Any) -> str:
        """格式化 P2P 预估震度范围。"""
        from_value = ScaleConverter.normalize_p2p_scale_value(scale_from)
        to_value = ScaleConverter.normalize_p2p_scale_value(scale_to)
        if from_value is None and to_value is None:
            return ""
        if from_value is None:
            return ScaleConverter.format_p2p_scale_display(to_value)
        if to_value is None or to_value == from_value:
            return ScaleConverter.format_p2p_scale_display(from_value)
        from_display = ScaleConverter.format_p2p_scale_display(from_value)
        to_display = ScaleConverter.format_p2p_scale_display(to_value)
        if not from_display:
            return to_display
        if not to_display:
            return from_display
        if to_value == 99:
            return f"{from_display}{to_display}"
        return f"{from_display} ～ {to_display}"

    @staticmethod
    def get_p2p_scale_emoji(scale_from: Any, scale_to: Any) -> str:
        """根据 P2P 震度业务值选择展示 emoji。"""
        candidates: list[float] = []
        for value in (scale_from, scale_to):
            raw_value = ScaleConverter.normalize_p2p_scale_value(value)
            if raw_value is None:
                continue
            converted = ScaleConverter.convert_p2p_scale(raw_value)
            if converted is not None:
                candidates.append(converted)
        if not candidates:
            return "⚪"
        max_scale = max(candidates)
        if max_scale >= 6.5:
            return "🟣"
        if max_scale >= 5.5:
            return "🔴"
        if max_scale >= 4.5:
            return "🟠"
        if max_scale >= 3.5:
            return "🟡"
        if max_scale >= 2.5:
            return "🟢"
        if max_scale >= 1.5:
            return "🔵"
        return "⚪"

    @staticmethod
    def format_jma_cwa_scale_display(scale_value: str | int | float | None) -> str:
        """
        将日本/台湾震度值转换为展示文本。

        支持输入：
        - 原始字符串: "5-", "5+", "5弱", "5強", "6弱"
        - 解析后的浮点值: 4.5, 5.0, 5.5, 6.0
        - P2P 原始整数: 45, 50, 55, 60, 70
        """
        if scale_value is None:
            return ""

        if isinstance(scale_value, str):
            scale_str = scale_value.strip()
            if not scale_str:
                return ""

            normalized = (
                scale_str.replace("強", "强").replace("＋", "+").replace("－", "-")
            )
            display_mapping = {
                "5-": "5弱",
                "5+": "5强",
                "6-": "6弱",
                "6+": "6强",
                "5弱": "5弱",
                "5强": "5强",
                "5強": "5强",
                "6弱": "6弱",
                "6强": "6强",
                "6強": "6强",
                "7": "7",
                "4": "4",
                "3": "3",
                "2": "2",
                "1": "1",
                "0": "0",
            }
            if normalized in display_mapping:
                return display_mapping[normalized]

            parsed = ScaleConverter.parse_jma_cwa_scale(normalized)
            if parsed is None:
                return scale_str
            scale_value = parsed

        if isinstance(scale_value, int) and scale_value in {
            10,
            20,
            30,
            40,
            45,
            46,
            50,
            55,
            60,
            70,
        }:
            if scale_value == 45 or scale_value == 46:
                return "5弱"
            if scale_value == 50:
                return "5强"
            if scale_value == 55:
                return "6弱"
            if scale_value == 60:
                return "6强"
            if scale_value == 70:
                return "7"
            return str(scale_value // 10)

        if isinstance(scale_value, (int, float)):
            num = float(scale_value)
            if math.isclose(num, 4.5, abs_tol=0.01):
                return "5弱"
            if math.isclose(num, 5.0, abs_tol=0.01):
                return "5强"
            if math.isclose(num, 5.5, abs_tol=0.01):
                return "6弱"
            if math.isclose(num, 6.0, abs_tol=0.01):
                return "6强"
            if math.isclose(num, round(num), abs_tol=0.01):
                return str(int(round(num)))
            return f"{num:.1f}".rstrip("0").rstrip(".")

        return str(scale_value)

    @classmethod
    def convert_roman_intensity(cls, intensity_str: str) -> float | None:
        """将罗马数字烈度转换为浮点数。"""
        if not intensity_str:
            return None

        if intensity_str in cls.ROMAN_TO_INT:
            return float(cls.ROMAN_TO_INT[intensity_str])

        return None
