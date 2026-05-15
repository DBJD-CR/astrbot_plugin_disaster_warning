"""
数据源健康探测器。
负责 Web 管理端的数据源主机映射、TCP 延迟探测与后台缓存刷新，减少 WebAdminServer 的职责聚合。
"""

from __future__ import annotations

import asyncio
from typing import Any

from astrbot.api import logger


class SourceHealthMonitor:
    """数据源健康探测器。"""

    HOST_MAP: dict[str, str] = {
        "fan_studio_all": "ws.fanstudio.tech",
        "p2p_main": "api.p2pquake.net",
        "wolfx_all": "ws-api.wolfx.jp",
        "global_quake": "gqm.aloys23.link",
    }

    DISPLAY_MAP: dict[str, str] = {
        "fan_studio_all": "FAN Studio",
        "p2p_main": "P2P地震情報",
        "wolfx_all": "Wolfx",
        "global_quake": "Global Quake",
    }

    def __init__(self, latency_cache: dict[str, float | None] | None = None):
        """初始化延迟缓存容器。"""
        self.latency_cache = latency_cache if latency_cache is not None else {}

    def get_expected_data_sources(self) -> dict[str, str]:
        """返回管理端面板预期展示的数据源列表。"""
        return dict(self.DISPLAY_MAP)

    def get_data_source_host(self, source_name: str) -> str | None:
        """获取指定数据源对应的探测主机名。"""
        return self.HOST_MAP.get(source_name)

    async def ping_host(
        self, host: str, port: int = 443, timeout: float = 3.0
    ) -> float | None:
        """使用 TCP 连接测试主机延迟。"""
        try:
            # 这里采用 TCP 建连近似测延迟，不依赖 ICMP，跨平台更稳定。
            start_time = asyncio.get_running_loop().time()
            future = asyncio.open_connection(host, port)
            _reader, writer = await asyncio.wait_for(future, timeout=timeout)
            end_time = asyncio.get_running_loop().time()

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

            return (end_time - start_time) * 1000
        except (asyncio.TimeoutError, OSError):
            return None
        except Exception as e:
            logger.error(
                "[灾害预警] TCP 延迟探测发生非预期异常，主机为 %s，端口为 %s，错误为 %s",
                host,
                port,
                e,
                exc_info=True,
            )
            return None

    async def run_background_ping_loop(self, interval_seconds: float = 30.0):
        """后台定期更新延迟缓存。"""
        logger.debug("[灾害预警] 启动后台延迟检测任务")
        ping_failures: dict[str, int] = {}

        while True:
            try:
                # 每轮都根据当前预期数据源重新构造探测任务，便于后续扩展动态来源表。
                expected_sources = self.get_expected_data_sources()
                ping_tasks: dict[str, Any] = {}

                for source_name in expected_sources.keys():
                    host = self.get_data_source_host(source_name)
                    if host:
                        ping_tasks[source_name] = self.ping_host(
                            host, port=443, timeout=2.0
                        )

                if ping_tasks:
                    results = await asyncio.gather(
                        *ping_tasks.values(), return_exceptions=True
                    )
                    for source_name, result in zip(ping_tasks.keys(), results):
                        if isinstance(result, Exception) or result is None:
                            ping_failures[source_name] = (
                                ping_failures.get(source_name, 0) + 1
                            )
                            # 连续失败 3 次后才把缓存标记为 None，避免偶发抖动导致前端频繁闪烁。
                            if ping_failures[source_name] >= 3:
                                self.latency_cache[source_name] = None
                        else:
                            ping_failures[source_name] = 0
                            self.latency_cache[source_name] = result

                await asyncio.sleep(interval_seconds)

            except asyncio.CancelledError:
                logger.info("[灾害预警] 后台延迟检测任务已停止")
                break
            except Exception as e:
                logger.error(f"[灾害预警] 后台延迟检测出错: {e}")
                await asyncio.sleep(interval_seconds)
