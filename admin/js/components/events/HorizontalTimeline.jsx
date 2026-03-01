const { Typography, Chip, Tooltip } = MaterialUI;
const { useMemo, useRef, useEffect, useState, useCallback } = React;

/**
 * 重大事件时间轴组件
 * 横向展示最近的重大事件 (M>=5.0 或 红色/橙色预警 或 海啸)
 * 数据直接从 /api/events/major 获取，支持历史回溯
 */
function HorizontalTimeline({ style }) {
    const { state } = useAppContext();
    const { config } = state;
    const displayTimezone = config.displayTimezone || 'UTC+8';

    const [majorEvents, setMajorEvents] = useState([]);

    const fetchMajorEvents = useCallback(() => {
        fetch('/api/events/major?limit=100')
            .then(res => res.json())
            .then(data => {
                if (Array.isArray(data.events)) {
                    setMajorEvents(data.events);
                }
            })
            .catch(err => console.error('Failed to fetch major events:', err));
    }, []);

    // 初始加载
    useEffect(() => {
        fetchMajorEvents();
    }, [fetchMajorEvents]);

    // 有新事件推送时刷新（fetchMajorEvents 由 useCallback([]) 生成，引用稳定）
    useEffect(() => {
        fetchMajorEvents();
    }, [state.events, fetchMajorEvents]);

    // 按事件时间排序（正序：旧→新，用于时间轴从左到右展示）
    const timelineItems = useMemo(() => {
        return majorEvents
            .slice()
            .sort((a, b) => {
                const timeA = parseEventTimeToDate(a.time || a.timestamp, a.source || '')?.getTime() || 0;
                const timeB = parseEventTimeToDate(b.time || b.timestamp, b.source || '')?.getTime() || 0;
                return timeA - timeB;
            });
    }, [majorEvents]);

    const scrollContainerRef = useRef(null);
    // 用于标记是否是用户触发的滚动，防止自动滚动逻辑干扰
    const isUserScrolling = useRef(false);

    // 导航按钮增强：更大步进、长按连续滚动、双击直达边界
    const BUTTON_SCROLL_STEP = 420;
    const HOLD_SCROLL_STEP = 140;
    const HOLD_SCROLL_INTERVAL = 45;
    const HOLD_START_DELAY = 220;

    const holdStartTimerRef = useRef(null);
    const holdIntervalRef = useRef(null);

    const stopContinuousScroll = useCallback(() => {
        if (holdStartTimerRef.current) {
            clearTimeout(holdStartTimerRef.current);
            holdStartTimerRef.current = null;
        }
        if (holdIntervalRef.current) {
            clearInterval(holdIntervalRef.current);
            holdIntervalRef.current = null;
        }
        // 稍作延迟再释放“用户正在交互”标志，避免和自动滚动互相打架
        setTimeout(() => {
            isUserScrolling.current = false;
        }, 120);
    }, []);

    const scrollByStep = useCallback((direction) => {
        if (!scrollContainerRef.current) return;
        isUserScrolling.current = true;
        scrollContainerRef.current.scrollBy({
            left: direction * BUTTON_SCROLL_STEP,
            behavior: 'smooth'
        });
        setTimeout(() => {
            isUserScrolling.current = false;
        }, 420);
    }, []);

    const scrollToEdge = useCallback((toRight) => {
        if (!scrollContainerRef.current) return;
        isUserScrolling.current = true;
        scrollContainerRef.current.scrollTo({
            left: toRight ? scrollContainerRef.current.scrollWidth : 0,
            behavior: 'smooth'
        });
        setTimeout(() => {
            isUserScrolling.current = false;
        }, 520);
    }, []);

    const startContinuousScroll = useCallback((direction) => {
        if (!scrollContainerRef.current) return;

        // 防止多次触发导致重复定时器
        stopContinuousScroll();
        isUserScrolling.current = true;

        // 长按达到阈值后启动连续滚动
        holdStartTimerRef.current = setTimeout(() => {
            holdIntervalRef.current = setInterval(() => {
                if (!scrollContainerRef.current) return;
                scrollContainerRef.current.scrollBy({
                    left: direction * HOLD_SCROLL_STEP,
                    behavior: 'auto'
                });
            }, HOLD_SCROLL_INTERVAL);
        }, HOLD_START_DELAY);
    }, [stopContinuousScroll]);

    // 组件卸载时清理定时器
    useEffect(() => {
        return () => {
            stopContinuousScroll();
        };
    }, [stopContinuousScroll]);

    // 在数据更新时自动滚动到最右侧
    // 逻辑优化：只在组件首次挂载 或 timelineItems 长度增加（有新事件）时滚动
    // 避免因其他原因导致的重渲染触发滚动，干扰用户查看历史
    const prevItemsLengthRef = useRef(0);

    useEffect(() => {
        const hasNewItems = timelineItems.length > prevItemsLengthRef.current;
        const isFirstRender = prevItemsLengthRef.current === 0;
        
        // 更新长度记录
        prevItemsLengthRef.current = timelineItems.length;

        if (scrollContainerRef.current && !isUserScrolling.current) {
            // 只有在首次加载 或 有新数据追加时 才自动滚动
            if (isFirstRender || hasNewItems) {
                setTimeout(() => {
                    if (!isUserScrolling.current && scrollContainerRef.current) {
                        scrollContainerRef.current.scrollLeft = scrollContainerRef.current.scrollWidth;
                    }
                }, 100);
            }
        }
    }, [timelineItems]);

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

    const formatTime = (isoString, source) => {
        if (!isoString) return '';
        try {
            // 使用新的时区处理函数，不包含年份
            const formatted = formatTimeWithZone(isoString, displayTimezone, false, source || '');
            // 格式化后的结果已经是 MM-DD HH:mm，这里为了样式紧凑，我们可以把 - 换成 /
            return formatted.replace('-', '/');
        } catch (e) {
            return '';
        }
    };

    const getEventColor = (event) => {
        // 地震颜色判断
        if (event.type === 'earthquake') {
            if (event.magnitude >= 8.0) return '#6A1B9A'; // 紫色
            if (event.magnitude >= 7.0) return '#D32F2F'; // 红色
            if (event.magnitude >= 6.0) return '#FB8C00'; // 橙色
            return '#FDD835'; // 黄色
        }

        // 海啸颜色判断
        if (event.type === 'tsunami') {
            const level = event.level || '';
            const desc = event.description || '';
            if (level.includes('红') || level.includes('Major') || desc.includes('红')) return '#D32F2F'; // 红色/大海啸警报
            if (level.includes('橙') || level.includes('Warning') || desc.includes('橙')) return '#FB8C00'; // 橙色/海啸警报
            if (level.includes('黄') || level.includes('Watch') || desc.includes('黄')) return '#FDD835'; // 黄色/海啸注意报
            return '#2196F3'; // 默认蓝色
        }

        // 气象预警颜色判断
        // 优先尝试从 level 字段判断
        if (event.level) {
            if (event.level.includes('红')) return '#D32F2F';
            if (event.level.includes('橙')) return '#FB8C00';
            if (event.level.includes('黄')) return '#FDD835';
            if (event.level.includes('蓝')) return '#2196F3';
        }
        
        // 回退到描述匹配
        const desc = event.description || '';
        if (desc.includes('红')) return '#D32F2F';
        if (desc.includes('橙')) return '#FB8C00';
        if (desc.includes('黄')) return '#FDD835';
        if (desc.includes('蓝')) return '#2196F3';
        
        return 'var(--md-sys-color-primary)';
    };

    const getSourceLabel = (event) => {
        return formatSourceName(event?.source_id || event?.source || 'unknown');
    };

    return (
        <div className="card" style={{ ...style, display: 'flex', flexDirection: 'column', overflowX: 'auto', position: 'relative' }}>
            <div className="chart-card-header" style={{ marginBottom: '24px' }}>
                <span style={{ fontSize: '20px' }}>⏳</span>
                <Typography variant="h6">重大事件回溯</Typography>
            </div>

            {/* 左右导航按钮 */}
            <>
                <div style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', zIndex: 10 }}>
                            <div
                                onClick={() => scrollByStep(-1)}
                                onDoubleClick={() => scrollToEdge(false)}
                                onMouseDown={() => startContinuousScroll(-1)}
                                onMouseUp={stopContinuousScroll}
                                onMouseLeave={(e) => {
                                    stopContinuousScroll();
                                    e.currentTarget.style.opacity = 0.6;
                                }}
                                onTouchStart={() => startContinuousScroll(-1)}
                                onTouchEnd={stopContinuousScroll}
                                onTouchCancel={stopContinuousScroll}
                                title="单击：向左快速移动｜长按：连续移动｜双击：跳到最左"
                                style={{
                                    width: '32px',
                                    height: '32px',
                                    borderRadius: '50%',
                                    backgroundColor: 'rgba(255, 255, 255, 0.8)',
                                    boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    cursor: 'pointer',
                                    color: 'var(--md-sys-color-on-surface)',
                                    backdropFilter: 'blur(4px)',
                                    opacity: 0.6,
                                    transition: 'opacity 0.2s',
                                }}
                                onMouseEnter={(e) => e.currentTarget.style.opacity = 1}
                            >
                                <span style={{ fontSize: '18px', fontWeight: 'bold' }}>‹</span>
                            </div>
                        </div>

                        <div style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', zIndex: 10 }}>
                            <div
                                onClick={() => scrollByStep(1)}
                                onDoubleClick={() => scrollToEdge(true)}
                                onMouseDown={() => startContinuousScroll(1)}
                                onMouseUp={stopContinuousScroll}
                                onMouseLeave={(e) => {
                                    stopContinuousScroll();
                                    e.currentTarget.style.opacity = 0.6;
                                }}
                                onTouchStart={() => startContinuousScroll(1)}
                                onTouchEnd={stopContinuousScroll}
                                onTouchCancel={stopContinuousScroll}
                                title="单击：向右快速移动｜长按：连续移动｜双击：跳到最右"
                                style={{
                                    width: '32px',
                                    height: '32px',
                                    borderRadius: '50%',
                                    backgroundColor: 'rgba(255, 255, 255, 0.8)',
                                    boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    cursor: 'pointer',
                                    color: 'var(--md-sys-color-on-surface)',
                                    backdropFilter: 'blur(4px)',
                                    opacity: 0.6,
                                    transition: 'opacity 0.2s',
                                }}
                                onMouseEnter={(e) => e.currentTarget.style.opacity = 1}
                            >
                                <span style={{ fontSize: '18px', fontWeight: 'bold' }}>›</span>
                            </div>
                        </div>

                        <div
                            ref={scrollContainerRef}
                            className="horizontal-timeline-scroll-container"
                            style={{
                                flex: 1,
                                display: 'flex',
                                alignItems: 'center',
                                position: 'relative',
                                padding: '20px 0',
                                overflowX: 'auto',
                                overflowY: 'hidden',
                                width: '100%',
                                cursor: 'grab',
                                // 隐藏滚动条但保留功能 (兼容性处理)
                                scrollbarWidth: 'none',  // Firefox
                                msOverflowStyle: 'none', // IE/Edge
                            }}
                            onMouseDown={(e) => {
                                isUserScrolling.current = true; // 标记用户正在交互
                                const ele = e.currentTarget;
                                ele.style.cursor = 'grabbing';
                                ele.style.userSelect = 'none';
                    
                                let pos = {
                                    left: ele.scrollLeft,
                                    x: e.clientX,
                                };

                                const mouseMoveHandler = (e) => {
                                    const dx = e.clientX - pos.x;
                                    ele.scrollLeft = pos.left - dx;
                                };

                                const mouseUpHandler = () => {
                                    isUserScrolling.current = false; // 交互结束
                                    ele.style.cursor = 'grab';
                                    ele.style.removeProperty('user-select');
                                    document.removeEventListener('mousemove', mouseMoveHandler);
                                    document.removeEventListener('mouseup', mouseUpHandler);
                                };

                                document.addEventListener('mousemove', mouseMoveHandler);
                                document.addEventListener('mouseup', mouseUpHandler);
                            }}
                            // 监听触摸事件，同样标记用户交互
                            onTouchStart={() => { isUserScrolling.current = true; }}
                            onTouchEnd={() => { isUserScrolling.current = false; }}
                        >
                            {/* 注入样式以隐藏 Webkit 滚动条 */}
                            <style>{`
                                .horizontal-timeline-scroll-container::-webkit-scrollbar {
                                    display: none;
                                }
                            `}</style>
                {/* 容器用于包裹内容，确保宽度足够 */}
                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    minWidth: 'min-content', // 宽度随内容撑开
                    padding: '0 20px',
                    position: 'relative',
                    height: '100%'
                }}>
                    {/* 轴线 - 固定位置 */}
                    <div style={{
                        position: 'absolute',
                        top: '65px', // 根据上方时间(30+8) + 圆点中心(8) 计算大约位置，根据实际微调
                        left: '20px',
                        right: '20px',
                        height: '2px',
                        background: 'var(--md-sys-color-outline-variant)',
                        zIndex: 0
                    }}></div>

                            {/* 事件节点 */}
                            {timelineItems.map((item, index) => {
                                const color = getEventColor(item);
                                const sourceLabel = getSourceLabel(item);

                                return (
                                    <div key={index} style={{
                                        display: 'flex',
                                        flexDirection: 'column',
                                        alignItems: 'center',
                                        position: 'relative',
                                        width: '140px', // 稍微增加宽度
                                        flexShrink: 0, // 防止被压缩
                                        zIndex: 1,
                                        height: '100%', // 占满高度
                                        justifyContent: 'flex-start', // 顶部对齐
                                        paddingTop: '20px' // 给上方留点空间
                                    }}>
                                {/* 上方：时间 */}
                                <div style={{
                                    height: '30px', // 固定高度区域
                                    display: 'flex',
                                    alignItems: 'flex-end',
                                    marginBottom: '8px'
                                }}>
                                    <Typography variant="caption" sx={{
                                        opacity: 0.7,
                                        fontWeight: 600,
                                        background: 'var(--md-sys-color-surface)',
                                        padding: '2px 6px',
                                        borderRadius: '4px'
                                    }}>
                                        {formatTime(item.time || item.timestamp, item.source)}
                                    </Typography>
                                </div>

                                {/* 中间：圆点 */}
                                <div style={{
                                    width: '16px',
                                    height: '16px',
                                    borderRadius: '50%',
                                    backgroundColor: color, // 使用 backgroundColor 确保颜色生效
                                    border: '3px solid var(--md-sys-color-surface)',
                                    boxShadow: `0 0 0 2px ${color}`,
                                    marginBottom: '12px',
                                    transition: 'all 0.2s',
                                    zIndex: 2, // 提高层级，防止被轴线遮挡
                                    flexShrink: 0 // 防止圆点被压缩
                                }}></div>

                                {/* 下方：描述 */}
                                <Tooltip title={item.description} arrow placement="bottom">
                                    <div style={{
                                        textAlign: 'center',
                                        width: '100%',
                                        display: 'flex',
                                        flexDirection: 'column',
                                        alignItems: 'center'
                                    }}>
                                        <Typography variant="body2" sx={{ 
                                            fontWeight: 700, 
                                            fontSize: '13px',
                                            whiteSpace: 'nowrap', 
                                            overflow: 'hidden', 
                                            textOverflow: 'ellipsis',
                                            maxWidth: '120px',
                                            color: color // 标题颜色跟随事件等级
                                        }}>
                                            {/* 标题显示优化：地震显示震级，气象显示核心类型 */}
                                            {(() => {
                                                if (item.type === 'earthquake') {
                                                    return Number.isInteger(item.magnitude) ? `M ${item.magnitude}.0` : `M ${item.magnitude}`;
                                                } else if (item.type === 'tsunami') {
                                                    return item.title || '海啸预警';
                                                } else {
                                                    // 气象预警：尝试提取“发布”和“信号”之间的内容
                                                    const match = item.description ? item.description.match(/发布(.*?)信号/) : null;
                                                    if (match && match[1]) {
                                                        return match[1];
                                                    }
                                                    // 回退逻辑
                                                    return (item.description || '未知事件').split(' ')[0].slice(0, 8);
                                                }
                                            })()}
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
                                            {/* 副标题优化：地震显示地点，气象显示完整描述（增加字数限制） */}
                                            {(() => {
                                                const desc = item.description || '';
                                                return item.type === 'earthquake'
                                                    ? (desc.includes(' ') ? desc.split(' ').slice(1).join(' ') : desc.replace(/^M[\d.]+\s*/, ''))
                                                    : (desc.length > 12 ? desc.substring(0, 12) + '...' : desc);
                                            })()}
                                        </Typography>
                                        <Typography variant="caption" sx={{
                                            opacity: 0.45,
                                            display: 'block',
                                            fontSize: '10px',
                                            whiteSpace: 'nowrap',
                                            overflow: 'hidden',
                                            textOverflow: 'ellipsis',
                                            maxWidth: '120px',
                                            mt: 0.25
                                        }}>
                                            📡 {sourceLabel}
                                        </Typography>
                                    </div>
                                </Tooltip>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
            </>
        </div>
    );
}
