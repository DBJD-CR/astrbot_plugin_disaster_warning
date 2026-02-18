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
            // 优先使用后端返回的 update_count (注意：是下划线命名)
            // 如果后端未返回，则回退使用前端聚合的数组长度
            const backendCount = groups[id].latestEvent.update_count || 0;
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
                    // 更新计数
                    groups[id].updateCount = Math.max(groups[id].events.length, backendCount);
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

    const renderEventCard = (evt, isHistory = false, isExpandable = false, isExpanded = false, reportIndex = null) => {
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

        // 计算报数显示
        let reportLabel = '';
        if (reportIndex !== null && reportIndex > 0) {
            // 历史记录：显示为 "第X报"
            reportLabel = `第 ${reportIndex} 报`;
        } else if (evt.report_num) {
            // 最新记录：如果后端提供了 report_num，使用它
            reportLabel = `第 ${evt.report_num} 报`;
        } else if (!isHistory && isExpandable) {
            // 最新记录但没有 report_num：显示为"最新"
            reportLabel = '最新';
        }

        return (
            <div className={`event-card ${isExpandable ? 'clickable' : ''}`} style={{
                marginBottom: isHistory ? '4px' : '0',
                padding: isHistory ? '12px 20px' : '',
                position: 'relative'
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
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                        <Typography variant={isHistory ? "body2" : "h6"} sx={{ fontWeight: 700, color: 'text.primary' }}>
                            {evt.description || '未知位置'}
                        </Typography>
                        {reportLabel && (
                            <span style={{
                                fontSize: isHistory ? '11px' : '12px',
                                fontWeight: 600,
                                padding: '2px 8px',
                                borderRadius: '4px',
                                background: reportIndex !== null && reportIndex > 0 
                                    ? 'rgba(0,0,0,0.06)' 
                                    : 'var(--md-sys-color-primary-container)',
                                color: reportIndex !== null && reportIndex > 0
                                    ? 'inherit'
                                    : 'var(--md-sys-color-on-primary-container)',
                                opacity: 0.9
                            }}>
                                {reportLabel}
                            </span>
                        )}
                    </div>
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
                    {groupedEvents.map((group) => {
                        const isExpanded = expandedEvents.has(group.id);
                        const totalReports = group.events.length;
                        
                        return (
                            <div key={group.id} className="event-group">
                                {/* 折叠状态：只显示最新一条 */}
                                {!isExpanded && (
                                    <div onClick={() => group.updateCount > 1 && toggleEventGroup(group.id)}>
                                        {renderEventCard(
                                            { ...group.latestEvent, updateCount: group.updateCount },
                                            false,
                                            group.updateCount > 1,
                                            false,
                                            null
                                        )}
                                    </div>
                                )}

                                {/* 展开状态：显示所有报的时间线 */}
                                {isExpanded && (
                                    <div className="card" style={{ 
                                        padding: '24px',
                                        position: 'relative'
                                    }}>
                                        {/* 顶部标题栏 */}
                                        <div style={{
                                            display: 'flex',
                                            justifyContent: 'space-between',
                                            alignItems: 'center',
                                            marginBottom: '24px',
                                            paddingBottom: '16px',
                                            borderBottom: '1px solid var(--md-sys-color-outline-variant)'
                                        }}>
                                            <div>
                                                <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
                                                    {group.latestEvent.description || '未知位置'}
                                                </Typography>
                                                <Typography variant="body2" sx={{ opacity: 0.6 }}>
                                                    📡 {formatSourceName(group.latestEvent.source)} · 共 {totalReports} 次更新
                                                </Typography>
                                            </div>
                                            <button
                                                onClick={() => toggleEventGroup(group.id)}
                                                style={{
                                                    background: 'var(--md-sys-color-surface-variant)',
                                                    border: 'none',
                                                    borderRadius: '8px',
                                                    padding: '8px 16px',
                                                    cursor: 'pointer',
                                                    fontSize: '13px',
                                                    fontWeight: 600,
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: '4px'
                                                }}
                                            >
                                                <span>收起</span>
                                                <span>▲</span>
                                            </button>
                                        </div>

                                        {/* 时间线展示所有报 */}
                                        <div style={{ position: 'relative', paddingLeft: '40px' }}>
                                            {/* 时间线竖线 */}
                                            <div style={{
                                                position: 'absolute',
                                                left: '19px',
                                                top: '12px',
                                                bottom: '12px',
                                                width: '2px',
                                                background: 'var(--md-sys-color-outline-variant)'
                                            }}></div>

                                            {/* 所有报的列表（倒序：最新在上） */}
                                            {group.events.map((evt, idx) => {
                                                const reportIndex = totalReports - idx;
                                                const isLatest = idx === 0;
                                                const isEarthquake = evt.type === 'earthquake' || evt.type === 'earthquake_warning';
                                                
                                                return (
                                                    <div key={idx} style={{
                                                        position: 'relative',
                                                        marginBottom: idx === group.events.length - 1 ? '0' : '20px',
                                                        paddingBottom: idx === group.events.length - 1 ? '0' : '20px',
                                                        borderBottom: idx === group.events.length - 1 ? 'none' : '1px solid var(--md-sys-color-outline-variant)'
                                                    }}>
                                                        {/* 时间线节点 */}
                                                        <div style={{
                                                            position: 'absolute',
                                                            left: '-29px',
                                                            top: '8px',
                                                            width: '20px',
                                                            height: '20px',
                                                            borderRadius: '50%',
                                                            background: isLatest 
                                                                ? 'var(--md-sys-color-primary)' 
                                                                : 'var(--md-sys-color-surface-variant)',
                                                            border: `3px solid ${isLatest ? 'var(--md-sys-color-primary-container)' : 'var(--md-sys-color-surface)'}`,
                                                            boxShadow: isLatest ? '0 2px 8px rgba(103, 80, 164, 0.3)' : 'none'
                                                        }}></div>

                                                        {/* 报的内容 */}
                                                        <div style={{
                                                            display: 'flex',
                                                            gap: '12px',
                                                            alignItems: 'flex-start'
                                                        }}>
                                                            {/* 震级徽章（只对地震显示） */}
                                                            {isEarthquake && (
                                                                <div style={{
                                                                    minWidth: '60px',
                                                                    height: '60px',
                                                                    borderRadius: '12px',
                                                                    background: 'var(--md-sys-color-error-container)',
                                                                    display: 'flex',
                                                                    alignItems: 'center',
                                                                    justifyContent: 'center',
                                                                    fontSize: '20px',
                                                                    fontWeight: 700,
                                                                    color: 'var(--md-sys-color-on-error-container)',
                                                                    flexShrink: 0
                                                                }}>
                                                                    {(evt.magnitude || 0).toFixed(1)}
                                                                </div>
                                                            )}

                                                            {/* 信息列 */}
                                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px', flexWrap: 'wrap' }}>
                                                                    <span style={{
                                                                        fontSize: '13px',
                                                                        fontWeight: 700,
                                                                        padding: '3px 10px',
                                                                        borderRadius: '6px',
                                                                        background: isLatest 
                                                                            ? 'var(--md-sys-color-primary)'
                                                                            : 'var(--md-sys-color-surface-variant)',
                                                                        color: isLatest 
                                                                            ? 'var(--md-sys-color-on-primary)'
                                                                            : 'inherit'
                                                                    }}>
                                                                        第 {reportIndex} 报
                                                                    </span>
                                                                    {isLatest && (
                                                                        <span style={{
                                                                            fontSize: '13px',
                                                                            fontWeight: 700,
                                                                            padding: '3px 10px',
                                                                            borderRadius: '6px',
                                                                            background: 'var(--md-sys-color-tertiary-container)',
                                                                            color: 'var(--md-sys-color-on-tertiary-container)'
                                                                        }}>
                                                                            最新
                                                                        </span>
                                                                    )}
                                                                    <Typography variant="body2" sx={{ opacity: 0.6, fontSize: '13px' }}>
                                                                        🕒 {formatTimeFriendly(evt.time, displayTimezone)}
                                                                    </Typography>
                                                                </div>
                                                                {isEarthquake && (
                                                                    <Typography variant="body2" sx={{ opacity: 0.8, fontSize: '13px' }}>
                                                                        深度: {evt.depth ? `${evt.depth} km` : '未知'}
                                                                    </Typography>
                                                                )}
                                                            </div>
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </Box>
    );
}
