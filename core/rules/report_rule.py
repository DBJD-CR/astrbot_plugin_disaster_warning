"""
报次规则。
负责按不同来源的报次策略控制推送频率，并处理首报、最终报等特殊放行条件。
"""

from __future__ import annotations

from ..domain.event_models import EarthquakeEvent
from ..services.identity.event_identity import resolve_report_num
from ..sources.source_catalog import get_source_entry
from .base_rule import BaseRule, RuleContext
from .rule_result import RuleDecision


class ReportRule(BaseRule):
    """原生报次规则。"""

    rule_name = "report_rule"

    def evaluate(self, context: RuleContext) -> RuleDecision:
        """根据来源报次策略决定当前事件是否应被推送。"""
        domain_event = context.domain_event
        if not isinstance(domain_event, EarthquakeEvent):
            return RuleDecision.accept(reason="非地震事件，跳过报数规则")

        # 不同来源的报次推进逻辑不同，因此先从目录中读取对应的报次策略。
        source_entry = get_source_entry(context.source_id)
        report_policy = (
            (source_entry.report_policy if source_entry is not None else "none")
            .strip()
            .lower()
        )
        if report_policy == "none":
            return RuleDecision.accept(reason="当前数据源无报数控制")

        push_config = context.runtime_config.get("push_frequency_control", {})
        report_num = resolve_report_num(context.event) or 1
        event_id = context.envelope.id or context.source_id or "unknown_event"
        # 状态存储用于记录某个事件最近一次已接受的报次，便于后续规则复用。
        state_store = context.extras.setdefault("report_rule_state", {})

        # 先以大陆和台湾预警的默认值初始化，再根据不同来源覆写。
        push_every_n = int(push_config.get("cea_cwa_report_n", 1) or 1)
        supports_final = True
        if report_policy == "jma":
            push_every_n = int(push_config.get("jma_report_n", 3) or 3)
        elif report_policy == "global_quake":
            push_every_n = int(push_config.get("gq_report_n", 5) or 5)
            supports_final = False
        elif report_policy == "cea_cwa":
            supports_final = False

        final_report_always_push = bool(
            push_config.get("final_report_always_push", True)
        )
        ignore_non_final_reports = bool(
            push_config.get("ignore_non_final_reports", False)
        )
        identity = getattr(context.envelope, "identity", None)
        metadata = (
            context.envelope.metadata
            if isinstance(context.envelope.metadata, dict)
            else {}
        )
        is_final = (
            (
                bool(getattr(identity, "is_final", False))
                or bool(metadata.get("is_final", False))
            )
            if supports_final
            else False
        )

        # 若配置要求最终报始终放行，则优先于常规报次间隔判断。
        if is_final and final_report_always_push:
            if context.commit_state:
                state_store[event_id] = report_num
            return RuleDecision.accept(
                reason="最终报直接放行",
                context={"event_id": event_id, "report_num": report_num},
            )

        # 首报通常信息最关键，默认直接放行。
        if report_num == 1:
            if context.commit_state:
                state_store[event_id] = report_num
            return RuleDecision.accept(
                reason="首报直接放行",
                context={"event_id": event_id, "report_num": report_num},
            )

        if ignore_non_final_reports and supports_final and not is_final:
            return RuleDecision.reject(
                reason="忽略非最终报",
                detail=f"事件 {event_id} 第 {report_num} 报未达到最终报条件",
                context={"event_id": event_id, "report_num": report_num},
            )

        # 兜底防御非法配置，避免出现除零或恒不命中的情况。
        if push_every_n <= 0:
            push_every_n = 1

        if report_num % push_every_n == 0:
            if context.commit_state:
                state_store[event_id] = report_num
            return RuleDecision.accept(
                reason="报数规则通过",
                detail=f"事件 {event_id} 第 {report_num} 报命中间隔值 {push_every_n}",
                context={
                    "event_id": event_id,
                    "report_num": report_num,
                    "push_every_n": push_every_n,
                },
            )

        return RuleDecision.reject(
            reason="报数规则过滤",
            detail=f"事件 {event_id} 第 {report_num} 报未命中间隔值 {push_every_n}",
            context={
                "event_id": event_id,
                "report_num": report_num,
                "push_every_n": push_every_n,
            },
        )
