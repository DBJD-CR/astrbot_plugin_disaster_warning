const { Typography, Chip } = MaterialUI;
const { useMemo, useState, useEffect } = React;

function NewsTicker({ style }) {
    const { state } = useAppContext();
    const { events, config, dataLoaded } = state;
    const displayTimezone = config.displayTimezone || 'UTC+8';
    const [paused, setPaused] = useState(false);

    // 获取最新的 5 条事件，并处理数据格式
    // 默认 events 数组通常是按时间倒序排列的（最新的在前面）
    const tickerItems = useMemo(() => {
        if (!events || !Array.isArray(events) || events.length === 0) return [];
        
        // 过滤掉 1 小时前的旧事件
        const oneHourAgo = Date.now() - 3600000;
        const recentEvents = events.filter(e => {
            const t = new Date(e.time || e.timestamp).getTime();
            return t > oneHourAgo;
        });

        // 如果近期没有事件，返回空 (或者可以返回占位符)
        if (recentEvents.length === 0) return [];

        // 取最新的 5 条，并反转顺序 (为了让跑马灯从右边进来的是最新的)
        return recentEvents.slice(0, 5).reverse().map(event => ({
            id: event.event_id || `${event.time || event.timestamp}-${event.type}`,
            time: event.time || event.timestamp,
            type: event.type,
            desc: event.description || '无详细描述',
            mag: event.magnitude
        }));
    }, [events]);

    // 如果数据还没加载完成，显示加载状态
    if (!dataLoaded) {
        return (
            <div className="card" style={{
                ...style,
                padding: '0 24px',
                height: '56px',
                display: 'flex',
                alignItems: 'center',
                gap: '16px',
                overflow: 'hidden',
                background: state.theme === 'dark' ? 'var(--md-sys-color-surface)' : 'var(--md-sys-color-secondary-container)',
                marginBottom: '16px'
            }}>
                <div style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '8px', 
                    fontWeight: 800, 
                    minWidth: 'fit-content',
                    fontSize: '0.9rem'
                }}>
                    <span style={{ fontSize: '20px' }}>📡</span>
                    <span>实时动态</span>
                </div>
                <div className="skeleton" style={{ flex: 1, height: '24px', borderRadius: '12px' }}></div>
            </div>
        );
    }

    // 如果没有近期事件，显示提示
    if (tickerItems.length === 0) {
        return (
            <div className="card" style={{
                ...style,
                padding: '0 24px',
                height: '56px',
                display: 'flex',
                alignItems: 'center',
                gap: '16px',
                background: state.theme === 'dark' ? 'var(--md-sys-color-surface)' : 'var(--md-sys-color-secondary-container)',
                marginBottom: '16px'
            }}>
                <div style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '8px', 
                    fontWeight: 800, 
                    fontSize: '0.9rem'
                }}>
                    <span style={{ fontSize: '20px' }}>📡</span>
                    <span>实时动态</span>
                </div>
                <Typography style={{ opacity: 0.6, fontSize: '0.9rem' }}>
                    暂无近期事件推送
                </Typography>
            </div>
        );
    }

    const formatTime = (isoString) => {
        if (!isoString) return '';
        try {
            // 使用自定义时区格式化
            const formatted = formatTimeWithZone(isoString, displayTimezone, false);
            // 这里只需要时分，例如 "14:30"
            return formatted.split(' ')[1];
        } catch (e) {
            return '';
        }
    };

    const getIcon = (type) => {
        if (!type) return '📢';
        if (type.includes('earthquake')) return '🌍';
        if (type.includes('tsunami')) return '🌊';
        if (type.includes('weather')) return '⛈️';
        return '📢';
    };

    return (
        <div className="card news-ticker-card"
            style={{
                ...style,
                padding: '0 24px',
                height: '56px',
                display: 'flex',
                alignItems: 'center',
                gap: '16px',
                overflow: 'hidden',
                background: state.theme === 'dark' ? 'var(--md-sys-color-surface)' : 'var(--md-sys-color-secondary-container)',
                color: state.theme === 'dark' ? 'var(--md-sys-color-on-surface)' : 'var(--md-sys-color-on-secondary-container)',
                border: state.theme === 'dark' ? '1px solid rgba(255, 255, 255, 0.1)' : 'none',
                marginBottom: '16px' // 减小下边距 (24px -> 16px)，与其他卡片间距保持一致
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
                    animation: `scroll-left 30s linear infinite`,
                    animationPlayState: paused ? 'paused' : 'running',
                    whiteSpace: 'nowrap'
                }}>
                    {/* 重复渲染以确保无缝滚动 */}
                    {[...tickerItems, ...tickerItems].map((item, index) => {
                        // 仅在每一组的末尾（首尾相接处）添加分隔符
                        const isLastInGroup = (index + 1) % tickerItems.length === 0;
                        return (
                            <div key={`${item.id}-${index}`} style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', marginRight: isLastInGroup ? '24px' : '48px' }}>
                                <span style={{ opacity: 0.7, fontSize: '13px', fontWeight: 600 }}>{formatTime(item.time)}</span>
                                <span style={{ fontSize: '16px' }}>{getIcon(item.type)}</span>
                                
                                {/* 震级标签挪到前面 */}
                                {item.mag && (
                                    <Chip
                                        label={Number.isInteger(item.mag) ? `M ${item.mag}.0` : `M ${item.mag}`}
                                        size="small"
                                        sx={{
                                            height: '22px', // 稍微增高
                                            fontSize: '12px', // 增大字号
                                            fontWeight: 700,
                                            background: 'rgba(0,0,0,0.08)', // 稍微调淡背景，突出文字
                                            color: 'inherit',
                                            '& .MuiChip-label': { // 修正 Chip 内部 padding 导致的垂直不居中
                                                padding: '0 8px',
                                                lineHeight: 1
                                            }
                                        }}
                                    />
                                )}

                                <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1, marginTop: '2px' }}>
                                    {/* 移除标题开头可能存在的震级描述 */}
                                    {item.desc.replace(/^M[\d.]+\s*/, '')}
                                </Typography>

                                {isLastInGroup && (
                                    // 调整 margin-left 使分隔符向左偏移几个像素 (24px -> 20px)
                                    <span style={{ marginLeft: '20px', opacity: 0.3, fontWeight: 300, fontSize: '18px' }}>|</span>
                                )}
                            </div>
                        );
                    })}
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