"""
WebSocket 重连与离线通知服务。
负责处理连接错误后的重连调度、关键错误判定、离线通知发送与状态清理，
减少 WebSocketManager 中的重连过程式逻辑。
"""

from __future__ import annotations

import asyncio
from typing import Any

from astrbot.api import logger


class WebSocketReconnectService:
    """WebSocket 重连与离线通知服务。"""

    def __init__(self, manager):
        """保存管理器引用，供重连流程读写连接状态。"""
        self.manager = manager

    def handle_connection_error(
        self, name: str, uri: str, headers: dict | None, error: Exception
    ) -> None:
        """统一处理连接错误。"""
        # 一旦连接异常，先清理运行时连接句柄与心跳任务，避免旧状态残留影响下一次重连。
        self.manager.connections.pop(name, None)
        if name in self.manager.heartbeat_tasks:
            self.manager.heartbeat_tasks[name].cancel()
            self.manager.heartbeat_tasks.pop(name, None)

        connection_info = self.manager.connection_info.get(name, {})
        offline_since = connection_info.get("offline_since")
        if offline_since is None:
            offline_since = asyncio.get_running_loop().time()
            connection_info["offline_since"] = offline_since
            self.manager.connection_info[name] = connection_info

        if not self.manager.running:
            return

        # 证书配置错误通常不是暂时性故障，继续重连意义不大，直接停止并通知上层。
        error_msg = str(error).lower()
        if "ssl" in error_msg or "certificate" in error_msg:
            logger.warning(f"[灾害预警] {name} 遇到 SSL 配置错误，停止重连: {error}")
            self.emit_offline_notification(
                connection_name=name,
                stage="stop",
                reason=f"SSL/证书错误: {error}",
                retry_count=self.manager.connection_retry_counts.get(name, 0),
                fallback_count=self.manager.fallback_retry_counts.get(name, 0),
            )
            return

        # 关键错误可跳过短时重试，直接进入更保守的兜底阶段。
        force_fallback = self.is_critical_error(error)
        if force_fallback:
            logger.warning(
                f"[灾害预警] {name} 遇到关键错误，将直接进入兜底重连阶段: {error}"
            )

        existing_task = self.manager.reconnect_tasks.get(name)
        if existing_task and not existing_task.done():
            logger.debug(f"[灾害预警] {name} 已有正在运行的重连任务，跳过重复创建")
            return

        reconnect_task = asyncio.create_task(
            self.schedule_reconnect(
                name, uri, headers, connection_info, force_fallback=force_fallback
            ),
            name=f"dw_reconnect_{name}",
        )
        self.manager.reconnect_tasks[name] = reconnect_task

    def is_critical_error(self, error: Exception) -> bool:
        """判断是否为需要直接进入兜底重连的关键错误。"""
        error_msg = str(error).lower()
        if "401" in error_msg or "403" in error_msg:
            return True
        if "协议错误关闭（不重连）" in error_msg:
            return True
        return False

    async def schedule_reconnect(
        self,
        name: str,
        uri: str,
        headers: dict | None = None,
        connection_info: dict[str, Any] | None = None,
        force_fallback: bool = False,
    ) -> None:
        """计划重连。"""
        if not self.manager.running:
            return

        try:
            connection_info = connection_info or {}
            offline_since = connection_info.get("offline_since")
            if offline_since is None:
                offline_since = asyncio.get_running_loop().time()
                connection_info["offline_since"] = offline_since
                self.manager.connection_info[name] = connection_info

            # 重连策略分成“短时重试 + 长周期兜底重试”两层，兼顾快速恢复与长期稳定性。
            max_retries = self.manager.config.get("max_reconnect_retries", 3)
            reconnect_interval = self.manager.config.get("reconnect_interval", 10)
            fallback_enabled = self.manager.config.get("fallback_retry_enabled", True)
            fallback_interval = self.manager.config.get("fallback_retry_interval", 1800)
            fallback_max_count = self.manager.config.get("fallback_retry_max_count", -1)

            # 短时重试计数与兜底重试计数分开维护，便于日志展示和策略判断。
            current_retry = self.manager.connection_retry_counts.get(name, 0)
            current_fallback = self.manager.fallback_retry_counts.get(name, 0)
            has_backup = connection_info and connection_info.get("backup_url")
            total_max_retries = max_retries * 2 if has_backup else max_retries

            if force_fallback:
                current_retry = total_max_retries
                self.manager.connection_retry_counts[name] = total_max_retries

            if current_retry >= total_max_retries:
                if not fallback_enabled:
                    logger.error(
                        f"[灾害预警] {name} 重连失败，已达到最大重试次数 ({total_max_retries})，停止重连"
                    )
                    self.emit_offline_notification(
                        connection_name=name,
                        stage="stop",
                        reason="短时重连次数已达上限且未启用兜底重试",
                        retry_count=current_retry,
                        fallback_count=current_fallback,
                    )
                    return

                if fallback_max_count != -1 and current_fallback >= fallback_max_count:
                    logger.error(
                        f"[灾害预警] {name} 兜底重试失败，已达到最大兜底重试次数 ({fallback_max_count})，停止重连"
                    )
                    self.emit_offline_notification(
                        connection_name=name,
                        stage="stop",
                        reason="兜底重试次数已达上限",
                        retry_count=current_retry,
                        fallback_count=current_fallback,
                    )
                    return

                self.manager.fallback_retry_counts[name] = current_fallback + 1
                fallback_display = current_fallback + 1
                fallback_max_display = (
                    "无限" if fallback_max_count == -1 else str(fallback_max_count)
                )

                if fallback_interval < 60:
                    fallback_interval_display = f"{fallback_interval} 秒"
                else:
                    minutes = fallback_interval // 60
                    seconds = fallback_interval % 60
                    if seconds == 0:
                        fallback_interval_display = f"{minutes} 分钟"
                    else:
                        fallback_interval_display = f"{minutes} 分钟 {seconds} 秒"

                logger.warning(
                    f"[灾害预警] {name} 短时重连失败，将在 {fallback_interval_display} 后进行兜底重试 "
                    f"({fallback_display}/{fallback_max_display})"
                )
                self.emit_offline_notification(
                    connection_name=name,
                    stage="fallback",
                    reason="短时重连失败，进入兜底重试",
                    next_retry_in=fallback_interval_display,
                    retry_count=current_retry,
                    fallback_count=self.manager.fallback_retry_counts.get(name, 0),
                )

                await asyncio.sleep(fallback_interval)
                if not self.manager.running:
                    return

                self.manager.reconnect_tasks.pop(name, None)
                await self.manager.connect(
                    name,
                    uri,
                    headers,
                    is_retry=True,
                    connection_info=connection_info,
                )
                return

            # 若配置了备用地址，则在主地址短时重试耗尽后切到备用地址继续尝试。
            target_uri = uri
            server_type = "主服务器"
            if has_backup and current_retry >= max_retries:
                backup_url = connection_info.get("backup_url")
                if backup_url:
                    target_uri = backup_url
                    server_type = "备用服务器"

            display_retry = current_retry + 1
            if server_type == "备用服务器":
                display_retry = current_retry - max_retries + 1

            logger.info(
                f"[灾害预警] {name} 将在 {reconnect_interval} 秒后尝试重连{server_type} ({display_retry}/{max_retries})"
            )

            offline_elapsed = asyncio.get_running_loop().time() - offline_since
            short_retry_notify_threshold = reconnect_interval * 3
            short_retry_notified = bool(
                connection_info.get("short_retry_notified", False)
            )
            if (
                short_retry_notify_threshold > 0
                and offline_elapsed >= short_retry_notify_threshold
                and not short_retry_notified
            ):
                self.emit_offline_notification(
                    connection_name=name,
                    stage="short_retry",
                    reason=(
                        f"离线已持续至少 {int(short_retry_notify_threshold)} 秒，"
                        "仍处于短时重连阶段"
                    ),
                    next_retry_in=f"{reconnect_interval} 秒",
                    retry_count=current_retry,
                    fallback_count=current_fallback,
                )
                connection_info["short_retry_notified"] = True
                self.manager.connection_info[name] = connection_info

            await asyncio.sleep(reconnect_interval)
            if not self.manager.running:
                return

            self.manager.reconnect_tasks.pop(name, None)
            await self.manager.connect(
                name,
                target_uri,
                headers,
                is_retry=True,
                connection_info=connection_info,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[灾害预警] 重连调度失败 {name}: {e}")

    def emit_offline_notification(
        self,
        connection_name: str,
        stage: str,
        reason: str,
        next_retry_in: str | None = None,
        retry_count: int | None = None,
        fallback_count: int | None = None,
    ) -> None:
        """触发离线通知回调（异步安全）。"""
        if not self.manager._offline_notify_callback:
            return

        # 回调载荷尽量保持扁平，便于通知层直接格式化输出。
        info = self.manager.connection_info.get(connection_name, {})
        payload = {
            "connection_name": connection_name,
            "data_source": info.get("data_source")
            or info.get("connection_name")
            or "unknown",
            "stage": stage,
            "reason": reason,
            "next_retry_in": next_retry_in,
            "retry_count": retry_count,
            "fallback_count": fallback_count,
        }
        asyncio.create_task(self.manager._offline_notify_callback(payload))
