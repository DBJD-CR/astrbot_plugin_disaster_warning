const { Typography, Chip, Tooltip } = MaterialUI;
const { useMemo } = React;

/**
 * 重大事件时间轴组件
 * 横向展示最近的重大事件 (M>=5.0 或 红色/橙色预警)
 */
function HorizontalTimeline({ style }) {
    const { state } = useAppContext();
    const { events } = state;

    // 筛选并排序重大事件
    const timelineItems = useMemo(() => {
        if (!events || !Array.isArray(events)) return [];

        const majorEvents = events.filter(e => {
            // 地震：M >= 5.0
            if (e.type === 'earthquake' && e.magnitude >= 5.0) return true;
            
            // 气象/海啸：描述中包含红色/橙色
            if (e.description && (e.description.includes('红') || e.description.includes('橙'))) return true;
            
            return false;
        });

        // 按时间倒序排列获取最新的 5 个，然后反转（右边是最新的）
        return majorEvents
            .slice()
            .sort((a, b) => {
                const timeA = new Date(a.time || a.timestamp).getTime();
                const timeB = new Date(b.time || b.timestamp).getTime();
                return timeB - timeA;
            })
            .slice(0, 5)
            .reverse();
    }, [events]);

    if (timelineItems.length === 0) {
        return (
            <div className="card" style={{ ...style, display: 'flex', flexDirection: 'column', minHeight: '180px' }}>
                <div className="chart-card-header">
                    <span style={{ fontSize: '20px' }}>⏳</span>
                    <Typography variant="h6">重大事件回溯</Typography>
                </div>
                <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.5 }}>
                    <Typography variant="body2">近期无重大事件</Typography>
                </div>
            </div>
        );
    }

    const formatTime = (isoString) => {
        if (!isoString) return '';
        try {
            const date = new Date(isoString);
            return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;
        } catch (e) {
            return '';
        }
    };

    const getEventColor = (event) => {
        if (event.type === 'earthquake') {
            if (event.magnitude >= 7.0) return 'var(--md-sys-color-error)'; // 红色
            if (event.magnitude >= 6.0) return '#FB8C00'; // 橙色
            return '#FDD835'; // 黄色
        }
        if (event.description?.includes('红')) return 'var(--md-sys-color-error)';
        if (event.description?.includes('橙')) return '#FB8C00';
        return 'var(--md-sys-color-primary)';
    };

    return (
        <div className="card" style={{ ...style, display: 'flex', flexDirection: 'column', overflowX: 'auto' }}>
            <div className="chart-card-header" style={{ marginBottom: '24px' }}>
                <span style={{ fontSize: '20px' }}>⏳</span>
                <Typography variant="h6">重大事件回溯</Typography>
            </div>

            <div style={{ 
                flex: 1, 
                display: 'flex', 
                alignItems: 'center', 
                position: 'relative', 
                padding: '20px 0',
                minWidth: '600px' // 保证最小宽度，避免挤压
            }}>
                {/* 轴线 */}
                <div style={{ 
                    position: 'absolute', 
                    top: '50%', 
                    left: '20px', 
                    right: '20px', 
                    height: '2px', 
                    background: 'var(--md-sys-color-outline-variant)',
                    zIndex: 0
                }}></div>

                {/* 事件节点 */}
                <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between', 
                    width: '100%', 
                    zIndex: 1,
                    padding: '0 20px'
                }}>
                    {timelineItems.map((item, index) => {
                        const color = getEventColor(item);
                        const isLatest = index === timelineItems.length - 1;

                        return (
                            <div key={index} style={{ 
                                display: 'flex', 
                                flexDirection: 'column', 
                                alignItems: 'center', 
                                position: 'relative',
                                width: '120px' // 固定每个节点的宽度区域
                            }}>
                                {/* 上方：时间 */}
                                <Typography variant="caption" sx={{ 
                                    opacity: 0.7, 
                                    mb: 1.5, 
                                    fontWeight: 600,
                                    background: 'var(--md-sys-color-surface)',
                                    padding: '2px 6px',
                                    borderRadius: '4px'
                                }}>
                                    {formatTime(item.time || item.timestamp)}
                                </Typography>

                                {/* 中间：圆点 */}
                                <div style={{ 
                                    width: isLatest ? '16px' : '12px', 
                                    height: isLatest ? '16px' : '12px', 
                                    borderRadius: '50%', 
                                    background: color,
                                    border: '3px solid var(--md-sys-color-surface)',
                                    boxShadow: isLatest ? `0 0 0 2px ${color}` : 'none',
                                    marginBottom: '12px',
                                    transition: 'all 0.2s'
                                }}></div>

                                {/* 下方：描述 */}
                                <Tooltip title={item.description} arrow placement="bottom">
                                    <div style={{ 
                                        textAlign: 'center', 
                                        width: '100%'
                                    }}>
                                        <Typography variant="body2" sx={{ 
                                            fontWeight: 700, 
                                            fontSize: '13px',
                                            whiteSpace: 'nowrap', 
                                            overflow: 'hidden', 
                                            textOverflow: 'ellipsis',
                                            maxWidth: '120px'
                                        }}>
                                            {item.type === 'earthquake' ? `M${item.magnitude} 地震` : item.description.split(' ')[0]}
                                        </Typography>
                                        <Typography variant="caption" sx={{ 
                                            opacity: 0.6, 
                                            display: 'block',
                                            fontSize: '11px',
                                            whiteSpace: 'nowrap', 
                                            overflow: 'hidden', 
                                            textOverflow: 'ellipsis',
                                            maxWidth: '120px'
                                        }}>
                                            {item.type === 'earthquake' ? item.description.split(' ').pop() : (item.description.length > 8 ? '...' : '')}
                                        </Typography>
                                    </div>
                                </Tooltip>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
