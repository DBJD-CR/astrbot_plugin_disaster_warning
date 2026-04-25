"""
领域事件身份模型。
统一表达事件业务身份、来源身份与展示可追踪标识，
用于替代旧 support / metadata 中分散的身份字段拼装逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class EventIdentity:
    """统一事件身份描述。"""

    # event_id 是事件在业务层的主标识。
    event_id: str
    # source_id 标识来自哪个具体数据源。
    source_id: str
    # event_type 用于区分地震、海啸、气象等灾种。
    event_type: str
    # provider_family 与 source_enum 主要用于归类来源体系和兼容旧枚举。
    provider_family: str = ""
    source_enum: str = ""
    # report_num 用于区分同一事件的第几报。
    report_num: int | None = None
    published_at: Any | None = None
    is_final: bool = False
    # aliases 用于收纳同一事件在不同来源或不同规则下的别名标识。
    aliases: tuple[str, ...] = ()
    # attributes 用于放置少量补充身份属性，避免无限扩张固定字段。
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def unique_key(self) -> str:
        """返回可用于去重与索引的统一键。"""
        report_suffix = f"|{self.report_num}" if self.report_num is not None else ""
        return f"{self.source_id}|{self.event_type}|{self.event_id}{report_suffix}"


__all__ = ["EventIdentity"]
