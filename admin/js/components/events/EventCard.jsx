const { Typography } = MaterialUI;

/**
 * 灾害事件单卡片渲染组件 (EventCard)
 * 渲染单个灾害/预警的详细摘要信息，支持地震（速报/预警）、海啸、气象预警等多种灾害类型。
 * 针对不同预警类型，展示对应的专属徽标 (Badge) 以及气象站图标，并支持卡片伸缩折叠展示多报更新。
 *
 * @param {Object} props
 * @param {Object} props.event 事件的核心数据负载对象
 * @param {string} props.displayTimezone 全局配置的展示时区，如 'UTC+8'
 * @param {boolean} [props.isHistory=false] 是否渲染为历史列表小尺寸卡片样式
 * @param {boolean} [props.isExpandable=false] 卡片是否包含多报更新并可展开折叠
 * @param {boolean} [props.isExpanded=false] 当前是否处于展开状态
 * @param {number|null} [props.reportIndex=null] 多报更新时的历史期数标签
 */
function EventCard({ 
    event, 
    displayTimezone, 
    isHistory = false, 
    isExpandable = false, 
    isExpanded = false, 
    reportIndex = null 
}) {
    const { buildEarthquakeTitle, getEarthquakeBadgeContent } = window.EventFormatSerialization || window.EventFormatters;
    const evt = event || {};
    const eventType = evt.type || evt._groupType || '';
    
    // 逻辑判别不同的防灾事件类型
    const isEarthquake = eventType === 'earthquake' || eventType === 'earthquake_warning';
    const isTsunami = eventType === 'tsunami';
    const isWeather = eventType === 'weather_alarm';
    
    // 生成动态标题文本：地震调用特定算法，气象优先展示 subtitle，其他事件展示 description
    const displayTitle = isEarthquake
        ? buildEarthquakeTitle(evt)
        : (isWeather ? (evt.subtitle || evt.description || '未知位置') : (evt.description || '未知位置'));

    // 初始化徽标内容与对应 CSS 类名
    let badgeContent = '❓';
    let badgeClass = 'badge-unknown';
    let weatherIconUrl = null;
    let earthquakeBadgeMeta = null;

    // 1. 地震：获取烈度/震级元数据与对应危险警示判色
    if (isEarthquake) {
        earthquakeBadgeMeta = getEarthquakeBadgeContent(evt);
        badgeContent = earthquakeBadgeMeta?.text || '--';
        badgeClass = 'badge-earthquake';
    } 
    // 2. 海啸：采用海浪图标 🌊
    else if (isTsunami) {
        badgeContent = '🌊';
        badgeClass = 'badge-tsunami';
    } 
    // 3. 气象预警：采用特定预警图标或 fallback 云朵 ☁️
    else if (isWeather) {
        badgeContent = '☁️';
        badgeClass = 'badge-weather';
        const normalizedIconUrl = typeof evt.icon_url === 'string' ? evt.icon_url.trim() : '';
        const weatherTypeCode = String(evt.weather_type_code || '').trim();
        // 若服务端未传 icon_url，则从国家气象中心镜像获取对应预警代码的矢量图
        weatherIconUrl = normalizedIconUrl || (weatherTypeCode ? `https://image.nmc.cn/assets/img/alarm/${weatherTypeCode}.png` : null);
    }

    // 计算报告第几期 (第几报) 的文案
    let reportLabel = '';
    if (reportIndex !== null && reportIndex > 0) {
        reportLabel = `第 ${reportIndex} 报`;
    } else if (evt.report_num) {
        reportLabel = `第 ${evt.report_num} 报`;
    }

    // 拼装卡片的主容器 Class 类名
    const cardClassName = [
        'event-card',
        isExpandable ? 'clickable' : '',
        isHistory ? 'event-card-history' : '',
    ].filter(Boolean).join(' ');

    // 拼装左侧徽标容器 Class 类名，关联震度警报的危险背景色类
    const badgeClassName = [
        'mag-badge',
        badgeClass,
        isHistory ? 'mag-badge-history' : '',
        weatherIconUrl ? 'mag-badge-weather-icon' : '',
        earthquakeBadgeMeta ? 'mag-badge-earthquake-meta' : '',
        earthquakeBadgeMeta?.toneClass ? `event-badge-tone-${earthquakeBadgeMeta.toneClass}` : '',
    ].filter(Boolean).join(' ');

    // 针对气象预警特殊重置徽标的高宽与背景样式
    const badgeStyle = weatherIconUrl ? {
        width: isHistory ? '40px' : '56px',
        height: isHistory ? '40px' : '56px',
        padding: 0,
        borderRadius: '0',
        backgroundColor: 'transparent',
        boxShadow: 'none',
        overflow: 'visible',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
    } : undefined;

    return (
        <div className={cardClassName}>
            {/* 左侧：特征标识徽标区 */}
            <div className={badgeClassName} style={badgeStyle}>
                {weatherIconUrl ? (
                    // 渲染气象预警图标
                    <img
                        src={weatherIconUrl}
                        alt={badgeContent}
                        className="event-weather-icon"
                        style={{
                            width: '100%',
                            height: '100%',
                            objectFit: 'contain',
                            objectPosition: 'center',
                            transform: 'scale(1.5)',
                            display: 'block',
                        }}
                        onError={(e) => {
                            // 若网络图片加载失败，退回到默认 Unicode 文字徽标
                            const badgeEl = e.target.parentElement;
                            e.target.remove();
                            if (badgeEl) {
                                badgeEl.classList.add('mag-badge-weather-icon-fallback');
                                badgeEl.textContent = badgeContent;
                            }
                        }}
                    />
                ) : earthquakeBadgeMeta ? (
                    // 渲染结构化的地震速报标签（如：上方烈度，下方震级）
                    <>
                        <span className="event-earthquake-badge-label">
                            {earthquakeBadgeMeta.label}
                        </span>
                        <span className="event-earthquake-badge-value">
                            {badgeContent}
                        </span>
                    </>
                ) : (
                    // 其他类型展示默认文字/Emoji
                    badgeContent
                )}
            </div>

            {/* 右侧：事件核心文字信息区 */}
            <div className="event-main">
                {/* 第一行：标题与报告期数 */}
                <div className="event-title-row">
                    <Typography 
                        variant={isHistory ? 'body2' : 'h6'} 
                        className="event-title-text"
                    >
                        {displayTitle}
                    </Typography>
                    {reportLabel && (
                        <span className={`event-report-label ${reportIndex !== null && reportIndex > 0 ? 'is-history-report' : ''}`}>
                            {reportLabel}
                        </span>
                    )}
                </div>
                {/* 第二行：发布时间、来源发布机构等元数据 */}
                <div className="event-meta">
                    <span className="event-meta-item">
                        🕒 {formatTimeFriendly(evt.time || evt.timestamp, displayTimezone, evt.source || '')}
                    </span>
                    <span className="event-meta-item">
                        <span className="event-meta-separator">•</span>
                        📡 {formatSourceName(evt.source_id || evt.source)}
                    </span>
                </div>
            </div>

            {/* 极右侧：多更新折叠控制提示（若包含） */}
            {isExpandable && (
                <div className="update-badge">
                    <span className="update-count">
                        {isExpanded ? '收起' : `${evt.updateCount || ''} 条更新`}
                    </span>
                    <span className="update-icon">{isExpanded ? '▲' : '▼'}</span>
                </div>
            )}
        </div>
    );
}
