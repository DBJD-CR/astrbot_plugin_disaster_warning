"""台风名称展示格式化。"""

from __future__ import annotations

from .typhoon_values import clean_text


def format_display_name(
    name_cn: object = "",
    name_en: object = "",
    typhoon_id: object = "",
    *,
    fallback: str = "未知台风",
) -> str:
    """生成统一的“中文（EN）”展示名，避免英文名重复拼接。"""
    cn = clean_text(name_cn).replace("(", "（").replace(")", "）")
    en = clean_text(name_en)
    tid = clean_text(typhoon_id)
    if cn and en:
        if en in cn or f"（{en}）" in cn or f"({en})" in cn:
            return cn
        return f"{cn}（{en}）"
    return cn or en or tid or fallback
