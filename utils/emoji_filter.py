"""推送文本 Emoji 过滤工具。

仅供预警推送链路使用：在文本消息构建完成后按配置模式过滤 emoji。
插件指令回复等其他场景不应调用本模块，以保持其原有展示风格。
"""

from __future__ import annotations

import re
from typing import Final

# 配置项可选值（与 _conf_schema.json 保持一致）
EMOJI_FILTER_MODE_DEFAULT: Final[str] = "默认"
EMOJI_FILTER_MODE_MINIMAL: Final[str] = "简洁"
EMOJI_FILTER_MODE_OFF: Final[str] = "关闭"

VALID_EMOJI_FILTER_MODES: Final[frozenset[str]] = frozenset(
    {
        EMOJI_FILTER_MODE_DEFAULT,
        EMOJI_FILTER_MODE_MINIMAL,
        EMOJI_FILTER_MODE_OFF,
    }
)

# 简洁模式白名单：烈度/震度方形/圆形指示器，以及气象/台风等严重性颜色指示图标。
# 与 earthquake_presenter / weather_constants / typhoon_display_format 中的指示器对齐。
SEVERITY_INDICATOR_EMOJIS: Final[frozenset[str]] = frozenset(
    {
        # 圆形颜色指示（EEW / 气象颜色 / 台风等级）
        "⚪",
        "⚫",
        "🔴",
        "🟠",
        "🟡",
        "🟢",
        "🔵",
        "🟣",
        "🟤",
        # 方形颜色指示（地震情报场景）
        "⬜",
        "⬛",
        "🟥",
        "🟧",
        "🟨",
        "🟩",
        "🟦",
        "🟪",
        "🟫",
    }
)

# 覆盖常见 emoji 序列：基础符号、补充符号、旗帜、肤色修饰、ZWJ 组合、变体选择符等。
# 不依赖第三方库，避免为展示层过滤引入额外运行时依赖。
_EMOJI_PATTERN = re.compile(
    "("
    # 区域指示符国旗（成对出现）
    r"[\U0001F1E6-\U0001F1FF]{2}"
    r"|"
    # 常见 emoji 与符号区段 + 可选肤色 + 可选变体选择符 + 可选零宽连接续接
    r"(?:"
    r"[\U0001F300-\U0001F5FF]"  # 杂项符号与象形文字
    r"|[\U0001F600-\U0001F64F]"  # 表情符号
    r"|[\U0001F680-\U0001F6FF]"  # 交通与地图符号
    r"|[\U0001F700-\U0001F77F]"  # 炼金术符号
    r"|[\U0001F780-\U0001F7FF]"  # 几何图形扩展（含彩色方块/圆形）
    r"|[\U0001F800-\U0001F8FF]"  # 补充箭头-C
    r"|[\U0001F900-\U0001F9FF]"  # 补充符号与象形文字
    r"|[\U0001FA00-\U0001FA6F]"  # 国际象棋符号
    r"|[\U0001FA70-\U0001FAFF]"  # 符号与象形文字扩展-A
    r"|[\U00002700-\U000027BF]"  # 装饰符号
    r"|[\U00002600-\U000026FF]"  # 杂项符号
    r"|[\U00002300-\U000023FF]"  # 杂项技术符号
    r"|[\U00002B00-\U00002BFF]"  # 杂项符号与箭头
    r"|[\U00002900-\U0000297F]"  # 补充箭头-B
    r"|[\U00002190-\U000021FF]"  # 箭头
    r"|[\U00003030\U0000303D\U00003297\U00003299]"  # 波浪线/部分封闭表意文字
    r"|[\U000000A9\U000000AE\U0000203C\U00002049\U00002122\U00002139]"  # 版权/注册/叹号问号等
    r"|[\U00002194-\U00002199\U000021A9\U000021AA]"  # 双向箭头与弯箭头
    r"|[\U0000231A\U0000231B\U00002328\U000023CF]"  # 手表/沙漏/键盘/弹出
    r"|[\U000023E9-\U000023F3\U000023F8-\U000023FA]"  # 播放控制与计时符号
    r"|[\U000024C2\U000025AA\U000025AB\U000025B6\U000025C0]"  # 圆圈字母与几何播放符
    r"|[\U000025FB-\U000025FE]"  # 中等几何方块
    r"|[\U00002B05-\U00002B07\U00002B1B\U00002B1C\U00002B50\U00002B55]"  # 方向箭头/大方块/星/圆
    r"|[\U00002934\U00002935]"  # 弧形箭头
    r")"
    r"[\U0001F3FB-\U0001F3FF]?"  # 肤色修饰符
    r"(?:\uFE0E|\uFE0F)?"  # 文本/emoji 变体选择符
    r"(?:"
    r"\u200D"
    r"(?:"
    r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF]"
    r"[\U0001F3FB-\U0001F3FF]?"
    r"(?:\uFE0E|\uFE0F)?"
    r")+"
    r")?"
    r")",
    flags=re.UNICODE,
)

