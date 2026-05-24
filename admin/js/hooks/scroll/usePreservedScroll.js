const { useRef, useEffect, useCallback } = React;

/**
 * 提供在列表重新拉取或数据变更后，尽量维持原先滚动位置的精细化控制钩子。
 * 
 * 核心机制说明：
 * - 列表高度变化保护：在数据进行异步请求刷新前，手动记录当时的滚动条相对顶部高度。
 * - 双重帧对齐还原：当数据更新依赖触发后，采用双重动画帧渲染等待。
 *   在确认最新 DOM 挂载并计算出最大可滚动边界后，
 *   再对滚动位置进行精准回填限幅（保证不超出物理容器），避免视图重绘时产生可见的卡顿或抖动。
 */
function usePreservedScroll(restoreDeps = []) {
    const scrollRef = useRef(null);
    const preservedScrollTopRef = useRef(null);
    const shouldRestoreScrollRef = useRef(false);

    /**
     * 保存现有的滚动高度，并置位待还原标志
     */
    const preserveScrollPosition = useCallback(() => {
        if (!scrollRef.current) return;
        preservedScrollTopRef.current = scrollRef.current.scrollTop;
        shouldRestoreScrollRef.current = true;
    }, []);

    // 监听依赖改变后的重新还原
    useEffect(() => {
        if (!shouldRestoreScrollRef.current) return;

        const targetTop = preservedScrollTopRef.current;
        if (targetTop === null || targetTop === undefined) {
            shouldRestoreScrollRef.current = false;
            return;
        }

        // 双帧等待，确保浏览器已完成子树列表元素的重构与物理高度测算
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                if (scrollRef.current) {
                    const maxScrollTop = Math.max(
                        scrollRef.current.scrollHeight - scrollRef.current.clientHeight,
                        0
                    );
                    // 还原高度，若因删除项导致高度变矮，则限制在最大可滑动边界以内
                    scrollRef.current.scrollTop = Math.min(targetTop, maxScrollTop);
                }
                shouldRestoreScrollRef.current = false;
            });
        });
    });

    return {
        scrollRef,               // 供需要监控滚动的容器 DOM 绑定的引用
        preserveScrollPosition,  // 外部在发起异步重新拉取前手动触发保存位置的函数
    };
}
