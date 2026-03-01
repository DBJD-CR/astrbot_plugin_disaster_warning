const { useRef, useEffect, useCallback } = React;

/**
 * 在异步列表刷新后尽量恢复滚动位置。
 *
 * @param {Array<any>} restoreDeps - 触发滚动恢复检查的依赖数组
 * @returns {{ scrollRef: React.MutableRefObject<HTMLElement|null>, preserveScrollPosition: Function }}
 */
function usePreservedScroll(restoreDeps = []) {
    const scrollRef = useRef(null);
    const preservedScrollTopRef = useRef(null);
    const shouldRestoreScrollRef = useRef(false);

    const preserveScrollPosition = useCallback(() => {
        if (!scrollRef.current) return;
        preservedScrollTopRef.current = scrollRef.current.scrollTop;
        shouldRestoreScrollRef.current = true;
    }, []);

    useEffect(() => {
        if (!shouldRestoreScrollRef.current) return;

        const targetTop = preservedScrollTopRef.current;
        if (targetTop === null || targetTop === undefined) {
            shouldRestoreScrollRef.current = false;
            return;
        }

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                if (scrollRef.current) {
                    const maxScrollTop = Math.max(
                        scrollRef.current.scrollHeight - scrollRef.current.clientHeight,
                        0
                    );
                    scrollRef.current.scrollTop = Math.min(targetTop, maxScrollTop);
                }
                shouldRestoreScrollRef.current = false;
            });
        });
    }, restoreDeps);

    return {
        scrollRef,
        preserveScrollPosition,
    };
}
