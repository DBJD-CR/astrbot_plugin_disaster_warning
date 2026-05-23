(() => {
    /**
     * 对后台统计的大屏分析数据进行归一化及排序规整的工具类。
     * 
     * 核心逻辑解析：
     * 1. 数组结构规整 (entriesToSortedList)：将后端传回的键值对形式的对象数据（如 区域名: 发生次数），
     *    转化为前端表格和柱状图可直接遍历的数组对象形式，并按照计数值从大到小降序排列，以便前台展示 Top10 榜单。
     * 2. 数据防抖与保护：对后端因时段无数据返回的未定义字段进行合理的默认零值拦截，
     *    防止前台大屏图表发生致命错误。
     */

    /**
     * 将对象键值对映射转换为降序排列的数组对象列表
     */
    function entriesToSortedList(source, keyName) {
        if (!source || typeof source !== 'object') {
            return [];
        }
        return Object.entries(source)
            .map(([key, count]) => ({ [keyName]: key, count }))
            .sort((a, b) => b.count - a.count); // 按发生频数由高到低降序重排
    }

    /**
     * 将后端复杂的嵌套统计对象整合并转化输出为前端标准的格式
     */
    function normalizeStatsPayload(stats = {}) {
        const earthquakeStats = stats.earthquake_stats || {};
        const weatherStats = stats.weather_stats || {};
        const byType = stats.by_type || {};

        return {
            stats: {
                totalEvents: stats.total_events || 0,                         // 捕捉事件总数
                earthquakeCount: byType.earthquake || 0,                     // 地震事件总数
                warningCount: typeof byType.earthquake_warning !== 'undefined'
                    ? Number(byType.earthquake_warning)
                    : 0,                                                      // 预警事件总数
                tsunamiCount: byType.tsunami || 0,                           // 海啸预警总数
                weatherCount: byType.weather_alarm || 0,                     // 气象灾害总数
                maxMagnitude: earthquakeStats.max_magnitude || null,         // 周期内全球最大震级极值
                earthquakeRegions: entriesToSortedList(earthquakeStats.by_region, 'region'), // 地震多发地 Top10 排行数据
                weatherRegions: entriesToSortedList(weatherStats.by_region, 'region'),       // 气象多发地 Top10 排行数据
                weatherTypes: entriesToSortedList(weatherStats.by_type, 'type'),             // 气象细分类别分布
                weatherLevels: entriesToSortedList(weatherStats.by_level, 'level'),          // 气象预警颜色分级占比
                dataSources: entriesToSortedList(stats.by_source, 'source'),                 // 三方数据源警报占比
                logStats: stats.log_stats || null,                                           // 日志拦截分析统计
            },
            events: stats.recent_pushes || [],                               // 历史推送详情队列
            magnitudeDistribution: earthquakeStats.by_magnitude || {},        // 地震震级区间分布映射表
        };
    }

    window.StatsNormalizer = {
        entriesToSortedList,
        normalizeStatsPayload,
    };
})();
