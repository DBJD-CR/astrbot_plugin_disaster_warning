"""
浏览器管理器
负责 Playwright 浏览器实例的生命周期管理和页面对象池
实现高性能的卡片渲染
"""

import asyncio
import os
import tempfile
import time

import aiohttp
from playwright.async_api import Browser, Page, async_playwright

from astrbot.api import logger


class BrowserManager:
    """浏览器管理器 - 单例浏览器 + 页面对象池"""

    def __init__(
        self,
        pool_size: int = 2,
        telemetry=None,
        mode: str = "local",
        server_url: str = "",
    ):
        """
        初始化浏览器管理器

        Args:
            pool_size: 页面池大小，默认 2 个页面
            telemetry: 遥测管理器（可选）
            mode: 运行模式，"local" 或 "remote"
            server_url: 远程 Playwright 服务器地址（mode="remote" 时必填）
        """
        self.pool_size = pool_size
        self._browser: Browser | None = None
        self._playwright = None
        self._context = None  # 保存 context 引用（CDP 模式需要）
        self._page_pool: asyncio.Queue = asyncio.Queue(maxsize=pool_size)
        self._semaphore = asyncio.Semaphore(pool_size)  # 并发控制
        self._page_creation_lock = asyncio.Lock()  # 页面创建锁,防止并发创建超出池大小
        self._init_lock = asyncio.Lock()  # 初始化锁，防止并发初始化
        self._initialized = False
        self._closed = False
        self._telemetry = telemetry
        self._mode = mode
        self._server_url = server_url

    async def initialize(self):
        """初始化浏览器和页面池"""
        async with self._init_lock:
            if self._initialized:
                logger.debug("[灾害预警] 浏览器已初始化，跳过")
                return

            try:
                # 远程模式使用 HTTP API，不需要初始化 Playwright
                if self._mode == "remote":
                    logger.info(
                        f"[灾害预警] 远程模式：使用 browserless HTTP API ({self._server_url})"
                    )
                    self._initialized = True
                    return

                logger.info(f"[灾害预警] 正在启动浏览器（模式：{self._mode}）...")
                start_time = time.time()

                # 启动 Playwright
                self._playwright = await async_playwright().start()

                # 本地模式：启动本地浏览器
                self._browser = await self._playwright.chromium.launch(
                    args=["--no-sandbox", "--disable-setuid-sandbox"]
                )
                logger.info("[灾害预警] 本地浏览器启动成功")

                # 本地模式：直接创建页面池
                await self._initialize_local_page_pool()

                elapsed = time.time() - start_time
                self._initialized = True
                logger.info(
                    f"[灾害预警] 浏览器启动完成，耗时 {elapsed:.2f}秒，页面池大小: {self.pool_size}"
                )

            except Exception as e:
                logger.error(f"[灾害预警] 浏览器初始化失败: {e}")
                # 上报浏览器初始化错误到遥测
                if self._telemetry and self._telemetry.enabled:
                    await self._telemetry.track_error(
                        e, module="core.browser_manager.initialize"
                    )
                # 清理已创建的资源
                await self._cleanup()
                raise

    async def _initialize_local_page_pool(self):
        """初始化本地浏览器的页面池"""
        for i in range(self.pool_size):
            try:
                page = await asyncio.wait_for(
                    self._browser.new_page(
                        viewport={"width": 800, "height": 800}, device_scale_factor=2
                    ),
                    timeout=10.0,
                )
                await self._page_pool.put(page)
                logger.debug(f"[灾害预警] 页面 {i + 1}/{self.pool_size} 已创建")
            except asyncio.TimeoutError:
                logger.error(f"[灾害预警] 创建页面 {i + 1} 超时")
                if i == 0:
                    raise  # 如果第一个页面就失败，抛出异常
                break  # 部分页面创建成功，继续使用
            except Exception as e:
                logger.error(f"[灾害预警] 创建页面 {i + 1} 失败: {e}")
                if i == 0:
                    raise
                break

    async def _initialize_remote_page_pool(self):
        """初始化远程浏览器的页面池（兼容 browserless CDP）"""
        try:
            # browserless CDP：必须使用默认 context
            contexts = self._browser.contexts
            logger.debug(f"[灾害预警] 发现 {len(contexts)} 个现有 context")

            if contexts:
                # 使用第一个 context（browserless 的默认 context）
                self._context = contexts[0]
                logger.debug("[灾害预警] 使用现有 context")
            else:
                # 没有现有 context，创建新的
                logger.debug("[灾害预警] 创建新 context")
                self._context = await asyncio.wait_for(
                    self._browser.new_context(
                        viewport={"width": 800, "height": 800},
                        device_scale_factor=2,
                    ),
                    timeout=15.0,
                )

            # 从 context 创建页面
            for i in range(self.pool_size):
                try:
                    page = await asyncio.wait_for(
                        self._context.new_page(), timeout=10.0
                    )
                    await self._page_pool.put(page)
                    logger.debug(f"[灾害预警] 页面 {i + 1}/{self.pool_size} 已创建")
                except asyncio.TimeoutError:
                    logger.error(f"[灾害预警] 创建页面 {i + 1} 超时")
                    if i == 0:
                        raise
                    break
                except Exception as e:
                    logger.error(f"[灾害预警] 创建页面 {i + 1} 失败: {e}")
                    if i == 0:
                        raise
                    break

            # 检查是否至少有一个页面可用
            if self._page_pool.qsize() == 0:
                raise RuntimeError("无法创建任何可用页面")

            logger.info(
                f"[灾害预警] 远程浏览器页面池初始化完成，可用页面: {self._page_pool.qsize()}"
            )

        except asyncio.TimeoutError:
            logger.error("[灾害预警] 远程浏览器页面池初始化超时")
            raise RuntimeError(
                "远程浏览器页面池初始化超时，请检查网络或增加 browserless 超时设置"
            )
        except Exception as e:
            logger.error(f"[灾害预警] 远程浏览器页面池初始化失败: {e}")
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
        # 远程模式：使用 browserless HTTP API
        if self._mode == "remote":
            if not self._initialized:
                logger.warning("[灾害预警] 浏览器未初始化，尝试初始化...")
                await self.initialize()
            return await self._render_card_via_http(html_content, output_path, selector)

        # 本地模式：使用 Playwright
        if not self._initialized:
            logger.warning("[灾害预警] 浏览器未初始化，尝试初始化...")
            await self.initialize()

        if self._closed:
            logger.error("[灾害预警] 浏览器已关闭，无法渲染")
            return None

        page: Page | None = None
        start_time = time.time()

        acquired_semaphore = False
        try:
            # 并发控制 - 限制同时渲染的数量
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=20.0)
                acquired_semaphore = True
            except asyncio.TimeoutError:
                logger.error("[灾害预警] 等待渲染信号量超时，系统负载过高")
                return None

            try:
                # 本地模式：从池中获取页面
                try:
                    page = await asyncio.wait_for(self._page_pool.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.error("[灾害预警] 从池中获取页面对象超时")
                    return None

                try:
                    # 本地模式：使用 file:// 协议（支持相对路径资源）
                    temp_html = None
                    try:
                        # 创建临时 HTML 文件
                        with tempfile.NamedTemporaryFile(
                            mode="w", suffix=".html", delete=False, encoding="utf-8"
                        ) as f:
                            temp_html = f.name
                            f.write(html_content)

                        # 使用 file:// 协议加载，支持相对路径
                        file_url = f"file://{temp_html}"
                        await page.goto(file_url, wait_until="domcontentloaded")
                    finally:
                        # 清理临时 HTML 文件
                        if temp_html and os.path.exists(temp_html):
                            try:
                                os.unlink(temp_html)
                            except Exception:
                                pass

                    # 等待地图渲染完成标记
                    try:
                        await page.wait_for_selector(
                            ".map-ready", state="attached", timeout=10000
                        )
                        logger.debug("[灾害预警] 地图渲染标记已就绪")
                    except Exception:
                        logger.warning(
                            "[灾害预警] 等待 .map-ready 标记超时，地图可能未完全加载"
                        )
                        # 兜底等待，确保至少能看到部分内容
                        await asyncio.sleep(0.2)

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

                    elapsed = time.time() - start_time

                    if os.path.exists(output_path):
                        logger.info(f"[灾害预警] 卡片渲染成功，耗时 {elapsed:.3f}秒")
                        return output_path
                    else:
                        logger.warning("[灾害预警] 截图未生成文件")
                        return None

                finally:
                    # 本地模式：归还页面到池
                    if page:
                        await self._page_pool.put(page)
            finally:
                # 释放信号量
                if acquired_semaphore:
                    self._semaphore.release()

        except Exception as e:
            logger.error(f"[灾害预警] 卡片渲染失败: {e}")
            # 上报卡片渲染错误到遥测
            if self._telemetry and self._telemetry.enabled:
                await self._telemetry.track_error(
                    e, module="core.browser_manager.render_card"
                )
            # 如果页面损坏，关闭它并恢复页面池（仅本地模式）
            if page:
                try:
                    await page.close()
                    logger.debug("[灾害预警] 已关闭损坏的页面")
                except Exception:
                    pass

                # 恢复页面池
                async with self._page_creation_lock:
                    try:
                        if self._browser and not self._closed:
                            if self._page_pool.qsize() < self.pool_size:
                                new_page = await self._browser.new_page(
                                    viewport={"width": 800, "height": 800},
                                    device_scale_factor=2,
                                )
                                await self._page_pool.put(new_page)
                                logger.debug("[灾害预警] 已重新创建页面")
                    except Exception as recover_err:
                        logger.error(f"[灾害预警] 页面恢复失败: {recover_err}")

            return None

    async def _render_card_via_http(
        self, html_content: str, output_path: str, selector: str
    ) -> str | None:
        """使用 browserless HTTP API 渲染卡片"""
        start_time = time.time()

        # 构建请求 URL
        api_url = self._server_url
        if not api_url.endswith("/"):
            api_url += "/"
        api_url += "screenshot"

        try:
            # 构建请求体 - 使用 browserless screenshot API
            payload = {
                "html": html_content,
                "options": {
                    "type": "png",
                    "omitBackground": True,
                    "fullPage": False,
                },
                "gotoOptions": {
                    "waitUntil": "networkidle2",  # 等待网络几乎空闲（允许2个连接）
                    "timeout": 60000,
                },
                "viewport": {
                    "width": 800,
                    "height": 800,
                    "deviceScaleFactor": 2,
                },
                "waitForTimeout": 3000,  # 额外等待 3 秒，确保地图瓦片加载
            }

            # 如果指定了选择器，使用元素截图
            if selector and selector != ".card":
                payload["selector"] = selector
                # 使用 waitForSelector 确保元素可见
                payload["waitForSelector"] = {
                    "selector": selector,
                    "visible": True,
                    "timeout": 10000,
                }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=90),  # 增加到 90 秒
                ) as response:
                    if response.status == 200:
                        # 保存截图
                        image_data = await response.read()
                        with open(output_path, "wb") as f:
                            f.write(image_data)

                        elapsed = time.time() - start_time
                        logger.info(
                            f"[灾害预警] 卡片渲染成功（HTTP API），耗时 {elapsed:.3f}秒"
                        )
                        return output_path
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"[灾害预警] browserless API 返回错误: {response.status} - {error_text}"
                        )
                        return None

        except asyncio.TimeoutError:
            logger.error("[灾害预警] browserless API 请求超时")
            return None
        except Exception as e:
            logger.error(f"[灾害预警] browserless API 请求失败: {e}")
            if self._telemetry and self._telemetry.enabled:
                await self._telemetry.track_error(
                    e, module="core.browser_manager._render_card_via_http"
                )
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
