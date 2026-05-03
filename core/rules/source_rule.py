"""
数据源开关规则。
负责根据会话运行时配置，判断当前事件所属数据源及其分组是否启用。
"""

from __future__ import annotations

from ..sources.source_catalog import SOURCE_CATALOG, get_source_entry
from .base_rule import BaseRule, RuleContext
from .rule_result import RuleDecision


class SourceEnabledRule(BaseRule):
    """运行时数据源开关规则。"""

    rule_name = "source_rule"

    def evaluate(self, context: RuleContext) -> RuleDecision:
        """检查当前事件对应的数据源是否在会话中开启。"""
        source_id = context.source_id
        data_sources_cfg = context.runtime_config.get("data_sources", {})
        source_entry = get_source_entry(source_id)

        # 缺少配置或目录项时默认放行，避免因配置不完整误拦截事件。
        if not isinstance(data_sources_cfg, dict) or source_entry is None:
            return RuleDecision.accept(reason="数据源已启用")

        # 先检查所属分组，再检查具体数据源开关，保持配置层级一致。
        group_cfg = data_sources_cfg.get(source_entry.config_group, {})
        if not isinstance(group_cfg, dict):
            return RuleDecision.accept(reason="数据源已启用")

        if group_cfg.get("enabled", True) is False:
            return RuleDecision.reject(
                reason="会话数据源开关关闭",
                detail=f"会话 {context.session_id or 'global'} 已禁用数据源分组 {source_entry.config_group}",
                context={"source_id": source_id},
            )

        catalog_entry = SOURCE_CATALOG.get(source_id)
        default_enabled = True
        if catalog_entry is not None:
            default_group_cfg = data_sources_cfg.get(catalog_entry.config_group, {})
            if (
                isinstance(default_group_cfg, dict)
                and catalog_entry.config_key in default_group_cfg
            ):
                default_enabled = bool(
                    default_group_cfg.get(catalog_entry.config_key, True)
                )

        source_enabled = bool(group_cfg.get(source_entry.config_key, default_enabled))
        if source_enabled:
            return RuleDecision.accept(reason="数据源已启用")

        return RuleDecision.reject(
            reason="会话数据源开关关闭",
            detail=f"会话 {context.session_id or 'global'} 已禁用数据源 {source_id}",
            context={"source_id": source_id},
        )
