"""
Web 管理端事件路由。
负责注册历史事件分页、数据源筛选与重大事件查询接口，减少 WebAdminServer 的路由定义体积。
"""

from __future__ import annotations

import asyncio
import time

from astrbot.api import logger

from ..payloads.api_response import ApiResponse

# 简单的基于内存的轻量级缓存，用来缓存数据源选项，降低分页查询和 sources 查询时的开销。
# 缓存有效期设为 10 秒，数据源不频繁变化但加载很频繁。
_SOURCES_CACHE_LIMIT = 10.0
_sources_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}


def _get_cached_source_options(db, event_type: str | None) -> list[dict[str, str]]:
    """获取缓存的数据源选项，若失效则拉取最新并更新缓存。"""
    now = time.time()
    cache_key = event_type or ""
    if cache_key in _sources_cache:
        t, data = _sources_cache[cache_key]
        if now - t < _SOURCES_CACHE_LIMIT:
            return data
    return None


def _set_cached_source_options(event_type: str | None, data: list[dict[str, str]]):
    """设置数据源选项的缓存。"""
    cache_key = event_type or ""
    _sources_cache[cache_key] = (time.time(), data)


# 为了配合写入操作清除缓存，我们也提供失效函数
def invalidate_sources_cache():
    """手动失效数据源的缓存。"""
    _sources_cache.clear()


def register_events_routes(app, *, disaster_service):
    """注册事件相关路由。"""

    @app.get("/api/events")
    async def get_events_paginated(
        page: int = 1,
        limit: int = 50,
        type: str = "",
        source: str = "",
        min_magnitude: float | None = None,
        magnitude_order: str = "",
        keyword: str = "",
        level_filter: str = "",
    ):
        """分页获取历史事件记录。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "statistics_manager",
            )
            if guard_result is not None:
                return ApiResponse.success(
                    {
                        "events": [],
                        "total": 0,
                        "page": page,
                        "limit": limit,
                        "total_pages": 0,
                        "sources": [],
                        "max_limit": 200,
                    }
                )

            db = disaster_service.statistics_manager.db
            event_type = type if type else None
            # 数据源筛选支持逗号分隔，便于前端一次性组合多个来源条件。
            source_filters = [s.strip() for s in source.split(",") if s.strip()]
            max_limit = 200
            # 在接口层统一收敛分页参数，避免极端查询直接压垮数据库。
            limit = min(max(1, limit), max_limit)
            page = max(1, page)

            normalized_magnitude_order = magnitude_order.lower().strip()
            if normalized_magnitude_order not in {"", "asc", "desc"}:
                normalized_magnitude_order = ""

            normalized_keyword = keyword.strip()
            normalized_level_filter = level_filter.strip()

            # 利用 asyncio.gather 并发查询总数与分页数据，最大化 SQLite I/O 效率
            total, events = await asyncio.gather(
                db.get_events_count(
                    event_type,
                    source_filters,
                    min_magnitude=min_magnitude,
                    keyword=normalized_keyword or None,
                    level_filter=normalized_level_filter or None,
                ),
                db.get_events_paginated(
                    page,
                    limit,
                    event_type,
                    source_filters,
                    min_magnitude=min_magnitude,
                    magnitude_order=normalized_magnitude_order or None,
                    keyword=normalized_keyword or None,
                    level_filter=normalized_level_filter or None,
                ),
            )

            # 气象事件在管理端列表中补充图标地址，便于前端直接展示而不再二次拼接。
            for event in events:
                if not isinstance(event, dict):
                    continue
                if event.get("type") != "weather_alarm":
                    continue

                weather_type_code = str(event.get("weather_type_code") or "").strip()
                if weather_type_code:
                    event["icon_url"] = (
                        f"https://image.nmc.cn/assets/img/alarm/{weather_type_code}.png"
                    )
                else:
                    event["icon_url"] = None
            total_pages = (total + limit - 1) // limit if total > 0 else 0

            # 优先从缓存获取数据源列表
            source_options = _get_cached_source_options(db, event_type)
            if source_options is None:
                source_options = await db.get_event_source_options(event_type)
                _set_cached_source_options(event_type, source_options)

            available_sources = [
                item.get("source_label", "")
                for item in source_options
                if item.get("source_label")
            ]

            return ApiResponse.success(
                {
                    "events": events,
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "total_pages": total_pages,
                    "sources": available_sources,
                    "source_options": source_options,
                    "max_limit": max_limit,
                }
            )
        except Exception as e:
            logger.error(f"[灾害预警] 分页获取事件失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.get("/api/events/sources")
    async def get_event_sources(type: str = ""):
        """获取可筛选的数据源列表。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "statistics_manager",
            )
            if guard_result is not None:
                return ApiResponse.success({"sources": []})

            db = disaster_service.statistics_manager.db
            event_type = type if type else None

            # 优先从缓存获取数据源列表
            source_options = _get_cached_source_options(db, event_type)
            if source_options is None:
                source_options = await db.get_event_source_options(event_type)
                _set_cached_source_options(event_type, source_options)

            sources = [
                item.get("source_label", "")
                for item in source_options
                if item.get("source_label")
            ]
            return ApiResponse.success(
                {"sources": sources, "source_options": source_options}
            )
        except Exception as e:
            logger.error(f"[灾害预警] 获取数据源列表失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.get("/api/events/major")
    async def get_major_events(limit: int = 50):
        """获取重大事件列表。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "statistics_manager",
            )
            if guard_result is not None:
                return ApiResponse.success({"events": []})

            db = disaster_service.statistics_manager.db
            # 负数或零表示“不限制”，但这里仍显式映射为数据库可接受的大整数上限。
            if limit <= 0:
                safe_limit = 9223372036854775807
            else:
                safe_limit = min(max(1, limit), 500)

            events = await db.get_major_events(safe_limit)
            return ApiResponse.success({"events": events})
        except Exception as e:
            logger.error(f"[灾害预警] 获取重大事件失败: {e}")
            return ApiResponse.error(str(e), status_code=500)
