const { Typography } = MaterialUI;

/**
 * 本地运行日志存储状态分析组件 (LogStatsCard)
 * 渲染系统日志统计指标，帮助运维管理人员实时观测日志体积与过滤系统的命中率。
 * 核心交互与特点：
 * 1. 提供“打开插件数据目录”的动作按钮，可异步调取系统自带的文件管理器展现本地数据位置。
 * 2. 统计并展示历史日志起止时间、总行数及生成的零散日志文件数。
 * 3. 动态展示日志占用磁盘的百分比与容量警示进度条（当使用量超出 70% 或 90% 时切换为警告黄色/危险红色）。
 * 4. 列出心跳、P2P无感震区、重复以及连接等类型的日志过滤器拦截命中数据统计。
 *
 * @param {Object} props
 * @param {Object} [props.style] 自定义样式
 */
function LogStatsCard({ style }) {
    const { state } = useAppContext();
    const statusApi = window.DisasterStatusApi;
    const { stats, config } = state;
    const { showToast } = useToast();
    
    // 获取日志分析状态
    const logStats = stats && stats.logStats ? stats.logStats : {};
    const hasLogStats = !!(stats && stats.logStats);

    /**
     * 辅助数值转换器
     */
    const toNumber = (value, fallback = 0) => {
        const n = Number(value);
        return Number.isFinite(n) ? n : fallback;
    };

    // 解构指标数据，做安全性校验
    const fileCount = toNumber(logStats.file_count, 0);
    const maxCapacity = toNumber(logStats.max_total_capacity_mb, 0);
    const usagePercent = toNumber(logStats.usage_percent, 0);
    const fileSize = toNumber(logStats.file_size_mb, 0);
    const startTime = logStats.date_range?.start || '暂无记录';
    const endTime = logStats.date_range?.end || '暂无记录';

    // 动态警报级别判定
    const usageTone = usagePercent > 90 ? 'danger' : (usagePercent > 70 ? 'warning' : 'normal');
    
    // 关联的 CSS 配色主题变量
    const usageToneVars = {
        normal: {
            '--log-stats-progress-color': 'var(--md-sys-color-primary)',
            '--log-stats-status-color': 'var(--md-sys-color-primary)',
        },
        warning: {
            '--log-stats-progress-color': 'var(--md-sys-color-tertiary, #F9A825)',
            '--log-stats-status-color': 'var(--md-sys-color-tertiary, #FFC107)',
        },
        danger: {
            '--log-stats-progress-color': 'var(--md-sys-color-error, #F44336)',
            '--log-stats-status-color': 'var(--md-sys-color-error, #F44336)',
        },
    };
    
    // 注入进度条宽度和颜色变量
    const progressStyle = {
        '--log-stats-progress-width': `${Math.min(usagePercent, 100)}%`,
        ...usageToneVars[usageTone],
    };

    /**
     * 向宿主发起请求：唤醒本地操作系统文件浏览器打开插件数据存储位置
     */
    const handleOpenLogDir = async () => {
        try {
            console.log('[LogStatsCard] Requesting open-log-dir via DisasterStatusApi');
            await statusApi.openLogDir(config.apiUrl || '');
            console.log('Log directory opened successfully');
        } catch (e) {
            console.error('Failed to open log dir:', e);
            // 捕获网络失败等问题并 Toast 弹窗
            showToast(`请求失败: ${e.message || '网络错误或服务不可达'}`, 'error');
        }
    };

    return (
        <div className="card log-stats-card" style={style}>
            {/* 卡片标题区与打开文件夹按钮 */}
            <div className="chart-card-header log-stats-header">
                <div className="log-stats-header-title">
                    <span className="log-stats-header-icon">📝</span>
                    <Typography variant="h6">系统日志统计</Typography>
                </div>
                <button
                    className="btn log-stats-open-button"
                    onClick={handleOpenLogDir}
                    title="在文件管理器中打开日志目录"
                >
                    <span className="log-stats-open-button__icon">📂</span>
                    打开插件数据目录
                </button>
            </div>
            
            {/* 空数据提示 */}
            {!hasLogStats && (
                <Typography variant="body2" className="log-stats-empty-text">
                    当前暂无日志统计数据，请等待日志文件生成后自动更新或开启日志记录功能。
                </Typography>
            )}

            {/* 日志指标参数网格 */}
            <div className="log-stats-grid" style={progressStyle}>
                {/* 1. 起止时间 */}
                <div className="log-stats-panel log-stats-panel--wide">
                    <Typography variant="caption" className="log-stats-muted">统计时间范围</Typography>
                    <Typography variant="body2" className="log-stats-strong-text">
                        {startTime} <span className="log-stats-range-separator">~</span> {endTime}
                    </Typography>
                </div>

                {/* 2. 日志总条数 */}
                <div className="log-stats-panel">
                    <Typography variant="caption" className="log-stats-muted">总条目</Typography>
                    <Typography variant="h6" className="log-stats-strong-heading">{logStats.total_entries || 0}</Typography>
                </div>
                
                {/* 3. 产生的文件文件数 */}
                <div className="log-stats-panel">
                    <Typography variant="caption" className="log-stats-muted">文件数量</Typography>
                    <Typography variant="h6" className="log-stats-strong-heading">{fileCount}</Typography>
                </div>

                {/* 4. 磁盘物理占用与进度条 */}
                <div className="log-stats-panel log-stats-panel--wide">
                    <div className="log-stats-storage-head">
                        <div className="log-stats-storage-status">
                            <div className="log-stats-status-dot"></div>
                            <Typography variant="caption" className="log-stats-muted">存储占用</Typography>
                            <Typography variant="caption" className="log-stats-percent-text">
                                ({usagePercent.toFixed(2)}%)
                            </Typography>
                        </div>
                        <Typography variant="caption" className="log-stats-strong-caption">
                            {fileSize.toFixed(2)} MB / {maxCapacity > 0 ? maxCapacity.toFixed(0) : '-'} MB
                        </Typography>
                    </div>
                    {/* 背景轨道与根据比例伸缩的彩条 */}
                    <div className="log-stats-progress-track">
                        <div className="log-stats-progress-bar"></div>
                    </div>
                </div>
                
                {/* 5. 过滤拦截器的统计分析报表 */}
                <div className="log-stats-panel log-stats-panel--wide">
                    <Typography variant="caption" className="log-stats-muted">过滤统计</Typography>
                    <div className="log-stats-filter-list">
                        <div className="log-stats-filter-row">
                            <Typography variant="body2" className="log-stats-body-sm">心跳包过滤</Typography>
                            <Typography variant="body2" className="log-stats-value-text">{logStats.filter_stats?.heartbeat_filtered || 0}</Typography>
                        </div>
                        <div className="log-stats-filter-row">
                            <Typography variant="body2" className="log-stats-body-sm">P2P节点过滤</Typography>
                            <Typography variant="body2" className="log-stats-value-text">{logStats.filter_stats?.p2p_areas_filtered || 0}</Typography>
                        </div>
                        <div className="log-stats-filter-row">
                            <Typography variant="body2" className="log-stats-body-sm">重复事件过滤</Typography>
                            <Typography variant="body2" className="log-stats-value-text">{logStats.filter_stats?.duplicate_events_filtered || 0}</Typography>
                        </div>
                        <div className="log-stats-filter-row">
                            <Typography variant="body2" className="log-stats-body-sm">连接状态过滤</Typography>
                            <Typography variant="body2" className="log-stats-value-text">{logStats.filter_stats?.connection_status_filtered || 0}</Typography>
                        </div>
                        {/* 过滤器拦截总数统计 */}
                        <div className="log-stats-filter-row log-stats-filter-row--total">
                            <Typography variant="body2" className="log-stats-body-sm log-stats-body-sm--strong">总计过滤</Typography>
                            <Typography variant="body2" className="log-stats-value-text log-stats-value-text--strong">{logStats.filter_stats?.total_filtered || 0}</Typography>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
