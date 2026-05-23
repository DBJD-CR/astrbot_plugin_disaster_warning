"""
地震强度规则。
负责根据不同数据源的强度判定模式，选择合适的震级、烈度或震度过滤策略。
"""

from __future__ import annotations

from ..domain.event_models import EarthquakeEvent
from ..sources.source_catalog import get_source_entry
from .base_rule import BaseRule, RuleContext
from .rule_result import RuleDecision


class EarthquakeThresholdRule(BaseRule):
    """按数据源强度模式选择过滤策略。"""

    rule_name = "intensity_rule"

    def evaluate(self, context: RuleContext) -> RuleDecision:
        """根据事件来源和强度模式执行地震过滤。"""
        domain_event = context.domain_event
        # 仅针对地震事件做强度限制过滤，非地震事件默认放行
        if not isinstance(domain_event, EarthquakeEvent):
            return RuleDecision.accept(reason="非地震事件，跳过强度规则")

        earthquake = domain_event
        source_id = context.source_id
        policy_state = context.policy_state
        source_entry = get_source_entry(source_id)
        # 获取该数据源的强度判定模式
        intensity_mode = (
            (source_entry.intensity_mode if source_entry is not None else "")
            .strip()
            .lower()
        )

        # 单元测试或模拟发震场景，支持强制绕过常规数值过滤
        if context.runtime_config.get("__simulation_bypass_regular_filters", False):
            return RuleDecision.accept(reason="模拟模式跳过强度过滤")

        # 模式 1：Global Quake，由于涉及罗马数字，较高的推送频率等，需要专门定制过滤条件
        if source_id == "global_quake":
            runtime_filter = policy_state.get("global_quake_filter") or {}
            if runtime_filter.get("enabled", True):
                # 震级或最大烈度满足其一即可放行
                magnitude_pass = (
                    earthquake.magnitude is not None
                    and earthquake.magnitude >= runtime_filter.get("min_magnitude", 4.5)
                )
                intensity_pass = isinstance(
                    earthquake.intensity, (int, float)
                ) and earthquake.intensity >= runtime_filter.get("min_intensity", 5.0)
                if not (magnitude_pass or intensity_pass):
                    return RuleDecision.reject(reason="Global Quake过滤器")
            return RuleDecision.accept(reason="Global Quake规则通过")

        # 模式 2：烈度过滤器（通常为中国地震预警），同样为震级与烈度或的双通道达标放行
        if intensity_mode == "intensity":
            runtime_filter = policy_state.get("intensity_filter") or {}
            if runtime_filter.get("enabled", True):
                magnitude_pass = (
                    earthquake.magnitude is not None
                    and earthquake.magnitude >= runtime_filter.get("min_magnitude", 2.0)
                )
                intensity_pass = (
                    earthquake.intensity is not None
                    and earthquake.intensity >= runtime_filter.get("min_intensity", 4.0)
                )
                if not (magnitude_pass or intensity_pass):
                    return RuleDecision.reject(reason="烈度过滤器")
            return RuleDecision.accept(reason="烈度规则通过")

        # 模式 3：震度过滤器（日本、台湾），同样为震级达标或震度达标其一通过
        if intensity_mode == "scale":
            runtime_filter = policy_state.get("scale_filter") or {}
            if runtime_filter.get("enabled", True):
                magnitude_pass = (
                    earthquake.magnitude is not None
                    and earthquake.magnitude != -1.0
                    and earthquake.magnitude >= runtime_filter.get("min_magnitude", 2.0)
                )
                scale_pass = (
                    earthquake.scale is not None
                    and earthquake.scale >= runtime_filter.get("min_scale", 1.0)
                )
                if not (magnitude_pass or scale_pass):
                    return RuleDecision.reject(reason="震度过滤器")
            return RuleDecision.accept(reason="震度规则通过")

        # 模式 4：仅依赖震级阈值的来源统一走这一分支。
        if source_id == "usgs_fanstudio" or intensity_mode == "magnitude":
            runtime_filter = policy_state.get("usgs_filter") or {}
            if runtime_filter.get("enabled", True):
                if (
                    earthquake.magnitude is not None
                    and earthquake.magnitude < runtime_filter.get("min_magnitude", 4.5)
                ):
                    return RuleDecision.reject(reason="USGS过滤器")
            return RuleDecision.accept(reason="USGS规则通过")

        # 其他未配置强度模式的数据源默认直接通过
        return RuleDecision.accept(reason="无需强度过滤")
