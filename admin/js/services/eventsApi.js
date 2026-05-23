(() => {
    /**
     * 事件列表模块的接口定义类。
     * 
     * 主要交互逻辑：
     * 1. 规整化过滤器 (normalizeEventQuery)：将前端胶囊类型的分类（如 weather 气象）
     *    转换映射为后端 API 接收的底层英文标识（如 weather_alarm）。
     * 2. 查询参数安全归一：自动将无震级概念的气象和海啸查询条件转化为空字符上传，防止后端接收报错，
     *    对空字符串及排序参数进行拦截。
     */
    const client = window.DisasterApiClient;

    // 前后端胶囊类别和底层灾害标识的映射字典
    const TYPE_MAP = {
        earthquake_warning: 'earthquake_warning',
        earthquake: 'earthquake',
        tsunami: 'tsunami',
        weather: 'weather_alarm',
    };

    /**
     * 将前端的多维过滤状态变量规整化为符合后端格式的请求参数字典
     */
    function normalizeEventQuery(params = {}) {
        const type = params.type === 'all' ? '' : (TYPE_MAP[params.type] || params.type || '');
        const sources = Array.isArray(params.sources)
            ? params.sources.map((source) => String(source || '').trim()).filter(Boolean)
            : [];
        const minMagnitude = params.minMagnitude;
        const magnitudeOrder = String(params.magnitudeOrder || '').toLowerCase();
        const keyword = String(params.keyword || '').trim();
        const levelFilter = String(params.levelFilter || '').trim();

        return {
            page: params.page || 1,
            limit: params.limit || 50,
            type,
            source: sources.length > 0 ? sources.join(',') : '', // 将多选数组转为逗号相接的字符串
            min_magnitude: minMagnitude === null || minMagnitude === undefined || minMagnitude === '' ? '' : minMagnitude,
            magnitude_order: ['asc', 'desc'].includes(magnitudeOrder) ? magnitudeOrder : '',
            keyword,
            level_filter: levelFilter,
        };
    }

    const eventsApi = {
        // 分页获取历史事件列表，保留外部传入的 options 取消信号等
        getEvents: (params = {}, options = {}) => client.request('/events', {
            ...options,
            query: normalizeEventQuery(params),
            unwrap: false, // 禁用自动解包，保留 total 计数等元数据信息
        }),
        // 获取特大灾害警报，用于横向时间导轨
        getMajorEvents: (limit = 50, options = {}) => client.request('/events/major', {
            ...options,
            query: { limit: limit === 'all' ? 0 : limit },
            unwrap: false,
        }),
        // 气象精确 ID 或地区预警检索接口
        queryWeather: ({ keyword, optionalA = '', optionalB = '' } = {}, options = {}) => client.request('/weather/query', {
            ...options,
            query: {
                keyword,
                optional_a: optionalA,
                optional_b: optionalB,
            },
            unwrap: false,
        }),
    };

    window.DisasterEventsApi = eventsApi;
})();
