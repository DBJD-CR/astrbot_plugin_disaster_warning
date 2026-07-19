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

        # 助手方法：基于 combine_mode 来组合多个条件判断结果
        def _combine_checks(
            combine_mode: str, checks: list[tuple[str, bool, str]]
        ) -> RuleDecision | None:
            if not checks:
                return None
            if combine_mode == "any":
                if any(passed for _, passed, _ in checks):
                    return None
                detail = "；".join(desc for _, _, desc in checks)
                return RuleDecision.reject(
                    reason="强度过滤器不满足(any)",
                    detail=f"满足任一条件组合失败：{detail}",
                )
            else:  # all
                failed = [desc for _, passed, desc in checks if not passed]
                if failed:
                    return RuleDecision.reject(
                        reason="强度过滤器不满足(all)",
                        detail=f"满足全部条件失败：{'；'.join(failed)}",
                    )
                return None

        # 模式 1：Global Quake，由于涉及罗马数字，较高的推送频率等，需要专门定制过滤条件
        if source_id == "global_quake":
            runtime_filter = policy_state.get("global_quake_filter") or {}
            if runtime_filter.get("enabled", True):
                combine_mode = (
                    str(runtime_filter.get("combine_mode") or "any").strip().lower()
                )
                checks = []
                # 震级条件
                mag = earthquake.magnitude
                min_mag = runtime_filter.get("min_magnitude", 4.5)
                mag_passed = mag is not None and mag >= min_mag
                checks.append(
                    ("magnitude", mag_passed, f"震级 {mag or '无'} ≥ {min_mag}")
                )
                # 烈度条件
                val = earthquake.intensity
                min_val = runtime_filter.get("min_intensity", 5.0)
                val_passed = isinstance(val, (int, float)) and val >= min_val
                checks.append(
                    ("intensity", val_passed, f"最大烈度 {val or '无'} ≥ {min_val}")
                )

                decision = _combine_checks(combine_mode, checks)
                if decision is not None:
                    return decision
            return RuleDecision.accept(reason="Global Quake规则通过")

        # 模式 2：烈度过滤器（通常为中国地震预警），同样为震级与烈度或的双通道达标放行
        if intensity_mode == "intensity":
            runtime_filter = policy_state.get("intensity_filter") or {}
            if runtime_filter.get("enabled", True):
                combine_mode = (
                    str(runtime_filter.get("combine_mode") or "any").strip().lower()
                )
                checks = []
                # 震级条件
                mag = earthquake.magnitude
                min_mag = runtime_filter.get("min_magnitude", 2.0)
                mag_passed = mag is not None and mag >= min_mag
                checks.append(
                    ("magnitude", mag_passed, f"震级 {mag or '无'} ≥ {min_mag}")
                )
                # 烈度条件
                val = earthquake.intensity
                min_val = runtime_filter.get("min_intensity", 4.0)
                val_passed = val is not None and val >= min_val
                checks.append(
                    ("intensity", val_passed, f"最大烈度 {val or '无'} ≥ {min_val}")
                )

                decision = _combine_checks(combine_mode, checks)
                if decision is not None:
                    return decision
            return RuleDecision.accept(reason="烈度规则通过")

        # 模式 3：震度过滤器（日本、台湾），同样为震级达标或震度达标其一通过
        if intensity_mode == "scale":
            runtime_filter = policy_state.get("scale_filter") or {}
            if runtime_filter.get("enabled", True):
                combine_mode = (
                    str(runtime_filter.get("combine_mode") or "any").strip().lower()
                )
                checks = []
                # 震级条件
                mag = earthquake.magnitude
                min_mag = runtime_filter.get("min_magnitude", 2.0)
                mag_passed = mag is not None and mag != -1.0 and mag >= min_mag
                checks.append(
                    ("magnitude", mag_passed, f"震级 {mag or '无'} ≥ {min_mag}")
                )
                # 震度条件
                scale = earthquake.scale
                min_scale = runtime_filter.get("min_scale", 1.0)
                scale_passed = scale is not None and scale >= min_scale
                checks.append(
                    ("scale", scale_passed, f"最大震度 {scale or '无'} ≥ {min_scale}")
                )

                decision = _combine_checks(combine_mode, checks)
                if decision is not None:
                    return decision
            return RuleDecision.accept(reason="震度规则通过")

        # 模式 4：S-Net 海底震度监测（包含最大震度过滤与触发测站数过滤）
        if source_id == "snet_msil" or intensity_mode == "snet_shindo":
            runtime_filter = policy_state.get("snet_filter") or {}
            if runtime_filter.get("enabled", True):
                combine_mode = (
                    str(runtime_filter.get("combine_mode") or "any").strip().lower()
                )
                checks = []

                # 条件一：最大震度过滤
                min_shindo = runtime_filter.get("min_shindo", 1.5)
                try:
                    min_shindo = float(min_shindo)
                except (TypeError, ValueError):
                    min_shindo = 1.5
                if min_shindo < -3.0:
                    min_shindo = -3.0
                if min_shindo > 7.0:
                    min_shindo = 7.0

                max_shindo = earthquake.scale
                if max_shindo is None:
                    metadata = getattr(earthquake, "metadata", {}) or {}
                    if isinstance(metadata, dict):
                        max_shindo = metadata.get("max_shindo")
                try:
                    max_shindo_val = (
                        float(max_shindo) if max_shindo is not None else None
                    )
                except (TypeError, ValueError):
                    max_shindo_val = None

                shindo_passed = (
                    max_shindo_val is not None and max_shindo_val >= min_shindo
                )
                checks.append(
                    (
                        "shindo",
                        shindo_passed,
                        f"最大震度 {max_shindo_val or '无'} ≥ {min_shindo}",
                    )
                )

                # 条件二：触发测站数量过滤
                min_triggered_stations = int(
                    runtime_filter.get("min_triggered_stations", 0)
                )
                station_min_shindo = float(
                    runtime_filter.get("station_min_shindo", 0.5)
                )

                if min_triggered_stations > 0:
                    # 优先从 metadata 获取针对触发测站数判定的 station_min_shindo 计数结果
                    metadata = getattr(earthquake, "metadata", {}) or {}
                    triggered_station_count = None
                    if isinstance(metadata, dict):
                        # 如果 metadata 里存有触发测站数，可以直接使用
                        triggered_station_count = metadata.get(
                            "triggered_station_count"
                        )

                    if triggered_station_count is None:
                        # 兜底通过 stations 列表计算
                        stations = (
                            metadata.get("stations")
                            or getattr(earthquake, "stations", None)
                            or []
                        )
                        if isinstance(stations, list):
                            triggered_station_count = sum(
                                1
                                for s in stations
                                if isinstance(s, dict)
                                and float(s.get("shindo", -999.0)) >= station_min_shindo
                            )
                        else:
                            triggered_station_count = 0

                    station_passed = triggered_station_count >= min_triggered_stations
                    checks.append(
                        (
                            "triggered_stations",
                            station_passed,
                            f"测站震度≥{station_min_shindo}的触发测站数 {triggered_station_count} ≥ {min_triggered_stations}",
                        )
                    )

                decision = _combine_checks(combine_mode, checks)
                if decision is not None:
                    return decision
            return RuleDecision.accept(reason="S-Net规则通过")

        # 模式 5：仅依赖震级阈值的来源统一走这一分支。
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
