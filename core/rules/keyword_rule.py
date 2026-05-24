"""
关键词规则。
负责根据地点名称中的黑白名单关键词，对地震事件做进一步筛选。
"""

from __future__ import annotations

from ..domain.event_models import EarthquakeEvent
from .base_rule import BaseRule, RuleContext
from .rule_result import RuleDecision


class KeywordRule(BaseRule):
    """旧关键词过滤器的规则化包装。"""

    rule_name = "keyword_rule"

    def evaluate(self, context: RuleContext) -> RuleDecision:
        """按地点名称执行关键词黑白名单过滤。"""
        domain_event = context.domain_event
        # 仅对地震事件的 place_name 执行过滤
        if not isinstance(domain_event, EarthquakeEvent):
            return RuleDecision.accept(reason="非地震事件，跳过关键词规则")

        keyword_filter = context.policy_state.get("keyword_filter") or {}
        # 若未开启关键词过滤开关，默认直接放行
        if not keyword_filter.get("enabled", False):
            return RuleDecision.accept(reason="关键词规则未启用")

        location = domain_event.place_name or ""

        # 加载配置中的黑白名单过滤关键词列表
        # 黑名单命中即拒绝，白名单存在时则要求至少命中一个关键词。
        blacklist = [
            keyword for keyword in keyword_filter.get("blacklist", []) if keyword
        ]
        whitelist = [
            keyword for keyword in keyword_filter.get("whitelist", []) if keyword
        ]

        # 黑名单检验：一旦震中地点名包含任何黑名单关键词，立即判定拒绝
        for keyword in blacklist:
            if keyword in location:
                return RuleDecision.reject(
                    reason="关键词过滤",
                    detail=f"命中黑名单关键词：{keyword}",
                    context={"keyword": keyword, "source_id": context.source_id},
                )

        # 白名单检验：若白名单非空，要求地点名必须至少命中其中一个关键词，否则过滤拒绝
        if whitelist and not any(keyword in location for keyword in whitelist):
            return RuleDecision.reject(
                reason="关键词过滤",
                detail=f"事件未命中白名单关键词，来源：{context.source_id}",
                context={"source_id": context.source_id, "location": location},
            )

        # 全校验通过
        return RuleDecision.accept(reason="关键词规则通过")