# 过滤后清理：连续空白压成单空格，但保留换行结构。
_MULTI_SPACE_PATTERN = re.compile(r"[^\S\n]{2,}")
_TRAILING_SPACE_PATTERN = re.compile(r"[ \t]+\n")
_LEADING_SPACE_PATTERN = re.compile(r"\n[ \t]+")


def normalize_emoji_filter_mode(mode: str | None) -> str:
    """将配置值规范化为三档之一；非法值回退为默认。"""
    if not isinstance(mode, str):
        return EMOJI_FILTER_MODE_DEFAULT
    value = mode.strip()
    if value in VALID_EMOJI_FILTER_MODES:
        return value
    # 兼容可能的英文别名
    aliases = {
        "default": EMOJI_FILTER_MODE_DEFAULT,
        "full": EMOJI_FILTER_MODE_DEFAULT,
        "minimal": EMOJI_FILTER_MODE_MINIMAL,
        "simple": EMOJI_FILTER_MODE_MINIMAL,
        "compact": EMOJI_FILTER_MODE_MINIMAL,
        "off": EMOJI_FILTER_MODE_OFF,
        "none": EMOJI_FILTER_MODE_OFF,
        "disable": EMOJI_FILTER_MODE_OFF,
        "disabled": EMOJI_FILTER_MODE_OFF,
        "close": EMOJI_FILTER_MODE_OFF,
    }
    return aliases.get(value.lower(), EMOJI_FILTER_MODE_DEFAULT)


def _cleanup_spaces(text: str) -> str:
    """清理 emoji 删除后残留的多余空白，尽量保持原有换行排版。"""
    text = _TRAILING_SPACE_PATTERN.sub("\n", text)
    text = _LEADING_SPACE_PATTERN.sub("\n", text)
    text = _MULTI_SPACE_PATTERN.sub(" ", text)
    return text.strip(" \t")


def _is_severity_indicator(emoji: str) -> bool:
    """判断是否为简洁模式应保留的严重性指示图标。"""
    # 去掉变体选择符后再比对，兼容 ⚪︎ / ⚪️ 等写法。
    normalized = emoji.replace("\ufe0f", "").replace("\ufe0e", "")
    if normalized in SEVERITY_INDICATOR_EMOJIS:
        return True
    if emoji in SEVERITY_INDICATOR_EMOJIS:
        return True
    return False


def filter_push_text_emoji(text: str, mode: str | None = None) -> str:
    """按模式过滤推送文本中的 emoji。

    参数：
    - text：原始推送文本
    - mode：默认 / 简洁 / 关闭

    返回：
    - 过滤后的文本；默认模式原样返回
    """
    if not text:
        return text

    normalized_mode = normalize_emoji_filter_mode(mode)
    if normalized_mode == EMOJI_FILTER_MODE_DEFAULT:
        return text

    if normalized_mode == EMOJI_FILTER_MODE_OFF:

        def _remove_all(match: re.Match[str]) -> str:
            return ""

        filtered = _EMOJI_PATTERN.sub(_remove_all, text)
        return _cleanup_spaces(filtered)

    # 简洁模式：仅保留严重性指示图标
    def _keep_severity(match: re.Match[str]) -> str:
        token = match.group(0)
        return token if _is_severity_indicator(token) else ""

    filtered = _EMOJI_PATTERN.sub(_keep_severity, text)
    return _cleanup_spaces(filtered)


__all__ = [
    "EMOJI_FILTER_MODE_DEFAULT",
    "EMOJI_FILTER_MODE_MINIMAL",
    "EMOJI_FILTER_MODE_OFF",
    "VALID_EMOJI_FILTER_MODES",
    "SEVERITY_INDICATOR_EMOJIS",
    "normalize_emoji_filter_mode",
    "filter_push_text_emoji",
]
