"""
Web 管理端认证路由。
负责注册认证相关接口，减少 WebAdminServer 中的路由定义体积。
"""

from __future__ import annotations

from typing import Any

from ..payloads.api_response import ApiResponse


def register_auth_routes(
    app, *, auth_enabled: bool, auth_token: str | None, password_getter
):
    """注册认证相关路由。"""
    # 认证路由保持最小闭环：告知是否需要登录 + 使用密码换取临时 token。

    @app.get("/api/auth-info")
    async def get_auth_info():
        """返回是否需要密码认证。"""
        return ApiResponse.success({"auth_required": auth_enabled})

    @app.post("/api/login")
    async def login(credentials: dict[str, Any]):
        """密码登录，返回访问令牌。"""
        if not auth_enabled:
            return ApiResponse.success({"token": "no-auth", "auth_required": False})

        password = password_getter()
        if __import__("secrets").compare_digest(
            credentials.get("password", ""), password
        ):
            return ApiResponse.success({"token": auth_token, "auth_required": True})

        return ApiResponse.error("密码错误", status_code=401)
