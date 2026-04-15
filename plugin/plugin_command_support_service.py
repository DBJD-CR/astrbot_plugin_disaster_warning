"""
插件命令层支持服务。
负责管理员校验、引用回复构造、配置 Schema 缓存与配置展示翻译等横切能力，
减少 main.DisasterWarningPlugin 中重复的命令辅助逻辑。
"""

from __future__ import annotations

import json
import os
from typing import Any

import astrbot.api.message_components as Comp


class PluginCommandSupportService:
    """插件命令支持服务。"""

    def __init__(self, plugin):
        self.plugin = plugin

    async def is_plugin_admin(self, event) -> bool:
        """检查用户是否为插件管理员或 Bot 管理员。"""
        if event.is_admin():
            return True

        sender_id = event.get_sender_id()
        plugin_admins = self.plugin.config.get("admin_users", [])
        return sender_id in plugin_admins

    @staticmethod
    def with_quote_reply(event, chain: list[Any]) -> list[Any]:
        """为消息链添加引用回复段（若可用）。"""
        message_obj = getattr(event, "message_obj", None)
        message_id = getattr(message_obj, "message_id", None) if message_obj else None
        if not message_id:
            return chain
        return [Comp.Reply(id=str(message_id)), *chain]

    def get_config_schema(self) -> dict[str, Any]:
        """获取并缓存配置 Schema。"""
        # Schema 只需读取一次，后续命令查询场景直接复用缓存以减少文件 IO。
        if self.plugin._config_schema is not None:
            return self.plugin._config_schema

        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "_conf_schema.json",
        )
        if os.path.exists(schema_path):
            with open(schema_path, encoding="utf-8") as f:
                self.plugin._config_schema = json.load(f)
        else:
            self.plugin._config_schema = {}
        return self.plugin._config_schema

    def translate_config_recursive(
        self,
        config_item: Any,
        schema_item: dict[str, Any] | None,
    ) -> Any:
        """递归将配置键名转换为中文描述。"""
        if not isinstance(config_item, dict):
            return config_item

        translated: dict[str, Any] = {}
        schema_item = schema_item or {}
        for key, value in config_item.items():
            item_schema = (
                schema_item.get(key, {}) if isinstance(schema_item, dict) else {}
            )
            description = item_schema.get("description", key)

            if isinstance(value, dict):
                sub_schema = item_schema.get("items", {})
                translated[description] = self.translate_config_recursive(
                    value, sub_schema
                )
            else:
                translated[description] = value

        return translated
