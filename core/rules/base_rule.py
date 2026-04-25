"""
统一规则抽象定义。
负责约束规则上下文结构，并提供所有过滤规则共用的基类接口。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.event_models import EventEnvelope


@dataclass(slots=True)
class RuleContext:
    """规则执行上下文。

    用于在规则链各节点之间传递事件对象、运行时配置、策略状态与临时附加数据。
    """

    event: Any
    runtime_config: dict[str, Any]
    policy_state: dict[str, Any]
    session_id: str | None = None
    commit_state: bool = True
    logger_instance: Any = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def envelope(self) -> EventEnvelope:
        """统一事件包裹体访问入口。

        这里会把首次解析成功的包裹体缓存到附加数据中，避免后续规则重复做类型判断。
        """
        cached = self.extras.get("event_envelope")
        if isinstance(cached, EventEnvelope):
            return cached
        if not isinstance(self.event, EventEnvelope):
            raise TypeError(
                f"RuleContext.event 仅接受 EventEnvelope，收到: {type(self.event)}"
            )
        self.extras["event_envelope"] = self.event
        return self.event

    @property
    def domain_event(self) -> Any:
        """统一领域事件访问入口。"""
        return self.envelope.event

    @property
    def event_type(self) -> str:
        """统一事件类型访问入口。"""
        return self.envelope.event_type

    @property
    def source_id(self) -> str:
        """统一数据源标识访问入口。"""
        return self.envelope.source_id


class BaseRule:
    """统一规则接口。

    各具体规则只需实现评估方法，并返回是否放行的决策结果。
    """

    rule_name = "base_rule"

    def evaluate(self, context: RuleContext):
        """评估当前规则。

        子类应根据上下文决定是否放行事件，并返回对应的规则决策对象。
        """
        raise NotImplementedError
