"""
统一规则结果定义。
负责描述规则是否放行、原因、细节以及可供后续链路复用的上下文信息。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RuleDecision:
    """规则决策结果。

    该对象同时承担链路调试信息载体的职责，便于后续记录过滤原因。
    """

    accepted: bool
    reason: str = ""
    detail: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def accept(
        cls,
        *,
        reason: str = "通过",
        detail: str = "",
        context: dict[str, Any] | None = None,
    ) -> RuleDecision:
        """构造放行结果。"""
        return cls(
            accepted=True,
            reason=reason,
            detail=detail,
            context=context or {},
        )

    @classmethod
    def reject(
        cls,
        *,
        reason: str,
        detail: str = "",
        context: dict[str, Any] | None = None,
    ) -> RuleDecision:
        """构造拒绝结果。"""
        return cls(
            accepted=False,
            reason=reason,
            detail=detail,
            context=context or {},
        )
