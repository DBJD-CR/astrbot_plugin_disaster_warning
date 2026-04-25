"""
Web 管理端配置路由。
负责注册配置 Schema、完整配置读取与更新接口，减少 WebAdminServer 的路由定义体积。
"""

from __future__ import annotations

import json
import os
import traceback
from typing import Any

from astrbot.api import logger

from ....services.config.config_validation_service import ConfigValidator
from ..payloads.api_response import ApiResponse


def register_config_routes(app, *, config):
    """注册配置相关路由。"""

    @app.get("/api/config-schema")
    async def get_config_schema():
        """获取配置结构定义。"""
        try:
            schema_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(
                            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                        )
                    ),
                    "_conf_schema.json",
                )
            )
            if os.path.exists(schema_path):
                # 配置结构定义单独放在文件中，便于前端动态渲染配置表单。
                with open(schema_path, encoding="utf-8") as f:
                    return ApiResponse.success(json.load(f))
            return ApiResponse.error(
                f"未找到配置结构定义文件: {schema_path}",
                status_code=404,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 获取配置结构定义失败: {e}, path: {schema_path}")
            return ApiResponse.error(
                f"{str(e)}, path: {schema_path}, trace: {traceback.format_exc()}",
                status_code=500,
            )

    @app.get("/api/full-config")
    async def get_full_config():
        """获取完整配置。"""
        try:
            full = dict(config)
            # 即便是完整配置读取接口，也要显式屏蔽管理端密码字段。
            if "web_admin" in full and isinstance(full["web_admin"], dict):
                full["web_admin"] = {
                    k: v for k, v in full["web_admin"].items() if k != "password"
                }
            return ApiResponse.success(full)
        except Exception as e:
            logger.error(f"[灾害预警] 获取完整配置失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.post("/api/full-config")
    async def update_full_config(config_data: dict[str, Any]):
        """更新完整配置。"""
        try:
            current_config_dict = dict(config)

            def deep_update(target, updates):
                # 递归合并前端提交的局部修改，避免未提交字段被整段覆盖丢失。
                for key, value in updates.items():
                    if (
                        isinstance(value, dict)
                        and key in target
                        and isinstance(target[key], dict)
                    ):
                        deep_update(target[key], value)
                    else:
                        target[key] = value

            deep_update(current_config_dict, config_data)
            # 只有通过校验后的配置才会回写到运行时对象与配置文件。
            validated_config = ConfigValidator.validate(current_config_dict)

            for key, value in validated_config.items():
                config[key] = value

            if hasattr(config, "save_config"):
                config.save_config()

            return ApiResponse.success({"success": True, "message": "配置已校验并保存"})
        except Exception as e:
            logger.error(f"[灾害预警] 保存配置失败: {e}")
            return ApiResponse.error(str(e), status_code=500)
