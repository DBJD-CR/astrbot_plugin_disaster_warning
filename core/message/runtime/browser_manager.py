"""
浏览器管理器。

负责管理浏览器实例、页面池、并发渲染与远程渲染模式切换，
为卡片、地图等图片渲染场景提供统一的浏览器基础设施。
"""

import asyncio
import json
import os
import tempfile
import time

import aiohttp
from playwright.async_api import Browser, Page, async_playwright

from astrbot.api import logger


class BrowserManager:
    """浏览器管理器。"""

    def __init__(
        self,
        pool_size: int = 2,
        telemetry=None,
        mode: str = "local",
        server_url: str = "",
    ):
        """初始化浏览器管理器。"""
        self.pool_size = pool_size
        self._browser: Browser | None = None
        self._playwright = None
        # 远程连接场景下可能需要保留上下文对象引用。
        self._context = None
        self._page_pool: asyncio.Queue = asyncio.Queue(maxsize=pool_size)
        # 信号量用于限制同时渲染数量，页面创建锁与初始化锁用于避免并发竞争。
        self._semaphore = asyncio.Semaphore(pool_size)
        self._page_creation_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._closed = False
        self._telemetry = telemetry
        self._mode = mode
        self._server_url = server_url

    def _truncate_debug_text(self, value, limit: int = 240) -> str:
        """截断浏览器侧日志文本，避免单条日志过长。"""
        text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

    async def _log_page_diagnostics(self, page: Page, *, reason: str) -> None:
        """输出页面级诊断信息，辅助定位资源加载、脚本执行与选择器状态问题。"""
        try:
            diagnostics = await page.evaluate(
                """
                () => {
                    const mapEl = document.querySelector('#map-container');
                    const cardEl = document.querySelector('#card-wrapper') || document.querySelector('.quake-card');
                    const html = document.documentElement;
                    const body = document.body;
                    return {
                        title: document.title || '',
                        readyState: document.readyState,
                        bodyClasses: body ? body.className || '' : '',
                        mapReady: !!document.querySelector('.map-ready'),
                        mapContainerExists: !!mapEl,
                        mapContainerSize: mapEl ? {
                            width: mapEl.clientWidth,
                            height: mapEl.clientHeight,
                        } : null,
                        cardExists: !!cardEl,
                        cardSize: cardEl ? {
                            width: cardEl.clientWidth,
                            height: cardEl.clientHeight,
                        } : null,
                        htmlLength: html ? (html.outerHTML || '').length : 0,
                    };
                }
                """
            )
            logger.warning(
                f"[灾害预警] 页面诊断（{reason}）：当前文档状态为 {diagnostics.get('readyState')}，"
                f"地图就绪标记{'已出现' if diagnostics.get('mapReady') else '尚未出现'}，"
                f"地图容器{'已找到' if diagnostics.get('mapContainerExists') else '未找到'}，"
                f"地图区域尺寸为 {diagnostics.get('mapContainerSize')}，"
                f"卡片容器{'已找到' if diagnostics.get('cardExists') else '未找到'}，"
                f"卡片尺寸为 {diagnostics.get('cardSize')}，"
                f"页面 body 类名为“{self._truncate_debug_text(diagnostics.get('bodyClasses'))}”，"
                f"页面 HTML 长度约为 {diagnostics.get('htmlLength')} 个字符。"
            )
        except Exception as diag_err:
            logger.warning(f"[灾害预警] 页面诊断({reason})失败: {diag_err}")

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
        """把 HTML 内容渲染为图片文件。"""
        # 远程模式直接走 HTTP 渲染接口，本地模式则复用页面池执行截图。
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
        console_messages: list[str] = []
        page_errors: list[str] = []
        request_failures: list[str] = []
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

                    def _record_console(msg):
                        try:
                            location = msg.location or {}
                            entry = (
                                f"[{msg.type}] {self._truncate_debug_text(msg.text)}"
                                f" @ {location.get('url', '')}:{location.get('lineNumber', '')}:{location.get('columnNumber', '')}"
                            )
                            console_messages.append(entry)
                            if msg.type in {"error", "warning"}:
                                logger.warning(f"[灾害预警] 页面控制台{entry}")
                        except Exception as hook_err:
                            logger.debug(f"[灾害预警] 记录控制台日志失败: {hook_err}")

                    def _record_page_error(exc):
                        try:
                            text = self._truncate_debug_text(exc)
                            page_errors.append(text)
                            logger.warning(f"[灾害预警] 页面脚本异常: {text}")
                        except Exception as hook_err:
                            logger.debug(f"[灾害预警] 记录页面脚本异常失败: {hook_err}")

                    def _record_request_failed(req):
                        try:
                            failure = req.failure
                            failure_text = ""
                            if failure:
                                if isinstance(failure, dict):
                                    failure_text = failure.get("errorText", "")
                                else:
                                    failure_text = str(failure)
                            entry = f"{req.method} {req.url} -> {self._truncate_debug_text(failure_text or 'unknown failure')}"
                            request_failures.append(entry)
                            logger.warning(f"[灾害预警] 页面资源请求失败: {entry}")
                        except Exception as hook_err:
                            logger.debug(f"[灾害预警] 记录请求失败失败: {hook_err}")

                    page.on("console", _record_console)
                    page.on("pageerror", _record_page_error)
                    page.on("requestfailed", _record_request_failed)

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

                    # 仅在页面实际包含地图区域时等待地图渲染完成标记。
                    # 地震列表等纯卡片模板并不包含地图容器，如果统一等待 .map-ready，
                    # 会在正常场景下产生误导性的“地图超时”诊断日志。
                    has_map_related_nodes = await page.evaluate("""
                        () => {
                            const selectors = [
                                '.map-ready',
                                '#map',
                                '.map-container',
                                '#map-container',
                                '.leaflet-container'
                            ];
                            return selectors.some((selector) => document.querySelector(selector));
                        }
                    """)
                    if has_map_related_nodes:
                        try:
                            await page.wait_for_selector(
                                ".map-ready", state="attached", timeout=10000
                            )
                            logger.debug("[灾害预警] 地图渲染标记已就绪")
                        except Exception:
                            logger.warning(
                                "[灾害预警] 等待 .map-ready 标记超时，地图可能未完全加载"
                            )
                            if request_failures:
                                logger.warning(
                                    f"[灾害预警] 地图等待超时期间捕获到资源失败: {' | '.join(request_failures[-5:])}"
                                )
                            if page_errors:
                                logger.warning(
                                    f"[灾害预警] 地图等待超时期间捕获到脚本异常: {' | '.join(page_errors[-3:])}"
                                )
                            await self._log_page_diagnostics(
                                page, reason="map-ready-timeout"
                            )
                            # 兜底等待，确保至少能看到部分内容
                            await asyncio.sleep(0.2)

                    # 等待卡片元素可见
                    try:
                        await page.wait_for_selector(
                            selector, state="visible", timeout=2000
                        )
                    except Exception:
                        # 兜底：尝试找常见的类名。该分支在部分模板中属于正常兼容路径，不额外输出诊断日志。
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
                        if request_failures:
                            logger.warning(
                                f"[灾害预警] 卡片渲染虽成功，但捕获到资源请求失败: {' | '.join(request_failures[-5:])}"
                            )
                        if page_errors:
                            logger.warning(
                                f"[灾害预警] 卡片渲染虽成功，但捕获到页面脚本异常: {' | '.join(page_errors[-3:])}"
                            )
                        logger.info(f"[灾害预警] 卡片渲染成功，耗时 {elapsed:.3f}秒")
                        return output_path
                    else:
                        logger.warning("[灾害预警] 截图未生成文件")
                        await self._log_page_diagnostics(
                            page, reason="screenshot-missing"
                        )
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

        # 对注入的 selector 进行 JSON 编码，规避转义和 JS 语法截断安全风险。
        js_encoded_selector = json.dumps(selector)

        # 注入大小修正脚本，将 html 和 body 的大小强制与卡片对齐。
        # 远程模式不传递 selector 给 browserless，从而完美避开 browserless 本身在 float 宽高时的 setViewportSize Bug。
        # 代之以在 JS 中锁死 html 与 body 为卡片的 Math.ceil() 精准整数长宽，并使用 fullPage 截图以获得完美卡片大小和透明背景。
        if selector:
            inject_js = f"""
<script>
(function() {{
    function fixSize() {{
        try {{
            var selectorStr = {js_encoded_selector};
            var el = document.querySelector(selectorStr) || document.querySelector('.quake-card') || document.querySelector('.container');
            if (el) {{
                document.documentElement.style.margin = '0';
                document.documentElement.style.padding = '0';
                document.body.style.margin = '0';
                document.body.style.padding = '0';

                var rect = el.getBoundingClientRect();
                var w = Math.ceil(rect.width);
                var h = Math.ceil(rect.height);
                if (w > 0 && h > 0) {{
                    document.documentElement.style.width = w + 'px';
                    document.documentElement.style.height = h + 'px';
                    document.documentElement.style.overflow = 'hidden';
                    document.body.style.width = w + 'px';
                    document.body.style.height = h + 'px';
                    document.body.style.overflow = 'hidden';
                }}
            }}
        }} catch (e) {{
            console.error('Error fixing size:', e);
        }}
    }}
    if (document.readyState !== 'loading') {{
        fixSize();
    }} else {{
        document.addEventListener('DOMContentLoaded', fixSize);
    }}
    window.addEventListener('load', fixSize);
    // 延迟多次调用，以应对地图或瓦片等异步资源载入撑开或调整卡片高度
    setTimeout(fixSize, 200);
    setTimeout(fixSize, 600);
    setTimeout(fixSize, 1200);
    setTimeout(fixSize, 2000);
    setTimeout(fixSize, 3000);
    // 对一些极其缓慢的渲染兜底再次修剪
    setTimeout(fixSize, 5000);
}})();
</script>
"""
            if "</body>" in html_content:
                html_content = html_content.replace("</body>", f"{inject_js}</body>")
            else:
                html_content = html_content + inject_js

        # 构建请求 URL
        api_url = self._server_url
        if not api_url.endswith("/"):
            api_url += "/"
        api_url += "screenshot"

        try:
            # 构建请求体 - 使用 browserless screenshot API
            # 注意：此处全量使用 fullPage: True 截图，绝对不传任何顶级 selector，以彻底规避底层 setViewportSize 错误
            # gotoOptions 的 waitUntil 使用兼容 Puppeteer/Playwright 的 networkidle2 (或 networkidle0) 选项，
            # 避免直接传递仅由 Playwright 独占的 networkidle 属性从而引发远程服务报错。
            payload = {
                "html": html_content,
                "options": {
                    "type": "png",
                    "omitBackground": True,
                    "fullPage": True,  # 使用 fullPage 配合被修剪成卡片大小的 html 与 body
                },
                "gotoOptions": {
                    "waitUntil": "networkidle2",  # 确保地图瓦片等网络连接稳定(Puppeteer 格式)
                    "timeout": 60000,
                },
                "viewport": {
                    "width": 800,
                    "height": 800,
                    "deviceScaleFactor": 2,
                },
                "waitForTimeout": 3000,  # 额外等待 3 秒，确保地图瓦片完全展现并让 JS 执行完锁定尺寸
            }

            # 我们不传 options 里的 "selector"，但在 waitForSelector 选项中，我们可以只“等待”选择器出现而不触发裁剪视口
            if selector:
                payload["waitForSelector"] = {
                    "selector": selector,
                    "visible": True,
                    "timeout": 15000,
                }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=90),  # 90 秒超时保护
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
                        # 降级策略：如果由于浮点数 viewportSize 报错，自动关闭 fullPage 进行降级截图重试
                        if (
                            "expected integer" in error_text
                            or "viewportSize" in error_text
                        ):
                            logger.warning(
                                "[灾害预警] 检测到 browserless viewport 浮点数限制错误，尝试禁用 fullPage 并以固定视口大小降级重试..."
                            )
                            fallback_payload = dict(payload)
                            fallback_payload["options"] = {
                                "type": "png",
                                "omitBackground": True,
                                "fullPage": False,  # 禁用 fullPage 以避免 browserless 底层自动计算 float scrollHeight 并设置 viewportSize
                            }
                            try:
                                async with session.post(
                                    api_url,
                                    json=fallback_payload,
                                    timeout=aiohttp.ClientTimeout(total=60),
                                ) as fallback_response:
                                    if fallback_response.status == 200:
                                        image_data = await fallback_response.read()
                                        with open(output_path, "wb") as f:
                                            f.write(image_data)
                                        elapsed = time.time() - start_time
                                        logger.info(
                                            f"[灾害预警] 卡片渲染通过降级重试成功（HTTP API），耗时 {elapsed:.3f}秒"
                                        )
                                        return output_path
                                    else:
                                        fallback_error = await fallback_response.text()
                                        logger.error(
                                            f"[灾害预警] browserless API 降级重试依然返回错误: {fallback_response.status} - {fallback_error}"
                                        )
                            except Exception as fallback_ex:
                                logger.error(
                                    f"[灾害预警] browserless API 降级重试请求失败: {fallback_ex}"
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
        """清理资源，确保前一步失败也不影响后续步骤继续执行。"""
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
