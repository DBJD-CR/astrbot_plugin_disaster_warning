const { Typography } = MaterialUI;

/**
 * 地震或灾害事件多报更新时间轴面板组件 (EventGroupTimeline)
 * 当某次地震存在多次修正速报或更新时，用户点击卡片会展开此组件。
 * 该组件以垂直时间线形式，由新到旧列出该事件组名下接收到的所有历史报告，
 * 并展示各期报告中的详细震级、震源深度以及对应的地震烈度/震度标志。
 *
 * @param {Object} props
 * @param {Object} props.group 包含同一事件关联的 events 列表与最新一条 event 记录的分组数据
 * @param {string} props.displayTimezone 全局配置的时区，如 'UTC+8'
 * @param {Function} props.onCollapse 折叠收起该面板的回调函数
 */
function EventGroupTimeline({ group, displayTimezone, onCollapse }) {
    const { getDisplayTimeValue, formatMagnitudeBadge, getEarthquakeBadgeContent } = window.EventFormatters;
    const totalReports = group.events.length;

    return (
        <div className="event-group-expanded event-group-expanded-panel">
            {/* 收起控制条 */}
            <button
                onClick={onCollapse}
                onKeyDown={(e) => { 
                    if (e.key === 'Enter' || e.key === ' ') { 
                        e.preventDefault(); 
                        onCollapse(); 
                    } 
                }}
                aria-expanded={true}
                className="event-group-collapse-button"
            >
                <Typography variant="body2" className="event-group-collapse-text">
                    共 {totalReports} 次更新
                </Typography>
                <div className="update-badge">
                    <span>收起</span>
                    <span className="update-icon">▲</span>
                </div>
            </button>

            {/* 垂直时间线容器 */}
            <div className="event-group-timeline">
                {/* 垂直中心轴线 */}
                <div className="event-group-timeline-line"></div>
                
                {/* 遍历输出每一报的历史明细 */}
                {group.events.map((evt, idx) => {
                    // 自下而上递增计算逻辑上的第几报，若数据包自带实际 report_num 则以其为准
                    const reportIndex = totalReports - idx;
                    const actualReportNum = Number(evt?.report_num);
                    const hasValidReportNum = Number.isInteger(actualReportNum) && actualReportNum > 0;
                    const displayReportNum = hasValidReportNum ? actualReportNum : reportIndex;
                    
                    // 标识最新的这一期（第0项）
                    const isLatest = idx === 0;
                    const rowType = evt.type || group.latestEvent.type || '';
                    const isEarthquake = rowType === 'earthquake' || rowType === 'earthquake_warning';
                    
                    // 获取报告中的地震参数
                    const rowDepth = evt.depth ?? group.latestEvent.depth;
                    const rowMagnitude = evt.magnitude ?? group.latestEvent.magnitude;
                    const rowMagnitudeText = formatMagnitudeBadge(rowMagnitude);
                    
                    // 提取此报对应的地震烈度徽标元数据
                    const rowBadgeMeta = getEarthquakeBadgeContent({ 
                        ...group.latestEvent, 
                        ...evt, 
                        _groupMagnitude: group.latestEvent.magnitude 
                    });

                    return (
                        <div 
                            key={idx} 
                            className={`event-group-timeline-item ${idx === group.events.length - 1 ? 'is-last' : ''}`}
                        >
                            {/* 时间线节点小圆点 */}
                            <div className={`event-group-timeline-dot ${isLatest ? 'is-latest' : ''}`}></div>
                            
                            {/* 单期报告内容排版行 */}
                            <div className="event-group-timeline-row">
                                {/* 若是地震类型，渲染对应的烈度徽标 */}
                                {isEarthquake && <IntensityBadge meta={rowBadgeMeta} />}
                                
                                <div className="event-group-timeline-main">
                                    {/* 报告数、最新标及发生时间 */}
                                    <div className="event-group-timeline-meta-row">
                                        <span className={`event-group-report-chip ${isLatest ? 'is-latest' : ''}`}>
                                            第 {displayReportNum} 报
                                        </span>
                                        {isLatest && <span className="event-group-latest-chip">最新</span>}
                                        <Typography variant="body2" className="event-group-time-text">
                                            🕒 {formatTimeFriendly(getDisplayTimeValue(evt, true), displayTimezone, evt.source || group.latestEvent.source || '')}
                                        </Typography>
                                    </div>
                                    
                                    {/* 地震专用数值参数区（震级、深度） */}
                                    {isEarthquake && (
                                        <div className="event-group-quake-details">
                                            <Typography variant="body2" className="event-group-quake-text event-group-quake-text--strong">
                                                震级: {rowMagnitudeText !== '--' ? `M ${rowMagnitudeText}` : '调查中'}
                                            </Typography>
                                            <Typography variant="body2" className="event-group-quake-text">
                                                深度: {(rowDepth !== undefined && rowDepth !== null) ? `${rowDepth} km` : '未知'}
                                            </Typography>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

/**
 * 局部时序烈度徽标子组件 (IntensityBadge)
 *
 * @param {Object} props
 * @param {Object} props.meta 包含 label (机构) 与 text (烈度数值/符号) 的配置
 */
function IntensityBadge({ meta }) {
    const toneClass = meta?.toneClass ? `event-badge-tone-${meta.toneClass}` : 'event-badge-tone-unknown';
    return (
        <div className={`event-group-intensity-badge ${toneClass}`}>
            <span className="event-group-intensity-label">{meta.label}</span>
            <span className="event-group-intensity-value">{meta.text}</span>
        </div>
    );
}
