"""
消息资源清理服务。
负责关闭浏览器与远程媒体会话，以及清理旧的临时图像记录，
减少 MessagePushManager 中的资源生命周期管理职责。
"""

from __future__ import annotations

import glob
import os
import time

from astrbot.api import logger

from ...services.config.config_service import ConfigAccessor


class MessageResourceCleanupService:
    """消息资源清理服务。"""

    def __init__(self, manager):
        self.manager = manager
        self.config_accessor = ConfigAccessor(manager.config)

    async def cleanup_browser(self) -> None:
        """清理浏览器与远程媒体抓取资源。"""
        try:
            # 先关远程媒体 session，避免退出阶段仍有残留 HTTP 连接未释放。
            await self.manager.close_remote_media_session()
            logger.debug("[灾害预警] 远程媒体 Session 已关闭")
        except Exception as e:
            logger.error(f"[灾害预警] 关闭远程媒体 Session 失败: {e}")

        if self.manager.browser_manager:
            try:
                await self.manager.browser_manager.close()
                logger.debug("[灾害预警] 浏览器管理器已关闭")
            except Exception as e:
                logger.error(f"[灾害预警] 关闭浏览器管理器失败: {e}")

    def cleanup_old_records(self) -> None:
        """清理旧记录与临时文件。"""
        # 去重状态与磁盘临时图像都属于长期运行时的累积数据，需要定期收缩。
        self.manager.deduplicator.cleanup_old_events()

        try:
            pattern = os.path.join(self.manager.temp_dir, "*.png")
            files = glob.glob(pattern)
            files.sort(key=os.path.getmtime)

            max_files = self.config_accessor.message_format_config().get(
                "max_temp_images", 256
            )
            if len(files) > max_files:
                to_delete = files[: len(files) - max_files]
                for file_path in to_delete:
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                logger.info(
                    f"[灾害预警] 临时文件过多，已清理 {len(to_delete)} 个旧文件"
                )
                files = files[len(to_delete) :]

            # 额外再按时间清理 3 小时前的图片，减少 temp 目录长期堆积。
            expire_time = time.time() - 10800
            for file_path in files:
                try:
                    if os.path.getmtime(file_path) < expire_time:
                        os.remove(file_path)
                        logger.debug(
                            f"[灾害预警] 已清理过期临时图片: {os.path.basename(file_path)}"
                        )
                except Exception as e:
                    logger.warning(f"[灾害预警] 清理文件失败 {file_path}: {e}")

        except Exception as e:
            logger.error(f"[灾害预警] 清理临时文件夹失败: {e}")
