/**
 * @file useConfigScrollMemory.js
 * @description 配置页面表单滚动条位置自动还原与持续化监听的 Hook。
 * 
 * 技术细节实现：
 * 1. 防抖拦截 (Debounce Scroll Listener)：由于滚动事件在用户滑动时高频触发，
 *    如果每次滚动都去执行 localStorage 写入，会导致主线程产生严重的 I/O 阻塞和卡顿。
 *    因此，我们在配置表单容器的滚动监听器中注入了 100ms 的防抖时滞 (Debounce Timeout)，只有在用户手势停稳后才保存当前坐标。
 * 2. 指针安全 (Passive Event Listener)：在绑定元素事件时，设置 { passive: true }，
 *    告知浏览器该滚动事件处理器中不会调用 preventDefault()，这可以让浏览器在垂直滚动时完全跳过主线程等待，在 GPU 线程中进行极速流畅地滑屏。
 */
function useConfigScrollMemory({
    draft,           // 本地持久化缓存读写模块
    loading,         // 页面整体骨架屏状态
    mode,            // 模式
    selectedSession, // 选中的 Session ID
    configScrollRef, // 保存表单 DOM 的容器 React Ref
}) {
    const restoredKeyRef = React.useRef('');

    /**
     * 将表单滚动条恢复至历史坐标处
     */
    const restoreScrollPosition = React.useCallback(() => {
        const el = configScrollRef.current;
        if (!el) return;

        // 生成区分模式和会话的标识键名
        const key = `${mode}::${selectedSession || ''}`;
        if (restoredKeyRef.current === key) return;

        const pos = draft.readScrollPosition(mode, selectedSession);
        restoredKeyRef.current = key;
        if (pos <= 0) return;

        // 使用 requestAnimationFrame 确保在浏览器重排重绘完成后再执行 scrollTop 的突变，保证还原 100% 成功
        requestAnimationFrame(() => {
            if (!configScrollRef.current) {
                return;
            }
            configScrollRef.current.scrollTop = pos;
        });
    }, [configScrollRef, draft, mode, selectedSession]);

    /**
     * 绑定监听函数，自动开启防抖监听
     */
    const bindScrollPersistence = React.useCallback((element) => {
        configScrollRef.current = element || null;
        if (!element || loading) {
            return () => {};
        }

        let timeout = null;
        const debouncedScroll = () => {
            if (timeout) {
                clearTimeout(timeout);
            }
            timeout = setTimeout(() => {
                draft.writeScrollPosition(element.scrollTop, mode, selectedSession);
            }, 100); // 100ms 防抖时限
        };

        // 绑定 passive: true，极大优化长列表移动端滑动帧率性能
        element.addEventListener('scroll', debouncedScroll, { passive: true });
        
        // 返回解除绑定的闭包函数，用以在配置模式改变、页面销毁或重载时进行垃圾回收
        return () => {
            element.removeEventListener('scroll', debouncedScroll);
            if (timeout) {
                clearTimeout(timeout);
            }
        };
    }, [configScrollRef, draft, loading, mode, selectedSession]);

    return {
        restoreScrollPosition,
        bindScrollPersistence,
    };
}
