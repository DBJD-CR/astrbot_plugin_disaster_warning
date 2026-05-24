const { Typography, Chip } = MaterialUI;
const { useMemo, useState } = React;

/**
 * 实时事件跑马灯动态滚动组件 (NewsTicker)
 * 用于在服务状态页顶部横向滚屏播放最近一小时内系统接收到的最新灾害速报。
 * 核心设计：
 * 1. 自动过滤掉一小时前的旧事件，仅提取最新的 5 条事件进行滚屏播放。
 * 2. 悬停机制：鼠标 Hover 到卡片上时跑马灯暂停滚动，方便用户定睛阅读，移开后恢复播放。
 * 3. 跑马灯复制技术：数组内容自我复制双倍排列，辅以 CSS 动画实现完美无缝无断点首尾相接平滑滚动。
 * 4. 跑马灯内高亮震级标签，且智能剔除事件说明中自带的多余震级字符防止文字重叠。
 *
 * @param {Object} props
 * @param {Object} [props.style] 外部样式
 */
function NewsTicker({ style }) {
    const { state } = useAppContext();
    const { events, config, dataLoaded } = state;
    const displayTimezone = config.displayTimezone || 'UTC+8';
    
    // 状态：控制跑马灯是否由于鼠标悬停而暂停滚动
    const [paused, setPaused] = useState(false);
    const isDark = state.theme === 'dark';

    // 核心数据处理：过滤近期事件、限额5条并反转倒序以迎合跑马灯左进右出的播放体验
    const tickerItems = useMemo(() => {
        if (!events || !Array.isArray(events) || events.length === 0) return [];
        
        // 过滤保留 1 小时内发生的新事件
        const oneHourAgo = Date.now() - 3600000;
        const recentEvents = events.filter(e => {
            const t = parseEventTimeToDate(e.time || e.timestamp, e.source || '')?.getTime() || 0;
            return t > oneHourAgo;
        });

        if (recentEvents.length === 0) return [];

        // 截取最新 5 条，反转数组让时间最旧的在右，最新事件在尾部依次飘过
        return recentEvents.slice(0, 5).reverse().map(event => ({
            id: event.event_id || `${event.time || event.timestamp}-${event.type}`,
            time: event.time || event.timestamp,
            type: event.type,
            source: event.source || '',
            desc: event.description || '无详细描述',
            mag: event.magnitude
        }));
    }, [events]);

    // 1. 状态：网络数据未就绪，渲染跑马灯骨架屏结构
    if (!dataLoaded) {
        return (
            <div className={`card news-ticker-card news-ticker-card--loading ${isDark ? 'is-dark' : 'is-light'}`} style={style}>
                <div className="news-ticker-head news-ticker-head--loading">
                    <span className="news-ticker-head__icon news-ticker-head__icon--large">📡</span>
                    <span>实时动态</span>
                </div>
                <div className="skeleton news-ticker-skeleton"></div>
            </div>
        );
    }

    // 2. 状态：若一小时内无任何预警发生，渲染静默提示状态
    if (tickerItems.length === 0) {
        return (
            <div className={`card news-ticker-card news-ticker-card--empty ${isDark ? 'is-dark' : 'is-light'}`} style={style}>
                <div className="news-ticker-head news-ticker-head--loading">
                    <span className="news-ticker-head__icon news-ticker-head__icon--large">📡</span>
                    <span>实时动态</span>
                </div>
                <Typography className="news-ticker-empty-text">
                    暂无近期事件推送
                </Typography>
            </div>
        );
    }

    /**
     * 格式化预警时间，保留 HH:mm 格式
     */
    const formatTime = (isoString, source) => {
        if (!isoString) return '';
        try {
            const formatted = formatTimeWithZone(isoString, displayTimezone, false, source || '');
            return formatted.split(' ')[1]; // 拆分日期，仅获取时间部分
        } catch (e) {
            return '';
        }
    };

    /**
     * 根据灾害类型获取 Emoji 视觉标示
     */
    const getIcon = (type) => {
        if (!type) return '📢';
        if (type.includes('earthquake')) return '🌍';
        if (type.includes('tsunami')) return '🌊';
        if (type.includes('weather')) return '⛈️';
        return '📢';
    };

    return (
        <div
            className={`card news-ticker-card ${isDark ? 'is-dark' : 'is-light'}`}
            style={style}
            onMouseEnter={() => setPaused(true)}
            onMouseLeave={() => setPaused(false)}
        >
            {/* 左侧固定标题 */}
            <div className="news-ticker-head">
                <span className="news-ticker-head__icon">🔔</span>
                <Typography variant="subtitle2" className="news-ticker-head__title">最新动态</Typography>
            </div>

            {/* 跑马灯滚动遮罩视窗 */}
            <div className="news-ticker-marquee-mask">
                {/* 滚动长轴轨道（通过 copy 两份数据序列以达成无缝首尾相接效果） */}
                <div className={`news-ticker-marquee-track ${paused ? 'is-paused' : ''}`}>
                    {[...tickerItems, ...tickerItems].map((item, index) => {
                        // 标记这一轮数据包的最后一项，用以在尾部插入 | 分隔符线
                        const isLastInGroup = (index + 1) % tickerItems.length === 0;
                        return (
                            <div 
                                key={`${item.id}-${index}`} 
                                className={`news-ticker-item ${isLastInGroup ? 'news-ticker-item--last' : ''}`}
                            >
                                <span className="news-ticker-time">{formatTime(item.time, item.source)}</span>
                                <span className="news-ticker-type-icon">{getIcon(item.type)}</span>
                                
                                {/* 震级标 (若包含震级) */}
                                {item.mag && (
                                    <Chip
                                        label={Number.isInteger(item.mag) ? `M ${item.mag}.0` : `M ${item.mag}`}
                                        size="small"
                                        className={`news-ticker-mag-chip ${isDark ? 'is-dark' : 'is-light'}`}
                                    />
                                )}

                                <Typography
                                    component="span"
                                    variant="body2"
                                    className="news-ticker-desc"
                                >
                                    {/* 去除首部可能冗余的 Mxx 格式前缀，防范视觉重复 */}
                                    {item.desc.replace(/^M[\d.]+\s*/, '')}
                                </Typography>

                                {isLastInGroup && (
                                    <span className="news-ticker-divider">|</span>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
