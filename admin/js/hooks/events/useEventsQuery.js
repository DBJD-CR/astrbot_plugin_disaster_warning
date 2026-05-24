/**
 * 历史灾害事件列表的多维过滤、分页查询与实时推送同步钩子。
 * 
 * 核心机制说明：
 * 1. 自动请求终止：在用户频繁点选切换灾害大类或者修改搜索关键词时，
 *    通过请求中止控制器提前中断先前未响应的网络请求，避免前后两次网络数据返回冲突。
 * 2. 滚动状态保护：在实时推送新事件发生或长连接网络重连时，如果直接刷新列表会导致滚动条强行弹回顶部。
 *    这里通过保存滚动高度的方法，静默拉取数据并更新列表，从而保留用户的滑屏视野。
 * 3. 动态过滤路由：自动纠正气象预警和海啸预警等没有常规震级数值的事件分类，
 *    自动将震级过滤条件转化为气象或海啸的级别过滤。
 */
function useEventsQuery({ wsEvents, wsConnected, preserveScrollPosition }) {
    const eventsApi = window.DisasterEventsApi;
    
    // 列表过滤与分页控制状态
    const [filterType, setFilterType] = React.useState('all');                // 当前分类：all, earthquake, weather, tsunami
    const [currentPage, setCurrentPage] = React.useState(1);                  // 当前页码
    const [totalPages, setTotalPages] = React.useState(0);                    // 总页数
    const [total, setTotal] = React.useState(0);                              // 数据总数
    const [events, setEvents] = React.useState([]);                            // 当前页的事件队列
    const [loading, setLoading] = React.useState(false);                      // 加载状态
    const [pageSize, setPageSize] = React.useState(50);                        // 单页显示数
    const [maxPageSize, setMaxPageSize] = React.useState(200);                // 单页上限数限制
    const [pageInput, setPageInput] = React.useState('');                      // 跳页输入框的值
    const [sourceFilterMode, setSourceFilterMode] = React.useState('single');  // 数据源过滤模式：single 单选，multi 多选
    const [selectedSources, setSelectedSources] = React.useState([]);          // 选中的数据源
    const [sourceOptions, setSourceOptions] = React.useState([]);              // 可选数据源列表
    const [magnitudeFilter, setMagnitudeFilter] = React.useState('all');      // 震级过滤值或气象海啸级别过滤值
    const [magnitudeOrder, setMagnitudeOrder] = React.useState('default');      // 排序方式：default 默认，asc 升序，desc 降序
    const [keyword, setKeyword] = React.useState('');                          // 地区或内容关键字检索

    // 跨渲染周期的最新状态引用，以供异步事件拉取时获取最新快照
    const abortControllerRef = React.useRef(null);
    const filterTypeRef = React.useRef(filterType);
    const pageSizeRef = React.useRef(pageSize);
    const selectedSourcesRef = React.useRef(selectedSources);
    const currentPageRef = React.useRef(currentPage);
    const magnitudeFilterRef = React.useRef(magnitudeFilter);
    const magnitudeOrderRef = React.useRef(magnitudeOrder);
    const keywordRef = React.useRef(keyword);

    /**
     * 核心拉取函数：装配并提交多维过滤参数，控制加载逻辑
     */
    const fetchEvents = React.useCallback((page, type, limit, sources = [], minMagnitude = null, magnitudeSort = '', searchKeyword = '', levelFilter = '', options = {}) => {
        // 请求拦截：如果先前有未完成的网络响应，强行中断，清理网络通道
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        const controller = new AbortController();
        abortControllerRef.current = controller;

        const safeLimit = Number(limit) > 0 ? Number(limit) : 50;
        const preserveScroll = Boolean(options?.preserveScroll);
        const shouldToggleLoading = !preserveScroll;

        // 如果配置了静默更新，利用回调保存当前的滚动高度
        if (preserveScroll && typeof preserveScrollPosition === 'function') {
            preserveScrollPosition();
        }
        if (shouldToggleLoading) {
            setLoading(true);
        }

        eventsApi.getEvents({
            page,
            limit: safeLimit,
            type,
            sources,
            minMagnitude,
            magnitudeOrder: magnitudeSort,
            keyword: searchKeyword,
            levelFilter,
        }, { signal: controller.signal })
            .then((data) => {
                setEvents(Array.isArray(data.events) ? data.events : []);
                setTotal(data.total || 0);
                setTotalPages(data.total_pages || 0);
                setSourceOptions(Array.isArray(data.source_options) ? data.source_options : []);
                
                // 按服务端的硬性阈值约束前端单页大小上限
                const apiMaxLimit = Number(data.max_limit);
                if (Number.isFinite(apiMaxLimit) && apiMaxLimit > 0) {
                    setMaxPageSize(Math.floor(apiMaxLimit));
                }
                if (shouldToggleLoading) setLoading(false);
            })
            .catch((err) => {
                if (err.name === 'AbortError') {
                    // 正常的请求中断，直接忽略，不影响界面
                    if (shouldToggleLoading) setLoading(false);
                    return;
                }
                console.error('Failed to fetch events:', err);
                if (shouldToggleLoading) setLoading(false);
            });
    }, [eventsApi, preserveScrollPosition]);

    // 异步加载所有可用数据源以作下拉筛选，即使大列表还在加载中，筛选器也能立即渲染出来
    React.useEffect(() => {
        eventsApi.getEvents({ page: 1, limit: 1 })
            .then((data) => {
                if (Array.isArray(data.source_options) && data.source_options.length > 0) {
                    setSourceOptions(data.source_options);
                }
            })
            .catch(() => {});
    }, [eventsApi]);

    // 监听过滤参数变化：重置当前页码为第一页并重新加载数据
    React.useEffect(() => {
        setCurrentPage(1);
        setPageInput('');
        
        // 气象与海啸没有震级属性，需要转换为级别过滤
        const usesLevelFilter = filterType === 'weather' || filterType === 'tsunami';
        const minMagnitude = usesLevelFilter || magnitudeFilter === 'all' ? null : Number(magnitudeFilter);
        const levelFilter = usesLevelFilter && magnitudeFilter !== 'all' ? magnitudeFilter : '';
        const magnitudeSort = usesLevelFilter || magnitudeOrder === 'default' ? '' : magnitudeOrder;
        
        fetchEvents(1, filterType, pageSize, selectedSources, minMagnitude, magnitudeSort, keyword, levelFilter);
    }, [filterType, pageSize, selectedSources, magnitudeFilter, magnitudeOrder, keyword, fetchEvents]);

    // 限制单页显示数不超出接口允许的最大上限
    React.useEffect(() => {
        if (pageSize > maxPageSize) setPageSize(maxPageSize);
    }, [pageSize, maxPageSize]);

    // 每次渲染结束后，将最新状态同步至引用对象中，保证异步回调能读取最新快照
    React.useEffect(() => {
        filterTypeRef.current = filterType;
        pageSizeRef.current = pageSize;
        selectedSourcesRef.current = selectedSources;
        currentPageRef.current = currentPage;
        magnitudeFilterRef.current = magnitudeFilter;
        magnitudeOrderRef.current = magnitudeOrder;
        keywordRef.current = keyword;
    });

    // 响应长连接的实时事件推送，若收到新灾害推送，进行滚动条保存并静默拉取最新列表
    React.useEffect(() => {
        if (!wsConnected) return;
        const currentFilterType = filterTypeRef.current;
        const usesLevelFilter = currentFilterType === 'weather' || currentFilterType === 'tsunami';
        const minMagnitude = usesLevelFilter || magnitudeFilterRef.current === 'all' ? null : Number(magnitudeFilterRef.current);
        const levelFilter = usesLevelFilter && magnitudeFilterRef.current !== 'all' ? magnitudeFilterRef.current : '';
        const magnitudeSort = usesLevelFilter || magnitudeOrderRef.current === 'default' ? '' : magnitudeOrderRef.current;
        
        fetchEvents(
            currentPageRef.current,
            currentFilterType,
            pageSizeRef.current,
            selectedSourcesRef.current,
            minMagnitude,
            magnitudeSort,
            keywordRef.current,
            levelFilter,
            { preserveScroll: true }
        );
    }, [wsEvents, wsConnected, fetchEvents]);

    // 组件卸载时自动终止未完成的网络请求
    React.useEffect(() => {
        return () => {
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };
    }, []);

    /**
     * 强类型跳页控制函数
     */
    const goToPage = React.useCallback((targetPage) => {
        if (totalPages <= 0) return;
        const safePage = Math.max(1, Math.min(totalPages, targetPage)); // 边界安全限幅
        if (safePage === currentPage) return;
        
        setCurrentPage(safePage);
        setPageInput('');
        const usesLevelFilter = filterType === 'weather' || filterType === 'tsunami';
        const minMagnitude = usesLevelFilter || magnitudeFilter === 'all' ? null : Number(magnitudeFilter);
        const levelFilter = usesLevelFilter && magnitudeFilter !== 'all' ? magnitudeFilter : '';
        const magnitudeSort = usesLevelFilter || magnitudeOrder === 'default' ? '' : magnitudeOrder;
        
        fetchEvents(safePage, filterType, pageSize, selectedSources, minMagnitude, magnitudeSort, keyword, levelFilter);
    }, [currentPage, totalPages, fetchEvents, filterType, pageSize, selectedSources, magnitudeFilter, magnitudeOrder, keyword]);

    return {
        filterType, setFilterType,
        currentPage, setCurrentPage,
        totalPages, total,
        events, loading,
        pageSize, setPageSize,
        maxPageSize,
        pageInput, setPageInput,
        sourceFilterMode, setSourceFilterMode,
        selectedSources, setSelectedSources,
        sourceOptions,
        magnitudeFilter, setMagnitudeFilter,
        magnitudeOrder, setMagnitudeOrder,
        keyword, setKeyword,
        fetchEvents,
        goToPage,
    };
}
