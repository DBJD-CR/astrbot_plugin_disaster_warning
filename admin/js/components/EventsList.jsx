const { Box, Typography, Collapse } = MaterialUI;
const { useState, useMemo } = React;

/**
 * 事件列表组件
 * 展示地震、海啸、气象预警等各类事件列表
 * 提供了按事件类型筛选、按事件ID分组以及折叠历史更新记录的功能
 */
function EventsList() {
    const { state } = useAppContext();
    const { events, config } = state;
    const displayTimezone = config.displayTimezone || 'UTC+8';
    const [filterType, setFilterType] = useState('all');
    const [expandedEvents, setExpandedEvents] = useState(new Set());

    const filteredEvents = useMemo(() => {
        // 先确保 events 是数组，如果不是则返回空数组，避免崩溃
        const safeEvents = Array.isArray(events) ? events : [];
        if (filterType === 'all') return safeEvents;
        
        return safeEvents.filter(evt => {
            const type = evt.type || '';
            if (filterType === 'earthquake_warning') {
                return type === 'earthquake_warning';
            }
            if (filterType === 'earthquake') {
                return type === 'earthquake';
            }
            if (filterType === 'tsunami') {
                return type === 'tsunami';
            }
            if (filterType === 'weather') {
                return type === 'weather_alarm';
            }
            return true;
        });
    }, [events, filterType]);

    // 将扁平的事件列表按照 event_id 进行分组
    // 这样可以将同一事件的多次更新（如：第1报、第2报...最终报）聚合在一起显示
    const groupedEvents = useMemo(() => {
        const groups = {};

        for (const evt of filteredEvents) {
            // 尝试获取唯一事件ID，如果不存在则使用 时间-描述 作为临时ID
            const eventId = evt.event_id || evt.id || `${evt.time}-${evt.description}`;
            if (!groups[eventId]) {
                groups[eventId] = {
                    id: eventId,
                    events: [],
                    latestEvent: null
                };
            }
            groups[eventId].events.push(evt);
        }

        // 处理每个分组：排序、计算更新数量、合并历史记录
        for (const id in groups) {
            // 按时间倒序排列，最新的在最前
            groups[id].events.sort((a, b) => new Date(b.time) - new Date(a.time));
            groups[id].latestEvent = groups[id].events[0];
            
            // 计算更新总数：
            // 优先使用后端返回的 updateCount (因为它可能包含数据库中更老的历史记录)
            // 如果后端未返回，则回退使用前端聚合的数组长度
            const backendCount = groups[id].latestEvent.updateCount || 0;
            groups[id].updateCount = Math.max(groups[id].events.length, backendCount);
            
            // 合并后端返回的 'history' 字段 (如果有)
            // 这是一个补充机制，确保即使 WebSocket 只推了最新一条，前端展开时也能看到之前的记录
            if (groups[id].latestEvent.history && Array.isArray(groups[id].latestEvent.history)) {
                // 过滤掉已存在的事件 (避免重复显示)
                const existingIds = new Set(groups[id].events.map(e => e.time));
                const historyEvents = groups[id].latestEvent.history.filter(h => !existingIds.has(h.time));
                
                if (historyEvents.length > 0) {
                    groups[id].events.push(...historyEvents);
                    // 合并后再次重新排序
                    groups[id].events.sort((a, b) => new Date(b.time) - new Date(a.time));
                }
            }
        }

        // 将分组转换为数组，并按最新事件的时间倒序排列（最近发生的事件排在列表顶部）
        return Object.values(groups).sort((a, b) =>
            new Date(b.latestEvent.time) - new Date(a.latestEvent.time)
        );
    }, [filteredEvents]);

    const toggleEventGroup = (groupId) => {
        setExpandedEvents(prev => {
            const newSet = new Set(prev);
            if (newSet.has(groupId)) {
                newSet.delete(groupId);
            } else {
                newSet.add(groupId);
            }
            return newSet;
        });
    };

    const renderEventCard = (evt, isHistory = false, isExpandable = false, isExpanded = false) => {
        const isEarthquake = evt.type === 'earthquake' || evt.type === 'earthquake_warning';
        const isTsunami = evt.type === 'tsunami';
        const isWeather = evt.type === 'weather_alarm';

        let badgeContent = '❓';
        let badgeClass = 'badge-unknown';
        let weatherIconUrl = null;

        if (isEarthquake) {
            badgeContent = (evt.magnitude || 0).toFixed(1);
            badgeClass = 'badge-earthquake';
        } else if (isTsunami) {
            badgeContent = '🌊';
            badgeClass = 'badge-tsunami';
        } else if (isWeather) {
            badgeContent = '☁️';
            badgeClass = 'badge-weather';
            // 尝试构建气象预警图标 URL
            // 优先从 weather_type_code (后端统计字段) 获取，其次尝试 raw_data
            const pCode = evt.weather_type_code || evt.raw_data?.type || evt.data?.type;
            if (pCode) {
                weatherIconUrl = `https://image.nmc.cn/assets/img/alarm/${pCode}.png`;
            }
        }

        return (
            <div className={`event-card ${isExpandable ? 'clickable' : ''}`} style={{
                marginBottom: isHistory ? '4px' : '0',
                padding: isHistory ? '12px 20px' : ''
            }}>
                <div className={`mag-badge ${badgeClass}`} style={{
                    width: isHistory ? '40px' : '56px',
                    height: isHistory ? '40px' : '56px',
                    fontSize: isHistory ? '14px' : '18px',
                    overflow: 'visible', // 允许溢出，防止图标被切
                    padding: weatherIconUrl ? 0 : undefined,
                    borderRadius: weatherIconUrl ? '0' : '50%', // 气象图标完全去圆角
                    backgroundColor: weatherIconUrl ? 'transparent' : undefined,
                    boxShadow: weatherIconUrl ? 'none' : undefined
                }}>
                    {weatherIconUrl ? (
                        <img
                            src={weatherIconUrl}
                            alt={badgeContent}
                            style={{
                                width: '100%',
                                height: '100%',
                                objectFit: 'contain',
                                transform: 'scale(1.5)' // 放大显示，因为原图标可能有留白
                            }}
                            onError={(e) => {
                                e.target.style.display = 'none';
                                // 图片加载失败时恢复背景色和阴影 (通过修改父元素样式较为复杂，这里简单处理)
                                e.target.parentElement.style.backgroundColor = 'var(--md-sys-color-surface-variant)';
                            }}
                        />
                    ) : (
                        badgeContent
                    )}
                </div>

                <div className="event-main">
                    <Typography variant={isHistory ? "body2" : "h6"} sx={{ fontWeight: 700, color: 'text.primary', mb: 0.5 }}>
                        {evt.description || '未知位置'}
                    </Typography>
                    <div className="event-meta" style={{ opacity: 0.6, display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            🕒 {formatTimeFriendly(evt.time, displayTimezone)}
                        </span>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{ opacity: 0.5 }}>•</span>
                            📡 {formatSourceName(evt.source)}
                        </span>
                    </div>
                </div>

                {isExpandable && (
                    <div className="update-badge">
                        <span className="update-count">{isExpanded ? '收起' : `${evt.updateCount || ''} 条更新`}</span>
                        <span className="update-icon">{isExpanded ? '▲' : '▼'}</span>
                    </div>
                )}
            </div>
        );
    };

    return (
        <Box sx={{ my: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4, flexWrap: 'wrap', gap: 2 }}>
                <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.5px', color: 'text.primary' }}>
                    最近事件记录
                </Typography>
                
                <div className="filter-group">
                    {[
                        { id: 'all', label: '全部' },
                        { id: 'earthquake_warning', label: '地震预警' },
                        { id: 'earthquake', label: '地震情报' },
                        { id: 'weather', label: '气象预警' },
                        { id: 'tsunami', label: '海啸预警' }
                    ].map(item => (
                        <button
                            key={item.id}
                            className={`btn-filter ${filterType === item.id ? 'active' : ''}`}
                            onClick={() => setFilterType(item.id)}
                        >
                            {filterType === item.id && <span style={{ fontSize: '12px' }}>✓</span>}
                            {item.label}
                        </button>
                    ))}
                </div>
            </Box>

            {groupedEvents.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: '80px' }}>
                    <Typography variant="h2" sx={{ opacity: 0.1, mb: 2 }}>📭</Typography>
                    <Typography variant="body1" sx={{ opacity: 0.5 }}>暂无该类型的事件记录</Typography>
                    <Typography variant="body2" sx={{ opacity: 0.3, mt: 1, fontSize: '0.8rem' }}>
                        系统正在持续监测中...
                    </Typography>
                </div>
            ) : (
                <div className="events-list">
                    {groupedEvents.map((group) => (
                        <div key={group.id} className="event-group">
                            <div onClick={() => group.updateCount > 1 && toggleEventGroup(group.id)}>
                                {renderEventCard(
                                    { ...group.latestEvent, updateCount: group.updateCount },
                                    false,
                                    group.updateCount > 1,
                                    expandedEvents.has(group.id)
                                )}
                            </div>

                            <Collapse in={expandedEvents.has(group.id)} timeout={300}>
                                {group.updateCount > 1 && (
                                    <div style={{
                                        padding: '12px 0 12px 64px',
                                        display: 'flex',
                                        flexDirection: 'column',
                                        gap: '12px',
                                        marginTop: '8px'
                                    }}>
                                        {group.events.slice(1).map((evt, idx) => (
                                            <div key={idx}>
                                                {renderEventCard(evt, true)}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </Collapse>
                        </div>
                    ))}
                </div>
            )}
        </Box>
    );
}
