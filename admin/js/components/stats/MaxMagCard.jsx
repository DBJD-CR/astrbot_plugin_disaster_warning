const { Box, Typography, Chip } = MaterialUI;

/**
 * 历史最大地震信息卡片组件 (MaxMagCard)
 * 用于在统计仪表盘显眼位置陈列系统捕获并持久化记录的历史上震级最大的地震事件。
 * 包含特效浮水印、震级大数字渲染、发布源高亮标签、震中地名及发生时间。
 *
 * @param {Object} props
 * @param {Object} [props.style] 外部自定义样式
 * @param {string} [props.className=''] 额外类名
 */
function MaxMagCard({ style, className = '' }) {
    const { state } = useAppContext();
    const { stats, config } = state;
    const displayTimezone = config.displayTimezone || 'UTC+8';
    
    // 获取历史最大震级地震负载
    const maxMag = stats && stats.maxMagnitude ? stats.maxMagnitude : null;
    const magValue = Number(maxMag?.value);
    
    const displayMag = Number.isFinite(magValue) ? magValue.toFixed(1) : '--';
    const displayPlace = maxMag?.place_name || '暂无震中信息';

    /**
     * 格式化震中发震时间
     */
    const formatTime = (time) => {
        if (!time) return '未知时间';
        return formatTimeWithZone(time, displayTimezone, true);
    };

    // 状态：若尚无记录（如初次布署尚未拦截地震数据），展示空卡片提示
    if (!maxMag) {
        return (
            <div className={`card max-mag-card max-mag-card--empty ${className}`} style={style}>
                <span className="max-mag-card-empty-icon">📉</span>
                <Typography variant="body2" className="max-mag-card-empty-text">暂无最大震级记录</Typography>
            </div>
        );
    }

    return (
        <div className={`card max-mag-card ${className}`} style={style}>
            {/* 卡片右上角的大号火球半透明背景水印 */}
            <div className="max-mag-card-watermark">🔥</div>

            {/* 卡片头部 */}
            <div className="chart-card-header max-mag-card-header">
                <span className="stats-card-header-icon">🔥</span>
                <Typography variant="h6" className="max-mag-card-title">历史最大地震</Typography>
            </div>
            
            {/* 震级高亮大数行与数据源来源标签 */}
            <div className="max-mag-card-mag-row">
                <Typography variant="h3" className="max-mag-card-mag-value">
                    <span className="max-mag-card-mag-prefix">M</span>{displayMag}
                </Typography>
                {maxMag?.source && (
                    <Chip
                        label={formatSourceName(maxMag.source)}
                        size="small"
                        className="max-mag-card-source-chip"
                    />
                )}
            </div>

            {/* 震中地点名称 */}
            <Typography variant="body1" className="max-mag-card-place">
                {displayPlace}
            </Typography>
            
            {/* 发震时间详情 */}
            <Typography variant="body2" className="max-mag-card-time">
                {formatTime(maxMag?.time)}
            </Typography>
        </div>
    );
}
