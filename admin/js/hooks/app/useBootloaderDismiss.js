/**
 * @file useBootloaderDismiss.js
 * @description 主应用就绪后隐藏启动加载遮罩的副作用钩子。
 * 
 * 性能优化细节：
 * 1. 双重动画帧等待 (Double RequestAnimationFrame)：为了确保骨架屏和 DOM 树已经在浏览器中完成了首次完整的绘制 (Paint) 
 *    并呈现在物理屏幕上，我们等待两个连续的渲染帧周期，然后在第二帧里执行隐藏遮罩的回调函数。
 * 2. 回退机制：对于缺少 requestAnimationFrame 支持的老旧 WebView，回退为秒级 `setTimeout(..., 0)` 执行。
 */
function useBootloaderDismiss() {
    React.useEffect(() => {
        const hideBootloader = () => {
            if (typeof window.__ASTRBOT_HIDE_BOOTLOADER === 'function') {
                window.__ASTRBOT_HIDE_BOOTLOADER();
            }
        };

        if (typeof window.requestAnimationFrame === 'function') {
            // 第一帧等待：确保当前的 DOM 合成与重绘已被浏览器排入日程
            window.requestAnimationFrame(() => {
                // 第二帧执行：在前一帧渲染完成并呈现出首屏后，再平滑解开加载背景遮罩
                window.requestAnimationFrame(hideBootloader);
            });
        } else {
            // 回退分支：老旧环境下的微秒延迟执行
            setTimeout(hideBootloader, 0);
        }
    }, []);
}
