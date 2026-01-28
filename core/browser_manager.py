"""
浏览器管理器
负责 Playwright 浏览器实例的生命周期管理和页面对象池
实现高性能的卡片渲染
"""

import asyncio
import os
import tempfile
import time

from playwright.async_api import Browser, Page, async_playwright

from astrbot.api import logger


class BrowserManager:
    """浏览器管理器 - 单例浏览器 + 页面对象池"""

    def __init__(self, pool_size: int = 2, telemetry=None):
        """
        初始化浏览器管理器

        Args:
            pool_size: 页面池大小，默认 2 个页面
            telemetry: 遥测管理器（可选）
        """
        self.pool_size = pool_size
        self._browser: Browser | None = None
        self._playwright = None
        self._page_pool: asyncio.Queue = asyncio.Queue(maxsize=pool_size)
        self._semaphore = asyncio.Semaphore(pool_size)  # 并发控制
        self._initialized = False
        self._closed = False
        self._telemetry = telemetry

    async def initialize(self):
        """初始化浏览器和页面池"""
        if self._initialized:
            logger.debug("[灾害预警] 浏览器已初始化，跳过")
            return

        try:
            logger.info("[灾害预警] 正在启动浏览器...")
            start_time = time.time()

            # 启动 Playwright
            self._playwright = await async_playwright().start()

            # 启动浏览器
            self._browser = await self._playwright.chromium.launch(
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )

            # 预创建页面对象池
            for i in range(self.pool_size):
                page = await self._browser.new_page(
                    viewport={"width": 800, "height": 800}, device_scale_factor=2
                )
                await self._page_pool.put(page)
                logger.debug(f"[灾害预警] 页面 {i + 1}/{self.pool_size} 已创建")

            elapsed = time.time() - start_time
            self._initialized = True
            logger.info(
                f"[灾害预警] 浏览器启动完成，耗时 {elapsed:.2f}秒，页面池大小: {self.pool_size}"
            )

        except Exception as e:
            logger.error(f"[灾害预警] 浏览器初始化失败: {e}")
            # 上报浏览器初始化错误到遥测
            if self._telemetry and self._telemetry.enabled:
                await self._telemetry.track_error(e, module="core.browser_manager.initialize")
            # 清理已创建的资源
            await self._cleanup()
            raise

    async def render_card(
        self,
        html_content: str,
        output_path: str,
        selector: str = "#card-wrapper",
        wait_until: str = "domcontentloaded",
    ) -> str | None:
        """
        渲染 HTML 卡片为图片

        Args:
            html_content: HTML 内容
            output_path: 输出图片路径
            selector: 卡片元素选择器
            wait_until: 等待策略 ('load', 'domcontentloaded', 'networkidle')

        Returns:
            成功返回图片路径,失败返回 None
        """
        if not self._initialized:
            logger.warning("[灾害预警] 浏览器未初始化，尝试初始化...")
            await self.initialize()

        if self._closed:
            logger.error("[灾害预警] 浏览器已关闭，无法渲染")
            return None

        page: Page | None = None
        start_time = time.time()

        try:
            # 并发控制 - 限制同时渲染的数量
            async with self._semaphore:
                # 从池中获取页面
                page = await self._page_pool.get()

                try:
                    # 将 HTML 保存为临时文件，以支持相对路径加载本地资源

                    temp_html = None
                    try:
                        # 创建临时 HTML 文件
                        with tempfile.NamedTemporaryFile(
                            mode="w", suffix=".html", delete=False, encoding="utf-8"
                        ) as f:
                            f.write(html_content)
                            temp_html = f.name

                        # 使用 file:// 协议加载，支持相对路径
                        file_url = f"file://{temp_html}"
                        await page.goto(file_url, wait_until="networkidle")

                        # 等待地图渲染完成标记
                        try:
                            await page.wait_for_selector(
                                ".map-ready", state="attached", timeout=3000
                            )
                            logger.debug("[灾害预警] 地图渲染标记已就绪")
                        except Exception:
                            logger.debug("[灾害预警] 未找到 .map-ready 标记")

                        # 额外等待地图瓦片加载（关键！）
                        await asyncio.sleep(0.5)

                        # 等待卡片元素可见
                        try:
                            await page.wait_for_selector(
                                selector, state="visible", timeout=2000
                            )
                        except Exception:
                            # 兜底：尝试找常见的类名
                            logger.debug(
                                f"[灾害预警] 选择器 {selector} 未找到，尝试备用选择器"
                            )
                            selector = ".quake-card"
                            await page.wait_for_selector(
                                selector, state="visible", timeout=1000
                            )

                        # 定位卡片元素
                        card = page.locator(selector)

                        # 截图：只截取元素，背景透明
                        await card.screenshot(path=output_path, omit_background=True)

                    finally:
                        # 清理临时 HTML 文件
                        if temp_html and os.path.exists(temp_html):
                            try:
                                os.unlink(temp_html)
                            except Exception:
                                pass

                    elapsed = time.time() - start_time

                    if os.path.exists(output_path):
                        logger.info(f"[灾害预警] 卡片渲染成功，耗时 {elapsed:.3f}秒")
                        return output_path
                    else:
                        logger.warning("[灾害预警] 截图未生成文件")
                        return None

                finally:
                    # 归还页面到池中
                    if page:
                        await self._page_pool.put(page)

        except Exception as e:
            logger.error(f"[灾害预警] 卡片渲染失败: {e}")
            # 上报卡片渲染错误到遥测
            if self._telemetry and self._telemetry.enabled:
                await self._telemetry.track_error(e, module="core.browser_manager.render_card")
            # 如果页面损坏，尝试重新创建一个新页面
            if page:
                try:
                    await page.close()
                    logger.debug("[灾害预警] 已关闭损坏的页面")
                except Exception:
                    pass

                # 创建新页面并放回池中
                try:
                    if self._browser and not self._closed:
                        new_page = await self._browser.new_page(
                            viewport={"width": 800, "height": 800},
                            device_scale_factor=2,
                        )
                        await self._page_pool.put(new_page)
                        logger.debug("[灾害预警] 已重新创建页面")
                except Exception as recover_err:
                    logger.error(f"[灾害预警] 页面恢复失败: {recover_err}")

            return None

    async def close(self):
        """关闭浏览器管理器"""
        if self._closed:
            logger.debug("[灾害预警] 浏览器已关闭，跳过")
            return

        logger.info("[灾害预警] 正在关闭浏览器...")
        self._closed = True

        await self._cleanup()

        logger.info("[灾害预警] 浏览器已关闭")

    async def _cleanup(self):
        """清理资源 - 确保每个步骤独立执行,即使前面失败也继续后续清理"""
        cleanup_errors = []

        # 步骤 1: 关闭页面池中的所有页面
        try:
            while not self._page_pool.empty():
                try:
                    page = self._page_pool.get_nowait()
                    await page.close()
                except Exception as e:
                    cleanup_errors.append(f"关闭页面失败: {e}")
                    logger.debug(f"[灾害预警] 关闭页面失败: {e}")
        except Exception as e:
            cleanup_errors.append(f"清理页面池失败: {e}")
            logger.warning(f"[灾害预警] 清理页面池时发生异常: {e}")

        # 步骤 2: 关闭浏览器
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
        except Exception as e:
            cleanup_errors.append(f"关闭浏览器失败: {e}")
            logger.warning(f"[灾害预警] 关闭浏览器失败: {e}")
            # 即使关闭失败,也强制置空引用,防止后续误用
            self._browser = None

        # 步骤 3: 停止 Playwright
        try:
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
        except Exception as e:
            cleanup_errors.append(f"停止 Playwright 失败: {e}")
            logger.warning(f"[灾害预警] 停止 Playwright 失败: {e}")
            # 即使停止失败,也强制置空引用
            self._playwright = None

        # 标记为未初始化
        self._initialized = False

        # 如果有清理错误,记录汇总日志
        if cleanup_errors:
            logger.warning(
                f"[灾害预警] 资源清理过程中遇到 {len(cleanup_errors)} 个错误"
            )

    def __del__(self):
        """析构函数 - 确保资源释放"""
        if self._browser or self._playwright:
            logger.warning(
                "[灾害预警] 检测到未正常关闭的浏览器资源，这可能导致进程泄漏"
            )
