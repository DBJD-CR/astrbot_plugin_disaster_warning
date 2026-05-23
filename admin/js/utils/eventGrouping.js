(() => {
    const { getDisplayTimeValue } = window.EventFormatters;

    /**
     * 获取事件发生时间对应的毫秒级时间戳，用于排序和时序校验
     */
    function getEventTimeMs(event) {
        const parsed = parseEventTimeToDate(getDisplayTimeValue(event, false), event?.source || '');
        return parsed ? parsed.getTime() : 0;
    }

    /**
     * 精细化事件版本/报数排序算法
     * 
     * 排序策略：
     * 1. 优先比对报数（report_num，如第 3 报必定在第 2 报之前展示）。
     * 2. 若报数一致或不存在，比对记录更新时间（recorded_at）以体现时效性。
     * 3. 若依然等价，比对最初发震的毫秒戳。
     */
    function compareEvents(a, b) {
        const reportA = Number(a?.report_num);
        const reportB = Number(b?.report_num);
        const hasA = Number.isFinite(reportA);
        const hasB = Number.isFinite(reportB);
        if (hasA && hasB && reportA !== reportB) return reportB - reportA; // 报数降序

        const updateA = parseEventTimeToDate(getDisplayTimeValue(a, true), a?.source || '');
        const updateB = parseEventTimeToDate(getDisplayTimeValue(b, true), b?.source || '');
        const diffUpdate = (updateB ? updateB.getTime() : 0) - (updateA ? updateA.getTime() : 0);
        if (diffUpdate !== 0) return diffUpdate; // 更新时间降序
        
        return getEventTimeMs(b) - getEventTimeMs(a); // 发震时间降序
    }

    /**
     * 构建去重唯一的 Key 指纹，防止重复的报数数据被重复渲染
     */
    function buildDedupKey(evt) {
        if (!evt || typeof evt !== 'object') return 'invalid';
        // 优先使用数据库 UUID 去重
        if (evt.id !== undefined && evt.id !== null && evt.id !== '') return `upd-id:${evt.id}`;
        // 使用三方源的独特事件 ID 去重
        if (evt.source_event_id) return `src-evt:${evt.source_event_id}`;
        // 使用报数和发震时间的组合指纹去重
        if (evt.report_num !== undefined && evt.report_num !== null && evt.report_num !== '') {
            return `report:${evt.report_num}|time:${evt.time || evt.timestamp || ''}`;
        }
        // 均不存在时，拼装物理数据指纹兜底去重
        return [evt.time || evt.timestamp || '', evt.magnitude ?? '', evt.depth ?? '', evt.description || ''].join('|');
    }

    /**
     * 将散装的时间事件流合并为以事件大类聚合的多报时序时间线组
     * 
     * 聚合逻辑：
     * 1. 扫描全部原始事件，依据 event_id（即某次地震发生时的唯一主 ID）将多次报数更新分流进对应的 group 容器。
     * 2. 对每个 group 内的数据序列进行 compareEvents 强力重排，确保第 1 报和最新报按顺序放置，并将最新一报赋给 latestEvent。
     * 3. 如果最新一报中携带了服务端的历史 history 事件快照，则提取去重，合并进前台事件容器中，防范网络断线引起的信息遗漏。
     * 4. 最终输出的所有 group 列表，按照 latestEvent 的发震时间由近到远降序重排。
     */
    function groupEvents(events) {
        const groups = {};
        const safeEvents = Array.isArray(events) ? events : [];

        // Step 1: 扫描并依据事件 ID 划分群组
        for (const evt of safeEvents) {
            const eventId = evt.event_id || evt.id || `${evt.time}-${evt.description}`;
            if (!groups[eventId]) {
                groups[eventId] = { id: eventId, events: [], latestEvent: null };
            }
            groups[eventId].events.push(evt);
        }

        // Step 2: 组内精密排序与历史去重合并
        Object.keys(groups).forEach((id) => {
            const group = groups[id];
            group.events.sort(compareEvents); // 组内排序
            group.latestEvent = group.events[0];
            
            const source = group.latestEvent.source || group.latestEvent.source_id || '';
            const sourceLower = String(source).toLowerCase();
            
            // 像 Wolfx 地震测定等 HTTP 定时拉取/低频补偿列表数据，不应算作多报更新，
            // 它们本身没有多报/增量更新概念（通常 report_num 固定为 1，但可能因为定时获取而多次入库或多条数据相同而被聚合为多更新）
            const isHttpListBased = sourceLower === 'cenc_wolfx' || sourceLower === 'jma_wolfx_info';

            const backendCount = group.latestEvent.update_count || 0;
            group.updateCount = isHttpListBased ? 1 : Math.max(group.events.length, backendCount);

            // 合并历史事件备份
            if (group.latestEvent.history && Array.isArray(group.latestEvent.history)) {
                const existingKeys = new Set(group.events.map((event) => buildDedupKey(event)));
                const historyEvents = group.latestEvent.history.filter((historyEvent) => {
                    const key = buildDedupKey(historyEvent);
                    if (existingKeys.has(key)) return false;
                    existingKeys.add(key);
                    return true;
                });
                if (historyEvents.length > 0) {
                    group.events.push(...historyEvents);
                    group.events.sort(compareEvents); // 再次排序
                    group.updateCount = isHttpListBased ? 1 : Math.max(group.events.length, backendCount);
                }
            }
        });

        // Step 3: 将群组按时间重新排布并输出为数组
        return Object.values(groups).sort((a, b) => getEventTimeMs(b.latestEvent) - getEventTimeMs(a.latestEvent));
    }

    window.EventGrouping = {
        getEventTimeMs,
        compareEvents,
        buildDedupKey,
        groupEvents,
    };
})();
