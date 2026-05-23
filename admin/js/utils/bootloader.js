(function () {
    let hidden = false;
    // 记录页面加载起点时刻，用于保证首屏加载遮罩展示的最短时长
    const start = (window.performance && typeof performance.now === 'function') ? performance.now() : Date.now();
    const MIN_VISIBLE_MS = 280; // 强制骨架屏展示的最短时间（单位毫秒），防止闪烁抖动

    // 执行隐藏骨架屏的操作
    function doHide() {
        if (hidden) return;
        hidden = true;

        const skeleton = document.getElementById('loading-skeleton');
        if (!skeleton) return;

        skeleton.classList.add('is-exiting'); // 注入平滑淡出动画类
        setTimeout(function () {
            if (skeleton && skeleton.parentNode) {
                skeleton.parentNode.removeChild(skeleton); // 从 DOM 树彻底注销骨架
            }

            const root = document.getElementById('root');
            if (root) {
                root.setAttribute('aria-busy', 'false'); // 标记主容器无阻塞
            }
        }, 320); // 320毫秒后完成垃圾清理
    }

    // 暴露在全局的隐藏遮罩接口
    window.__ASTRBOT_HIDE_BOOTLOADER = function () {
        const now = (window.performance && typeof performance.now === 'function') ? performance.now() : Date.now();
        // 如果系统就绪时间极短，自动做时长补偿，防止闪烁现象
        const delay = Math.max(0, MIN_VISIBLE_MS - (now - start));
        setTimeout(doHide, delay);
    };

    // 监听 window 的 load 加载事件，并触发遮罩淡出
    window.addEventListener('load', function () {
        if (window.__ASTRBOT_AUTH_PENDING) return; // 如果仍处于鉴权挂起状态，不予关闭
        setTimeout(window.__ASTRBOT_HIDE_BOOTLOADER, 1200); // 1.2秒超时强制关闭兜底
    }, { once: true });
})();
