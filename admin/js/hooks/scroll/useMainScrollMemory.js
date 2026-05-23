/**
 * 控制系统主视窗页面在视图切换时的滚动条位置记忆与平滑还原钩子。
 * 
 * 核心技术细节与业务交互：
 * 1. 分页位置隔离：依据当前激活的视图模式（如 status, events 等）拼装本地存储键名，
 *    实现不同视图下的滚动高度独立记忆。
 * 2. 状态冲突判定：在滚动条执行异步还原期间，暂时锁定写入。
 *    若在此期间管理员强行用手势进行滑屏（如触发 touchstart, wheel, keydown 等物理事件），
 *    表示用户意图主动干预，立即打断并宣告还原终止，将滚动控制权交还给用户。
 * 3. 稳健的多频级延迟重试：由于部分视图包含复杂图表、图片等异步组件，初次挂载时可能因高度尚未被撑开导致 scrollTop 赋值失败。
 *    设计了自退火延迟队列 [50, 200, 500, 1000, 2000] 毫秒进行梯度重试，确保高度被撑开的瞬间立即完成还原。
 */
function useMainScrollMemory({ currentView, restoreTriggers = [] }) {
    const mainContentRef = React.useRef(null);
    const isRestoringRef = React.useRef(false); // 是否正处于滚动还原周期

    React.useLayoutEffect(() => {
        const el = mainContentRef.current;
        if (!el) return;

        const key = `astrbot_scroll_${currentView}`;
        const savedPos = parseInt(localStorage.getItem(key) || '0', 10);
        isRestoringRef.current = true;

        if (savedPos > 0) {
            el.scrollTop = savedPos;

            // 延迟重试算子：防止由于子页面骨架屏未完成异步请求、图片未加载前高度不足导致的还原失效
            const retryScroll = () => {
                if (!isRestoringRef.current) return;

                const currentScroll = el.scrollTop;
                // 如果发现用户的实际高度和保存高度偏差过大且不处于初始的 0 状态，说明发生了强力手势干预，主动退出
                if (currentScroll > 0 && Math.abs(currentScroll - savedPos) > 100) {
                    isRestoringRef.current = false;
                    return;
                }

                // 若偏差较小且容器内容已加载出，微调还原到指定精确点
                if (Math.abs(currentScroll - savedPos) > 5 && el.scrollHeight > el.clientHeight) {
                    el.scrollTop = savedPos;
                }
            };

            // 梯度延时重试队列
            const timeouts = [50, 200, 500, 1000, 2000].map((delay) => setTimeout(retryScroll, delay));
            const endTimer = setTimeout(() => {
                isRestoringRef.current = false;
            }, 2500);

            // 清理临时定时器
            return () => {
                timeouts.forEach(clearTimeout);
                clearTimeout(endTimer);
            };
        }

        el.scrollTop = 0;
        isRestoringRef.current = false;
    }, [currentView]);

    // 辅助触发器监听：如列表数据更新后，再次执行定位微调
    React.useEffect(() => {
        if (!isRestoringRef.current || !mainContentRef.current) return;

        const key = `astrbot_scroll_${currentView}`;
        const savedPos = parseInt(localStorage.getItem(key) || '0', 10);
        const el = mainContentRef.current;

        if (savedPos > 0 && Math.abs(el.scrollTop - savedPos) > 20 && el.scrollHeight >= savedPos) {
            if (el.scrollTop > 0 && Math.abs(el.scrollTop - savedPos) > 100) {
                isRestoringRef.current = false;
                return;
            }
            el.scrollTop = savedPos;
        }
    }, [currentView, ...restoreTriggers]);

    React.useEffect(() => {
        const el = mainContentRef.current;
        if (!el) return;

        const handleScroll = () => {
            const key = `astrbot_scroll_${currentView}`;
            const savedPos = parseInt(localStorage.getItem(key) || '0', 10);

            if (isRestoringRef.current) {
                if (Math.abs(el.scrollTop - savedPos) > 100) {
                    isRestoringRef.current = false;
                } else {
                    return;
                }
            }

            localStorage.setItem(key, el.scrollTop);
        };

        let timeout;
        const debouncedScroll = () => {
            clearTimeout(timeout);
            timeout = setTimeout(handleScroll, 100); // 100ms 写入防抖
        };
        const stopRestoring = () => {
            isRestoringRef.current = false; // 用户主动产生物理触碰或按键时，终止还原模式
        };

        el.addEventListener('scroll', debouncedScroll);
        el.addEventListener('touchstart', stopRestoring, { passive: true });
        el.addEventListener('wheel', stopRestoring, { passive: true });
        el.addEventListener('mousedown', stopRestoring);
        el.addEventListener('keydown', stopRestoring);

        return () => {
            el.removeEventListener('scroll', debouncedScroll);
            el.removeEventListener('touchstart', stopRestoring);
            el.removeEventListener('wheel', stopRestoring);
            el.removeEventListener('mousedown', stopRestoring);
            el.removeEventListener('keydown', stopRestoring);
            clearTimeout(timeout);
        };
    }, [currentView]);

    return mainContentRef;
}

window.useMainScrollMemory = useMainScrollMemory;
