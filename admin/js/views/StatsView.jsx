const { Box, Typography, Chip } = MaterialUI;

function StatsView() {
    const { state } = useAppContext();
    const { stats, config } = state;
    const { showToast } = useToast(); // 使用 Toast 提示
    const displayTimezone = config.displayTimezone || 'UTC+8';
    const maxMag = stats && stats.maxMagnitude ? stats.maxMagnitude : null;
    const sources = stats && stats.dataSources ? stats.dataSources : [];
    const eqRegions = stats && stats.earthquakeRegions ? stats.earthquakeRegions : [];
    const weatherTypes = stats && stats.weatherTypes ? stats.weatherTypes : [];
    const weatherRegions = stats && stats.weatherRegions ? stats.weatherRegions : [];
    const weatherLevels = stats && stats.weatherLevels ? stats.weatherLevels : [];
    const logStats = stats && stats.logStats ? stats.logStats : null;

    // 格式化时间
    const formatTime = (time) => {
        if (!time) return '未知时间';
        return formatTimeWithZone(time, displayTimezone, true);
    };

    const renderMaxMagCard = () => {
        if (!maxMag) {
            return (
                <div className="card" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', minHeight: '200px' }}>
                    <span style={{ fontSize: '48px', opacity: 0.2 }}>📉</span>
                    <Typography variant="body2" sx={{ opacity: 0.5, mt: 1 }}>暂无最大震级记录</Typography>
                </div>
            );
        }

        return (
            <div className="card" style={{
                background: 'linear-gradient(135deg, var(--md-sys-color-error-container) 0%, var(--md-sys-color-surface) 100%)',
                position: 'relative',
                overflow: 'hidden',
                height: '100%' // 确保填满容器
            }}>
                <div style={{
                    position: 'absolute',
                    top: '-10px',
                    right: '-10px',
                    fontSize: '100px',
                    opacity: 0.05,
                    pointerEvents: 'none',
                    userSelect: 'none'
                }}>🔥</div>

                <div className="chart-card-header" style={{ marginBottom: '16px' }}>
                    <span style={{ fontSize: '20px' }}>🔥</span>
                    <Typography variant="h6" sx={{ color: 'var(--md-sys-color-on-error-container)' }}>历史最大地震</Typography>
                </div>
                
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '8px' }}>
                    <Typography variant="h3" sx={{
                        fontWeight: 800,
                        color: 'var(--md-sys-color-error)',
                        lineHeight: 1
                    }}>
                        <span style={{ marginRight: '8px' }}>M</span>{parseFloat(maxMag.value).toFixed(1)}
                    </Typography>
                    {maxMag.source && (
                        <Chip
                            label={formatSourceName(maxMag.source)}
                            size="small"
                            sx={{
                                height: '24px',
                                fontSize: '12px',
                                background: 'rgba(255,255,255,0.3)',
                                color: 'var(--md-sys-color-on-error-container)'
                            }} 
                        />
                    )}
                </div>

                <Typography variant="body1" sx={{ fontWeight: 800, mb: 1, color: 'var(--md-sys-color-on-error-container)' }}>
                    {maxMag.place_name}
                </Typography>
                
                <Typography variant="body2" sx={{ opacity: 0.7, color: 'var(--md-sys-color-on-error-container)' }}>
                    {formatTime(maxMag.time)}
                </Typography>
            </div>
        );
    };

    const renderTopListCard = (title, icon, data, color) => {
        if (!data || data.length === 0) {
            return (
                <div className="card" style={{ height: '100%', minHeight: '200px' }}>
                    <div className="chart-card-header">
                        <span style={{ fontSize: '20px' }}>{icon}</span>
                        <Typography variant="h6">{title}</Typography>
                    </div>
                    <Typography variant="body2" sx={{ opacity: 0.5, textAlign: 'center', py: 4 }}>
                        暂无数据
                    </Typography>
                </div>
            );
        }
        
        // 计算最大值，用于比例条
        const maxCount = Math.max(...data.slice(0, 10).map(d => d.count));

        return (
            <div className="card" style={{ height: '100%', minHeight: '200px' }}>
                <div className="chart-card-header">
                    <span style={{ fontSize: '20px' }}>{icon}</span>
                    <Typography variant="h6">{title}</Typography>
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {data.slice(0, 10).map((item, index) => {
                        const percentage = (item.count / maxCount) * 100;
                        
                        return (
                            <div key={index} style={{ position: 'relative', padding: '6px 8px', borderRadius: '8px', zIndex: 1, overflow: 'hidden' }}>
                                {/* 进度条背景 - 从文字开始 (跳过数字标号)，稍微左移一点包裹文字 */}
                                <div style={{
                                    position: 'absolute',
                                    top: '4px',
                                    bottom: '4px',
                                    left: '40px', // 稍微往左移一点 (44px -> 40px)
                                    right: '8px',
                                    zIndex: -1,
                                }}>
                                    <div style={{
                                        width: `calc(${percentage}% + 4px)`, // 稍微加宽一点补偿左移
                                        height: '100%',
                                        background: color,
                                        opacity: 0.2,
                                        borderRadius: '4px',
                                        transition: 'width 0.5s ease-out'
                                    }}></div>
                                </div>

                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', position: 'relative' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: 0, marginRight: '8px' }}>
                                        <div style={{
                                            width: '24px',
                                            height: '24px',
                                            borderRadius: '6px',
                                            background: index < 3 ? color : 'var(--md-sys-color-surface-variant)',
                                            color: index < 3 ? '#fff' : 'inherit',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            fontSize: '12px',
                                            fontWeight: 700,
                                            flexShrink: 0
                                        }}>
                                            {index + 1}
                                        </div>
                                        <Typography variant="body2" noWrap sx={{ fontWeight: 600, fontSize: '13px' }}>
                                            {item.region ? item.region : (item.type ? item.type : formatSourceName(item.source))}
                                        </Typography>
                                    </div>
                                    <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.7, flexShrink: 0 }}>
                                        {item.count}
                                    </Typography>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        );
    };

    const renderWeatherLevelCard = () => {
        if (!weatherLevels || weatherLevels.length === 0) {
            return (
                <div className="card" style={{ height: '100%', minHeight: '200px' }}>
                    <div className="chart-card-header">
                        <span style={{ fontSize: '20px' }}>🎨</span>
                        <Typography variant="h6">气象预警级别</Typography>
                    </div>
                    <Typography variant="body2" sx={{ opacity: 0.5, textAlign: 'center', py: 4 }}>暂无数据</Typography>
                </div>
            );
        }

        const total = weatherLevels.reduce((acc, curr) => acc + curr.count, 0);
        let currentAngle = 0;

        // 颜色映射
        const getColor = (level) => {
            if (level.includes('红')) return '#F94543';
            if (level.includes('橙')) return '#FF7639';
            if (level.includes('黄')) return '#FCD952';
            if (level.includes('蓝')) return '#1982C1';
            if (level.includes('白')) return '#e5e7eb'; // 白色预警，使用浅灰色
            return '#9ca3af';
        };

        return (
            <div className="card" style={{ height: '100%', minHeight: '200px', display: 'flex', flexDirection: 'column' }}>
                <div className="chart-card-header">
                    <span style={{ fontSize: '20px' }}>🎨</span>
                    <Typography variant="h6">气象预警级别</Typography>
                </div>
                
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', padding: '16px 0' }}>
                    {/* CSS Conic Gradient Pie Chart */}
                    <div style={{
                        width: '160px',
                        height: '160px',
                        borderRadius: '50%',
                        background: `conic-gradient(${weatherLevels.map(item => {
                            const start = currentAngle;
                            const percentage = (item.count / total) * 100;
                            currentAngle += percentage;
                            return `${getColor(item.level)} ${start}% ${currentAngle}%`;
                        }).join(', ')})`,
                        position: 'relative',
                        marginBottom: '32px'
                    }}>
                        {/* 中空圆环效果 */}
                        <div style={{
                            position: 'absolute',
                            top: '50%',
                            left: '50%',
                            transform: 'translate(-50%, -50%)',
                            width: '60%',
                            height: '60%',
                            background: 'var(--md-sys-color-surface)',
                            // 强制叠加一层白色（在亮色模式下）以确保不透明，或者使用混合模式
                            // 这里简单粗暴地用 box-shadow 填补可能的透明缝隙，或者直接指定一个 fallback 颜色
                            backgroundColor: '#e5e7eb', // 先设为白色
                            backgroundImage: 'linear-gradient(var(--md-sys-color-surface), var(--md-sys-color-surface))', // 再叠加上主题色
                            borderRadius: '50%',
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center'
                        }}>
                            <Typography variant="h5" sx={{ fontWeight: 800, lineHeight: 1 }}>{total}</Typography>
                            <Typography variant="caption" sx={{ opacity: 0.6, fontSize: '11px', mt: 0.5 }}>预警总数</Typography>
                        </div>
                    </div>

                    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {weatherLevels.map((item, index) => (
                            <div key={index} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '13px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    <span style={{ fontWeight: 600, opacity: 0.9 }}>{item.level}</span>
                                </div>
                                <div style={{ display: 'flex', gap: '8px' }}>
                                    <span style={{ fontWeight: 700 }}>{item.count}</span>
                                    <span style={{ opacity: 0.5, minWidth: '45px', textAlign: 'right' }}>
                                        {((item.count / total) * 100).toFixed(2)}%
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        );
    };

    const renderLogStatsCard = () => {
        if (!logStats) return null;

        const fileCount = logStats.file_count || 1;
        const maxCapacity = logStats.max_total_capacity_mb || 0;
        const usagePercent = logStats.usage_percent || 0;
        const fileSize = logStats.file_size_mb || 0;
        const startTime = logStats.date_range?.start || '未知';
        const endTime = logStats.date_range?.end || '未知';

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
                const baseUrl = state.config.apiUrl || '';
                const cleanBaseUrl = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
                const targetUrl = `${cleanBaseUrl}/api/open-log-dir`;
                
                console.log('[StatsView] Requesting open-log-dir:', targetUrl);

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
            <div className="card" style={{ height: '100%', minHeight: '200px' }}>
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
    };

    return (
        <Box>
            <div className="dashboard-grid">
                {/* 第一行：左侧震级图，右侧统计卡片和最大地震 */}
                {/* 使用 grid 嵌套，强制左边大卡片和右边两个小卡片组等高 */}
                <div style={{ gridColumn: 'span 12', display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '24px', alignItems: 'stretch' }}>
                    <div style={{ gridColumn: 'span 8', display: 'flex' }}>
                        <div style={{ width: '100%', display: 'flex', flexDirection: 'column' }}>
                            <MagnitudeChart style={{ flex: 1 }} />
                        </div>
                    </div>
                    <div style={{ gridColumn: 'span 4', display: 'flex', flexDirection: 'column', gap: '24px' }}>
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                            <StatsCard style={{ flex: 1, height: '100%' }} />
                        </div>
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                             {renderMaxMagCard()}
                        </div>
                    </div>
                </div>

                {/* 时间维度统计：趋势图和热力图 */}
                <div className="span-12">
                    <TrendChart style={{ height: '100%', minHeight: '300px' }} />
                </div>
                <div className="span-12">
                    <CalendarHeatmap style={{ height: '100%', minHeight: '220px' }} />
                </div>

                {/* 第二行：三个 Top 榜单 (地震地区、气象类型、数据源) */}
                <div className="span-4">
                    {renderTopListCard("国内地震高发地 (TOP 10)", "📍", eqRegions, "#FF9800")}
                </div>
                <div className="span-4">
                    {renderTopListCard("气象预警类型 (TOP 10)", "⛈️", weatherTypes, "#4CAF50")}
                </div>
                <div className="span-4">
                    {renderTopListCard("数据源贡献 (TOP 10)", "📡", sources, "#2196F3")}
                </div>

                {/* 第三行：新增气象地区、气象级别、日志统计 */}
                <div className="span-4">
                    {renderTopListCard("气象预警地区分布 (TOP 10)", "🗺️", weatherRegions, "#00ACC1")}
                </div>
                <div className="span-4">
                    {renderWeatherLevelCard()}
                </div>
                <div className="span-4">
                    {renderLogStatsCard()}
                </div>

                <div className="span-12">
                    <div className="card" style={{ background: 'var(--md-sys-color-primary-container)', color: 'var(--md-sys-color-on-primary-container)', border: 'none' }}>
                        <h4 style={{ fontWeight: 800, marginBottom: '12px' }}>📊 数据摘要</h4>
                        <p style={{ fontSize: '14px', opacity: 0.8, lineHeight: 1.6 }}>
                            统计信息会自动实时更新。您可以从这些图表中直观的观察到灾害活动的强度分布和频率。
                        </p>
                    </div>
                </div>
            </div>
        </Box>
    );
}
