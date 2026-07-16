"""
数据源开关规则。
负责根据会话运行时配置，判断当前事件所属数据源及其分组是否启用。
"""

from __future__ import annotations

from ..sources.source_catalog import get_source_entry
from .base_rule import BaseRule, RuleContext
from .rule_result import RuleDecision


class SourceEnabledRule(BaseRule):
    """运行时数据源开关规则。"""

    rule_name = "source_rule"

    def evaluate(self, context: RuleContext) -> RuleDecision:
        """检查当前事件对应的数据源是否在会话中开启。

        判定口径必须与 SourceRuntimeQueryService.is_source_enabled 对齐：
        - 分组/子源缺省均为 False（opt-in）
        - 未注册 source_id / 配置缺失 → 不推送
        避免数据源在会话差异配置中“未显式开启却被默认放行”。
        """
        # 单元测试模拟发震，直接通过，绕开全局数据源开关限制
        if context.runtime_config.get("__simulation_bypass_regular_filters", False):
            return RuleDecision.accept(reason="模拟模式跳过数据源开关过滤")

        source_id = context.source_id
        # 读取会话生效配置中的 data_sources（已含全局默认 + 会话 override）
        data_sources_cfg = context.runtime_config.get("data_sources", {})
        source_entry = get_source_entry(source_id)

        # 未注册数据源：不推送，与运行时查询服务一致
        if source_entry is None:
            return RuleDecision.reject(
                reason="会话数据源开关关闭",
                detail=f"未注册数据源 {source_id or 'unknown'}，拒绝推送",
                context={"source_id": source_id},
            )

        # 配置结构异常时不放行 opt-in 源
        if not isinstance(data_sources_cfg, dict):
            return RuleDecision.reject(
                reason="会话数据源开关关闭",
                detail=f"会话 {context.session_id or 'global'} 数据源配置无效",
                context={"source_id": source_id},
            )

        group_cfg = data_sources_cfg.get(source_entry.config_group, {})
        if not isinstance(group_cfg, dict):
            group_cfg = {}

        # 分组总开关：缺省 False（与 SourceRuntimeQueryService 一致）
        if not bool(group_cfg.get("enabled", False)):
            return RuleDecision.reject(
                reason="会话数据源开关关闭",
                detail=(
                    f"会话 {context.session_id or 'global'} 已禁用数据源分组 "
                    f"{source_entry.config_group}"
                ),
                context={"source_id": source_id},
            )

        # 组内子源开关：缺省 False。
        # 注意 S-Net 的 config_key 本身就是 "enabled"，与分组开关同一字段，
        # 此时 group 已通过则子源也通过；其他源（如 wolfx.*）仍检查独立子键。
        source_enabled = bool(group_cfg.get(source_entry.config_key, False))
        if source_enabled:
            return RuleDecision.accept(reason="数据源已启用")

        return RuleDecision.reject(
            reason="会话数据源开关关闭",
            detail=f"会话 {context.session_id or 'global'} 已禁用数据源 {source_id}",
            context={"source_id": source_id},
        )
