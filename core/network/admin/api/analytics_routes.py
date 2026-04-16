"""
Web 管理端统计分析路由。
负责注册地震可视化、趋势与热力图接口，减少 WebAdminServer 的路由定义体积。
"""

from __future__ import annotations

from datetime import datetime

from astrbot.api import logger

from ....support.event_view_factory import EventViewFactory
from ..api_response import ApiResponse


def register_analytics_routes(app, *, disaster_service):
    """注册统计分析相关路由。"""

    @app.get("/api/earthquakes")
    async def get_earthquakes():
        """获取地震数据用于 3D 地球可视化。"""
        try:
            if not disaster_service or not disaster_service.statistics_manager:
                return ApiResponse.success(
                    {"earthquakes": [], "timestamp": datetime.now().isoformat()}
                )

            stats = disaster_service.statistics_manager.stats
            recent_pushes = stats.get("recent_pushes", [])
            # 统一复用事件视图工厂，把统计记录转换为前端图形化可直接消费的地震视图。
            earthquakes = EventViewFactory.build_recent_earthquake_views(recent_pushes)

            return ApiResponse.success(
                {
                    "earthquakes": earthquakes,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"[灾害预警] 获取地震数据失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.get("/api/trend")
    async def get_trend(hours: int = 24):
        """获取预警趋势数据。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "statistics_manager",
            )
            if guard_result is not None:
                return guard_result

            if hours not in [24, 168]:
                hours = 24

            trend_data = disaster_service.statistics_manager.get_trend_data(hours)
            return ApiResponse.success(
                {
                    "data": trend_data,
                    "hours": hours,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"[灾害预警] 获取趋势数据失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.get("/api/heatmap")
    async def get_heatmap(days: int = 180, year: int = None):
        """获取日历热力图数据。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "statistics_manager",
            )
            if guard_result is not None:
                return guard_result

            if year:
                heatmap_data = disaster_service.statistics_manager.get_heatmap_data(
                    days=0,
                    year=year,
                )
            else:
                if days < 90:
                    days = 90
                elif days > 365:
                    days = 365

                heatmap_data = disaster_service.statistics_manager.get_heatmap_data(
                    days=days
                )

            return ApiResponse.success(
                {
                    "data": heatmap_data,
                    "days": days,
                    "year": year,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"[灾害预警] 获取热力图数据失败: {e}")
            return ApiResponse.error(str(e), status_code=500)
