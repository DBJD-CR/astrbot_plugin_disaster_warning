"""
运行态数据与测试接口路由。
承接气象查询、模拟参数、模拟推送与地理定位接口，
进一步缩减 WebAdminServer 的内联路由规模。
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from astrbot.api import logger

from .....core.support.simulation_service import (
    build_earthquake_simulation,
    get_simulation_params,
    resolve_target_session,
)
from .....core.support.weather_query_service import query_weather_alarm_data
from .....utils.geolocation import fetch_location_from_ip
from ..api_response import ApiResponse


def register_runtime_routes(app, disaster_service, config: dict[str, Any]):
    """注册运行态查询与模拟接口。"""

    @app.get("/api/weather/query")
    async def query_weather_alarm(
        keyword: str = "",
        optional_a: str = "",
        optional_b: str = "",
    ):
        """查询气象预警（与 /气象预警查询 逻辑保持一致）。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "statistics_manager",
            )
            if guard_result is not None:
                return guard_result

            db = disaster_service.statistics_manager.db
            query_result = await query_weather_alarm_data(
                db,
                keyword,
                optional_a or None,
                optional_b or None,
            )
            return ApiResponse.success(query_result)
        except Exception as e:
            logger.error(f"[灾害预警] Web端查询气象预警失败: {e}")
            return ApiResponse.error(str(e), status_code=500, success=False)

    @app.get("/api/simulation-params")
    async def get_simulation_params_api():
        """获取模拟预警可用参数选项。"""
        try:
            return ApiResponse.success(get_simulation_params(config))
        except Exception as e:
            logger.error(f"[灾害预警] 获取模拟参数失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.post("/api/simulate")
    async def simulate_disaster(simulation_data: dict[str, Any]):
        """模拟灾害预警（当前支持地震）。"""
        try:
            # 模拟接口是管理端运维工具，不依赖真实上游数据源，但仍要求主服务已就绪。
            if not disaster_service:
                return ApiResponse.error("服务未初始化", status_code=503)

            target_session = simulation_data.get("target_session", "")
            disaster_type = simulation_data.get("disaster_type", "earthquake")
            test_type = simulation_data.get("test_type", "cea_fanstudio")
            custom_params = simulation_data.get("custom_params", {})

            if disaster_type != "earthquake":
                return ApiResponse.error(
                    f"暂不支持 {disaster_type} 类型的模拟，仅支持 earthquake",
                    status_code=400,
                )

            final_target_session = resolve_target_session(config, target_session)
            if not final_target_session:
                return ApiResponse.error("未配置目标会话", status_code=400)

            lat = float(custom_params.get("latitude", 39.9))
            lon = float(custom_params.get("longitude", 116.4))
            magnitude = float(custom_params.get("magnitude", 5.5))
            depth = float(custom_params.get("depth", 10.0))
            source = custom_params.get("source", test_type)

            manager = disaster_service.message_manager
            try:
                simulation_result = build_earthquake_simulation(
                    manager,
                    lat=lat,
                    lon=lon,
                    magnitude=magnitude,
                    depth=depth,
                    source=source,
                )
            except ValueError as ve:
                return ApiResponse.error(str(ve), status_code=400)

            if simulation_result.global_pass and simulation_result.local_pass:
                logger.info("[灾害预警] 开始构建模拟预警消息...")
                # 模拟推送复用真实消息构建与发送链路，确保测试结果尽量贴近线上行为。
                msg_chain = await manager.build_message_async(
                    simulation_result.disaster_event
                )
                await manager.send_message(final_target_session, msg_chain)
                logger.info(
                    f"[灾害预警] ✅ 模拟事件已成功推送到 {final_target_session}"
                )
                simulation_result.report_lines.append(
                    f"\n✅ 消息已发送到: {final_target_session}"
                )
                return ApiResponse.success(
                    {
                        "success": True,
                        "message": "\n".join(simulation_result.report_lines),
                    }
                )

            simulation_result.report_lines.append("\n⛔ 结论: 该事件不会触发预警推送。")
            return ApiResponse.success(
                {
                    "success": False,
                    "message": "\n".join(simulation_result.report_lines),
                }
            )

        except Exception as e:
            logger.error(f"[灾害预警] 模拟推送失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.get("/api/geolocate")
    async def get_geolocation(request: Request):
        """获取客户端 IP 地理位置信息。"""
        try:
            client_ip = request.client.host if request.client else None
            location_data = await fetch_location_from_ip(ip=client_ip)
            return ApiResponse.success(
                {
                    "success": True,
                    "data": {
                        "latitude": location_data.get("latitude"),
                        "longitude": location_data.get("longitude"),
                        "city": location_data.get("city_zh", ""),
                        "province": location_data.get("province_name_zh", ""),
                        "country": location_data.get("country_name_zh", ""),
                        "ip": location_data.get("ip", ""),
                    },
                }
            )
        except Exception as e:
            logger.error(f"[灾害预警] IP地理定位失败: {e}")
            return ApiResponse.error(
                f"获取地理位置失败: {str(e)}", status_code=500, success=False
            )
