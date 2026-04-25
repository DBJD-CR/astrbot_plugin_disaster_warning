"""
灾害预警插件 Web 管理服务器。
负责创建管理端宿主应用，并装配路由、实时广播、健康探测与静态页面入口。
"""

import asyncio
import os
import secrets
from typing import Any

from astrbot.api import logger

from .....utils.geolocation import close_geoip_session
from ....services.config.config_service import ConfigAccessor
from ...monitoring.source_health_monitor import SourceHealthMonitor
from ...websocket.websocket_hub import WebSocketHub
from ..payloads.api_response import ApiResponse
from ..payloads.config_payload_builder import ConfigPayloadBuilder
from ..payloads.connections_payload_builder import ConnectionsPayloadBuilder
from ..payloads.realtime_payload_builder import RealtimePayloadBuilder
from .web_server_runtime_service import WebServerRuntimeService

try:
    import uvicorn
    from fastapi import FastAPI, Request, WebSocket
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logger.warning(
        "[灾害预警] FastAPI 未安装，Web 管理端功能不可用。请运行: pip install fastapi uvicorn"
    )


class WebAdminServer:
    """Web 管理端服务器。"""

    def __init__(self, disaster_service, config: dict[str, Any]):
        """初始化管理端宿主，并装配运行时依赖。"""
        # WebAdminServer 现在主要承担宿主和装配入口职责，
        # 具体的路由注册、WebSocket 广播与实时数据拼装已拆给独立服务/构建器。
        self.disaster_service = disaster_service
        self.config = config
        self.config_accessor = ConfigAccessor(config)
        self.app = None
        self.server = None
        self._server_task = None
        self._broadcast_task = None
        self._ping_task = None
        self._ws_hub = WebSocketHub()
        # 延迟缓存由健康监控器写入，再由连接状态与实时载荷构建器复用。
        self._latency_cache: dict[str, float | None] = {}
        self._source_health_monitor = SourceHealthMonitor(self._latency_cache)
        self._connections_payload_builder = ConnectionsPayloadBuilder(
            disaster_service=self.disaster_service,
            config=self.config,
            latency_cache=self._latency_cache,
        )
        self._config_payload_builder = ConfigPayloadBuilder(self.config)
        self._realtime_payload_builder = RealtimePayloadBuilder(
            disaster_service=self.disaster_service,
            config=self.config,
            latency_cache=self._latency_cache,
        )
        self._auth_enabled = False
        self._auth_token: str | None = None
        self._runtime_service = WebServerRuntimeService(self)

        if not FASTAPI_AVAILABLE:
            return

        self._setup_app()

    def _setup_app(self):
        """配置 FastAPI 应用。"""

        self.app = FastAPI(
            title="灾害预警管理端",
            description="灾害预警插件 Web 管理界面",
            version="1.0.0",
        )

        # 鉴权配置先于路由注册完成，确保中间件与 WebSocket 端点复用同一套运行时状态。
        self._runtime_service.configure_auth()

        @self.app.middleware("http")
        async def auth_middleware(request: Request, call_next):
            """拦截管理端 API 请求并执行令牌鉴权。"""
            if not self._auth_enabled:
                return await call_next(request)
            path = request.url.path
            if path in {"/api/login", "/api/auth-info"}:
                return await call_next(request)
            if not path.startswith("/api"):
                return await call_next(request)
            token = request.query_params.get("token", "")
            if not token:
                auth_header = request.headers.get("Authorization", "")
                auth_parts = auth_header.split(" ", 1)
                token = (
                    auth_parts[1].strip()
                    if len(auth_parts) == 2 and auth_parts[0].lower() == "bearer"
                    else ""
                )
            if not self._auth_token or not secrets.compare_digest(
                token, self._auth_token
            ):
                return ApiResponse.error("未授权，请先登录", status_code=401)
            return await call_next(request)

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self._register_routes()

        admin_dir = os.path.join(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                )
            ),
            "admin",
        )
        if os.path.exists(admin_dir):
            self.app.mount(
                "/", StaticFiles(directory=admin_dir, html=True), name="admin"
            )

    def _register_routes(self):
        """注册 API 路由。"""
        self._runtime_service.register_routes()

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """管理端 WebSocket 实时推送端点。"""
            await self._runtime_service.handle_websocket(websocket)

    async def _send_full_update(self, websocket: WebSocket):
        """向单个客户端发送完整数据更新。"""
        await self._runtime_service.send_full_update(websocket)

    async def _broadcast_data(self):
        """向所有已连接客户端广播数据更新。"""
        await self._runtime_service.broadcast_data()

    async def get_realtime_data(self) -> dict:
        """获取 WebSocket 推送所需的实时数据。"""
        return await self._runtime_service.get_realtime_data()

    def get_expected_data_sources(self) -> dict[str, str]:
        """获取所有支持的数据源列表，不区分当前是否启用。"""
        return self._source_health_monitor.get_expected_data_sources()

    async def _broadcast_loop(self):
        """后台广播循环，作为保底同步机制定期推送快照。"""
        await self._runtime_service.run_broadcast_loop(interval_seconds=30)

    async def notify_event(self, event_data: dict = None):
        """当有新灾害事件时，立即向所有客户端推送事件更新。"""
        await self._runtime_service.notify_event(event_data)

    def _get_data_source_host(self, source_name: str) -> str | None:
        """获取数据源的主机名，供延迟探测使用。"""
        return self._source_health_monitor.get_data_source_host(source_name)

    async def _ping_host(
        self, host: str, port: int = 443, timeout: float = 3.0
    ) -> float | None:
        """使用 TCP 连接测试主机延迟。"""
        return await self._source_health_monitor.ping_host(
            host, port=port, timeout=timeout
        )

    async def _background_ping_loop(self):
        """后台定期更新延迟缓存。"""
        await self._source_health_monitor.run_background_ping_loop(interval_seconds=30)

    async def start(self):
        """启动 Web 服务器。"""
        if not FASTAPI_AVAILABLE:
            logger.error("[灾害预警] 无法启动 Web 管理端: FastAPI 未安装")
            return

        web_config = self.config_accessor.web_admin_config()
        host = web_config.get("host", "0.0.0.0")
        port = web_config.get("port", 8089)

        config = uvicorn.Config(
            self.app, host=host, port=port, log_level="warning", access_log=False
        )
        self.server = uvicorn.Server(config)

        logger.info(f"[灾害预警] Web 管理端已启动: http://{host}:{port}")

        # 服务主循环、广播循环、延迟探测三类任务分开维护，便于停机时逐项回收。
        self._server_task = asyncio.create_task(self.server.serve())
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        self._ping_task = asyncio.create_task(self._background_ping_loop())

    async def stop(self):
        """停止 Web 服务器。"""
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

        # 先关闭管理端前端连接，再继续释放其他外部资源。
        await self._runtime_service.close_all_websockets()

        try:
            await close_geoip_session()
        except Exception as e:
            logger.debug(f"[灾害预警] 关闭 GeoIP 会话时出错: {e}")

        if self.server:
            self.server.should_exit = True
            if self._server_task:
                try:
                    await asyncio.wait_for(self._server_task, timeout=5.0)
                except asyncio.TimeoutError:
                    self._server_task.cancel()
            logger.info("[灾害预警] Web 管理端已停止")
