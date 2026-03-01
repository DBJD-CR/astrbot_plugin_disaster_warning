const { Typography } = MaterialUI;

function LogStatsCard({ style }) {
    const { state } = useAppContext();
    const { stats, config } = state;
    const { showToast } = useToast();
    const logStats = stats && stats.logStats ? stats.logStats : {};
    const hasLogStats = !!(stats && stats.logStats);

    const toNumber = (value, fallback = 0) => {
        const n = Number(value);
        return Number.isFinite(n) ? n : fallback;
    };

    const fileCount = toNumber(logStats.file_count, 0);
    const maxCapacity = toNumber(logStats.max_total_capacity_mb, 0);
    const usagePercent = toNumber(logStats.usage_percent, 0);
    const fileSize = toNumber(logStats.file_size_mb, 0);
    const startTime = logStats.date_range?.start || '暂无记录';
    const endTime = logStats.date_range?.end || '暂无记录';

    // 进度条颜色逻辑和状态灯
    let progressColor = 'var(--md-sys-color-primary)';
    let statusDotColor = '#4CAF50'; // Green
    
    if (usagePercent > 90) {
        progressColor = 'var(--md-sys-color-error)';
        statusDotColor = '#F44336'; // Red
    } else if (usagePercent > 70) {
        progressColor = '#F9A825'; // Yellow/Amber
        statusDotColor = '#FFC107'; // Amber
    }

    const handleOpenLogDir = async () => {
        try {
            // 确保 API URL 格式正确
            const baseUrl = config.apiUrl || '';
            const cleanBaseUrl = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
            const targetUrl = `${cleanBaseUrl}/api/open-log-dir`;
            
            console.log('[LogStatsCard] Requesting open-log-dir:', targetUrl);

            const response = await fetch(targetUrl, {
                method: 'POST'
            });
            
            const result = await response.json();
            
            if (result.success) {
                // 成功时不弹窗，直接静默打开
                console.log('Log directory opened successfully');
            } else {
                // 显示服务器返回的错误信息
                showToast(result.error || '操作失败', 'error');
            }
        } catch (e) {
            console.error('Failed to open log dir:', e);
            // 网络错误才弹窗
            showToast(`请求失败: ${e.message || '网络错误或服务不可达'}`, 'error');
        }
    };

    return (
        <div className="card" style={{ height: '100%', minHeight: '200px', ...style }}>
            <div className="chart-card-header" style={{ justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '20px' }}>📝</span>
                    <Typography variant="h6">系统日志统计</Typography>
                </div>
                <button
                    className="btn"
                    onClick={handleOpenLogDir}
                    style={{
                        padding: '6px 12px',
                        fontSize: '12px',
                        background: 'var(--md-sys-color-primary-container)',
                        color: 'var(--md-sys-color-on-primary-container)',
                        borderRadius: '8px',
                        border: 'none',
                        fontWeight: 600,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        cursor: 'pointer',
                        boxShadow: '0 2px 4px rgba(0,0,0,0.05)'
                    }}
                    title="在文件管理器中打开日志目录"
                >
                    <span style={{ fontSize: '14px' }}>📂</span>
                    打开插件数据目录
                </button>
            </div>
            
            {!hasLogStats && (
                <Typography variant="body2" sx={{ opacity: 0.6, mb: 1 }}>
                    当前暂无日志统计数据，请等待日志文件生成后自动更新或开启日志记录功能。
                </Typography>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div style={{ background: 'var(--md-sys-color-surface-variant)', padding: '12px', borderRadius: '8px', gridColumn: 'span 2' }}>
                    <Typography variant="caption" sx={{ opacity: 0.7 }}>统计时间范围</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '13px' }}>
                        {startTime} <span style={{ opacity: 0.5, margin: '0 4px' }}>~</span> {endTime}
                    </Typography>
                </div>

                <div style={{ background: 'var(--md-sys-color-surface-variant)', padding: '12px', borderRadius: '8px' }}>
                    <Typography variant="caption" sx={{ opacity: 0.7 }}>总条目</Typography>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>{logStats.total_entries || 0}</Typography>
                </div>
                <div style={{ background: 'var(--md-sys-color-surface-variant)', padding: '12px', borderRadius: '8px' }}>
                    <Typography variant="caption" sx={{ opacity: 0.7 }}>文件数量</Typography>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>{fileCount}</Typography>
                </div>

                <div style={{ background: 'var(--md-sys-color-surface-variant)', padding: '12px', borderRadius: '8px', gridColumn: 'span 2' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{
                                width: '8px',
                                height: '8px',
                                borderRadius: '50%',
                                backgroundColor: statusDotColor,
                                boxShadow: `0 0 4px ${statusDotColor}`
                            }}></div>
                            <Typography variant="caption" sx={{ opacity: 0.7 }}>存储占用</Typography>
                            <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.7, fontSize: '11px' }}>
                                ({usagePercent.toFixed(2)}%)
                            </Typography>
                        </div>
                        <Typography variant="caption" sx={{ fontWeight: 700 }}>
                            {fileSize.toFixed(2)} MB / {maxCapacity > 0 ? maxCapacity.toFixed(0) : '-'} MB
                        </Typography>
                    </div>
                    <div style={{
                        width: '100%',
                        height: '6px',
                        background: 'rgba(0,0,0,0.1)',
                        borderRadius: '3px',
                        overflow: 'hidden'
                    }}>
                        <div style={{
                            width: `${Math.min(usagePercent, 100)}%`,
                            height: '100%',
                            background: progressColor,
                            borderRadius: '3px',
                            transition: 'width 0.5s ease-out'
                        }}></div>
                    </div>
                </div>
                <div style={{ background: 'var(--md-sys-color-surface-variant)', padding: '12px', borderRadius: '8px', gridColumn: 'span 2' }}>
                    <Typography variant="caption" sx={{ opacity: 0.7 }}>过滤统计</Typography>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '8px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Typography variant="body2" sx={{ fontSize: '13px' }}>心跳包过滤</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>{logStats.filter_stats?.heartbeat_filtered || 0}</Typography>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Typography variant="body2" sx={{ fontSize: '13px' }}>P2P节点过滤</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>{logStats.filter_stats?.p2p_areas_filtered || 0}</Typography>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Typography variant="body2" sx={{ fontSize: '13px' }}>重复事件过滤</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>{logStats.filter_stats?.duplicate_events_filtered || 0}</Typography>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Typography variant="body2" sx={{ fontSize: '13px' }}>连接状态过滤</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>{logStats.filter_stats?.connection_status_filtered || 0}</Typography>
                        </div>
                        <div style={{ borderTop: '1px solid rgba(0,0,0,0.1)', marginTop: '4px', paddingTop: '4px', display: 'flex', justifyContent: 'space-between' }}>
                            <Typography variant="body2" sx={{ fontSize: '13px', fontWeight: 700 }}>总计过滤</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 700 }}>{logStats.filter_stats?.total_filtered || 0}</Typography>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
