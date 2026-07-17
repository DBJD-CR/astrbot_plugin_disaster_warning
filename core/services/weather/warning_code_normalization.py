"""Normalize weather warning codes against their semantic warning names."""

from __future__ import annotations

import re
from typing import Any


# FAN icons use the national 11B warning namespace. Some upstream payloads carry
# CMA's compact TYPECODE under the same prefix, so the warning name is the
# authoritative discriminator when the two namespaces conflict.
_STANDARD_WARNING_CODE_BY_NAME = {
    "台风": "11B01",
    "龙卷风": "11B02",
    "暴雨": "11B03",
    "暴雪": "11B04",
    "寒潮": "11B05",
    "大风": "11B06",
    "沙尘暴": "11B07",
    "低温冻害": "11B08",
    "高温": "11B09",
    "热浪": "11B10",
    "干热风": "11B11",
    "下击暴流": "11B12",
    "雪崩": "11B13",
    "雷电": "11B14",
    "冰雹": "11B15",
    "霜冻": "11B16",
    "大雾": "11B17",
    "低空风切变": "11B18",
    "霾": "11B19",
    "雷雨大风": "11B20",
    "雷雨强风": "11B20",
    "道路结冰": "11B21",
    "干旱": "11B22",
    "海上大风": "11B23",
    "海区大风": "11B23",
    "高温中暑": "11B24",
    "森林火险": "11B25",
    "草原火险": "11B26",
    "冰冻": "11B27",
    "空间天气": "11B28",
    "重污染": "11B29",
    "空气重污染": "11B29",
    "重污染天气": "11B29",
    "低温雨雪冰冻": "11B30",
    "强对流": "11B31",
    "臭氧": "11B32",
    "臭氧污染": "11B32",
    "大雪": "11B33",
    "寒冷": "11B34",
    "连阴雨": "11B35",
    "渍涝风险": "11B36",
    "地质灾害气象风险": "11B37",
    "地质灾害": "11B37",
    "强降雨": "11B38",
    "强降温": "11B39",
    "雪灾": "11B40",
    "森林（草原）火险": "11B41",
    "森林(草原)火险": "11B41",
    "医疗气象": "11B42",
    "雷暴": "11B43",
    "停课信号": "11B44",
    "停工信号": "11B45",
    "海上风险": "11B46",
    "春季沙尘天气": "11B47",
    "降温": "11B48",
    "台风暴雨": "11B49",
    "严寒": "11B50",
    "沙尘": "11B51",
    "海上雷雨大风": "11B52",
    "海上大雾": "11B53",
    "海上雷电": "11B54",
    "海上台风": "11B55",
    "低温": "11B56",
    "道路冰雪": "11B57",
    "雷暴大风": "11B58",
    "持续低温": "11B59",
    "浓浮尘": "11B61",
    "短时强阵雨": "11B64",
    "短时强降水": "11B64",
}
_SORTED_WARNING_NAMES = tuple(
    sorted(_STANDARD_WARNING_CODE_BY_NAME, key=len, reverse=True)
)
_FAN_WARNING_CODE_PATTERN = re.compile(
    r"^(?P<code>11B\d{2})(?P<suffix>_(?:blue|yellow|orange|red|white))?$",
    re.IGNORECASE,
)


def normalize_weather_warning_code(
    source_code: Any,
    *semantic_texts: Any,
) -> str:
    """Return a canonical FAN icon code when warning text resolves a conflict."""
    code = source_code.strip() if isinstance(source_code, str) else ""
    match = _FAN_WARNING_CODE_PATTERN.fullmatch(code)
    if match is None:
        return code

    for value in semantic_texts:
        if not isinstance(value, str) or not value.strip():
            continue
        warning_name = next(
            (name for name in _SORTED_WARNING_NAMES if name in value),
            None,
        )
        if warning_name is None:
            continue
        canonical_code = _STANDARD_WARNING_CODE_BY_NAME[warning_name]
        suffix = (match.group("suffix") or "").lower()
        return f"{canonical_code}{suffix}"

    return code
