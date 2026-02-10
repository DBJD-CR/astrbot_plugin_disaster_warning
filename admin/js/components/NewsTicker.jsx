const { Typography, Chip } = MaterialUI;
const { useMemo, useState, useEffect } = React;

function NewsTicker({ style }) {
    const { state } = useAppContext();
    const { events } = state;
    const [paused, setPaused] = useState(false);

    // 获取最新的 5 条事件，并处理数据格式
    const tickerItems = useMemo(() => {
        if (!events || !Array.isArray(events) || events.length === 0) return [];
        return events.slice(0, 5).map(event => ({
            id: event.event_id || Math.random().toString(),
            time: event.time || event.timestamp,
            type: event.type,
            desc: event.description || '无详细描述',
            mag: event.magnitude
        }));
    }, [events]);

    if (tickerItems.length === 0) return null;

    const formatTime = (isoString) => {
        if (!isoString) return '';
        try {
            return new Date(isoString).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        } catch (e) {
            return '';
        }
    };

    const getIcon = (type) => {
        if (!type) return '📢';
        if (type.includes('earthquake')) return '🌍';
        if (type.includes('tsunami')) return '🌊';
        if (type.includes('weather')) return '☁️';
        return '📢';
    };

    return (
        <div className="card" 
            style={{ 
                ...style, 
                padding: '0 24px', 
                height: '56px',
                display: 'flex', 
                alignItems: 'center', 
                gap: '16px',
                overflow: 'hidden',
                background: 'var(--md-sys-color-secondary-container)',
                color: 'var(--md-sys-color-on-secondary-container)',
                border: 'none',
                marginBottom: '24px' // 默认下边距
            }}
            onMouseEnter={() => setPaused(true)}
            onMouseLeave={() => setPaused(false)}
        >
            <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: '8px', 
                fontWeight: 800, 
                minWidth: 'fit-content',
                zIndex: 2,
                background: 'inherit',
                paddingRight: '12px',
                boxShadow: '10px 0 10px -5px rgba(0,0,0,0.1)'
            }}>
                <span style={{ fontSize: '18px' }}>🔔</span>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>最新动态</Typography>
            </div>

            <div style={{ 
                flex: 1, 
                overflow: 'hidden', 
                whiteSpace: 'nowrap',
                maskImage: 'linear-gradient(to right, transparent, black 20px, black 95%, transparent)'
            }}>
                <div style={{ 
                    display: 'inline-block',
                    animation: `scroll-left 20s linear infinite`,
                    animationPlayState: paused ? 'paused' : 'running',
                    whiteSpace: 'nowrap'
                }}>
                    {/* 重复渲染以确保无缝滚动 */}
                    {[...tickerItems, ...tickerItems].map((item, index) => (
                        <div key={`${item.id}-${index}`} style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', marginRight: '48px' }}>
                            <span style={{ opacity: 0.7, fontSize: '13px', fontWeight: 600 }}>{formatTime(item.time)}</span>
                            <span style={{ fontSize: '16px' }}>{getIcon(item.type)}</span>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                {item.desc}
                            </Typography>
                            {item.mag && (
                                <Chip 
                                    label={`M${item.mag}`} 
                                    size="small" 
                                    sx={{ 
                                        height: '20px', 
                                        fontSize: '11px', 
                                        fontWeight: 700,
                                        background: 'rgba(0,0,0,0.1)',
                                        color: 'inherit'
                                    }} 
                                />
                            )}
                        </div>
                    ))}
                </div>
            </div>

            <style>{`
                @keyframes scroll-left {
                    0% { transform: translateX(0); }
                    100% { transform: translateX(-50%); }
                }
            `}</style>
        </div>
    );
}