/**
 * 重大灾害事件列表拉取与监听钩子。
 * 
 * 业务细节说明：
 * - 聚合最近发生的强震、海啸预警或红色气象预警，主要用于大屏横向时间轴导轨组件的数据供给。
 * - 支持外部刷新信号，当长连接收到重大事件上报时，可强行重载大屏导轨。
 */
function useMajorEvents(displayLimit, refreshSignal) {
    const eventsApi = window.DisasterEventsApi;
    const [majorEvents, setMajorEvents] = React.useState([]); // 重大灾害队列
    const [loading, setLoading] = React.useState(false);       // 重大事件加载状态

    /**
     * 并发拉取最近发生的重大事件
     */
    const fetchMajorEvents = React.useCallback(() => {
        setLoading(true);
        eventsApi.getMajorEvents(displayLimit)
            .then((data) => {
                if (Array.isArray(data.events)) {
                    setMajorEvents(data.events);
                }
                setLoading(false);
            })
            .catch((err) => {
                console.error('Failed to fetch major events:', err);
                setLoading(false);
            });
    }, [eventsApi, displayLimit]);

    // 挂载或上限设置改变时触发载入
    React.useEffect(() => {
        fetchMajorEvents();
    }, [fetchMajorEvents]);

    // 当触发外部业务刷新信号时触发重拉
    React.useEffect(() => {
        fetchMajorEvents();
    }, [refreshSignal, fetchMajorEvents]);

    return {
        majorEvents,                     // 过滤出的危险事件队列
        loading,                         // 加载状态
        refreshMajorEvents: fetchMajorEvents // 手动触发强制更新的方法
    };
}

// 挂载至全局，供外部大屏与分析视图直接消费
window.useMajorEvents = useMajorEvents;
