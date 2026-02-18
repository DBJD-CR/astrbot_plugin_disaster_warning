const { Box, Typography } = MaterialUI;
const { useMemo } = React;

/**
 * 连接状态网格组件
 * 显示各个数据源（如 FAN Studio, P2P, Wolfx, Global Quake）的连接状态、重试次数和子数据源启用情况
 */
function ConnectionsGrid() {
    const { state } = useAppContext();
    const { connections, dataLoaded } = state;

    const displayConnections = useMemo(() => {
        // 定义需要监控的目标数据源及其匹配规则
        // id: 内部标识符
        // displayName: 前端显示的名称
        // matcher: 用于在 connections 状态中查找对应键值的函数
        const targets = [
            {
                id: 'fan',
                displayName: 'FAN Studio',
                matcher: (key) => key.toLowerCase().includes('fan')
            },
            {
                id: 'p2p',
                displayName: 'P2P地震情報',
                matcher: (key) => key.toLowerCase().includes('p2p')
            },
            {
                id: 'wolfx',
                displayName: 'Wolfx',
                matcher: (key) => key === 'wolfx_all' || key.toLowerCase().includes('wolfx')
            },
            {
                id: 'gq',
                displayName: 'Global Quake',
                matcher: (key) => key.toLowerCase().includes('global')
            }
        ];

        return targets.map(target => {
            // 在所有连接中找到匹配的项
            const matchedEntries = Object.entries(connections).filter(([key]) => target.matcher(key));
            
            // 判断状态：未启用 | 在线 | 离线
            let status = 'disabled';
            if (matchedEntries.length > 0) {
                // 只要有一个匹配项连接成功，视为在线
                const isConnected = matchedEntries.some(([, info]) => !!info.connected);
                status = isConnected ? 'online' : 'offline';
            }
            
            // 聚合重试次数 (取最大值)
            const retryCount = matchedEntries.reduce((max, [, info]) => Math.max(max, info.retry_count || 0), 0);

            // 聚合所有已启用的子数据源
            const allSubSources = {};
            matchedEntries.forEach(([, info]) => {
                if (info.sub_sources) {
                    Object.assign(allSubSources, info.sub_sources);
                }
            });

            // 获取延迟信息（取第一个匹配项的延迟）
            const latency = matchedEntries.length > 0 ? matchedEntries[0][1].latency : undefined;

            return {
                name: target.displayName,
                status: status, // 'online' | 'offline' | 'disabled'
                retry_count: retryCount,
                sub_sources: allSubSources,
                latency: latency  // 添加延迟字段
            };
        });
    }, [connections]);

    // 状态样式配置
    const statusConfig = {
        online: {
            color: '#4CAF50',
            bgColor: 'rgba(76, 175, 80, 0.04)',
            borderColor: 'rgba(76, 175, 80, 0.3)',
            label: '在线',
            indicatorShadow: '0 0 8px rgba(76, 175, 80, 0.6)'
        },
        offline: {
            color: '#F44336',
            bgColor: 'rgba(244, 67, 54, 0.04)',
            borderColor: 'rgba(244, 67, 54, 0.3)',
            label: '离线',
            indicatorShadow: '0 0 8px rgba(244, 67, 54, 0.6)'
        },
        disabled: {
            color: '#9E9E9E',
            bgColor: 'rgba(158, 158, 158, 0.05)',
            borderColor: 'rgba(0, 0, 0, 0.08)',
            label: '未启用',
            indicatorShadow: 'none'
        }
    };

    // 骨架屏
    if (!dataLoaded) {
        return (
            <div className="connections-grid" style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                gap: '16px'
            }}>
                {[1, 2, 3, 4].map(i => (
                    <div key={i} style={{
                        borderRadius: '16px',
                        border: '1px solid var(--glass-border)',
                        padding: '20px',
                        minHeight: '140px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '12px'
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div className="skeleton" style={{ width: '120px', height: '22px', borderRadius: '6px' }}></div>
                            <div className="skeleton" style={{ width: '60px', height: '24px', borderRadius: '12px' }}></div>
                        </div>
                        <div className="skeleton" style={{ width: '80%', height: '16px', borderRadius: '4px' }}></div>
                        <div className="skeleton" style={{ width: '60%', height: '16px', borderRadius: '4px' }}></div>
                    </div>
                ))}
            </div>
        );
    }

    return (
        <div className="connections-grid" style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '16px'
        }}>
            {displayConnections.map((conn) => {
                const config = statusConfig[conn.status];
                
                return (
                    <Box key={conn.name} sx={{
                        position: 'relative',
                        borderRadius: '16px',
                        border: '1px solid',
                        borderColor: config.borderColor,
                        bgcolor: config.bgColor,
                        p: 2.5,
                        transition: 'all 0.3s ease',
                        display: 'flex',
                        flexDirection: 'column',
                        minHeight: '140px',
                        '&:hover': {
                            transform: 'translateY(-2px)',
                            boxShadow: '0 6px 16px rgba(0,0,0,0.05)'
                        }
                    }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                            <Typography sx={{ fontWeight: 700, fontSize: '1.1rem', color: 'text.primary' }}>
                                {conn.name}
                            </Typography>
                            
                            {/* 状态指示灯 */}
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                {conn.retry_count > 0 && conn.status !== 'disabled' && (
                                    <Typography variant="caption" sx={{ color: 'warning.main', fontWeight: 600 }}>
                                        重试: {conn.retry_count}
                                    </Typography>
                                )}
                                <div style={{
                                    width: '10px',
                                    height: '10px',
                                    borderRadius: '50%',
                                    backgroundColor: config.color,
                                    boxShadow: config.indicatorShadow,
                                    transition: 'background-color 0.3s'
                                }}></div>
                            </Box>
                        </Box>

                        <Box sx={{ mb: 2 }}>
                            <Typography sx={{
                                color: config.color,
                                fontWeight: 600,
                                fontSize: '0.95rem',
                                display: 'flex',
                                alignItems: 'center'
                            }}>
                                {config.label}
                            </Typography>
                            
                            {/* 延迟显示 */}
                            {conn.latency !== undefined && conn.latency !== null && (
                                <Typography sx={{
                                    color: 'text.secondary',
                                    fontSize: '0.85rem',
                                    mt: 0.5,
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 0.5
                                }}>
                                    <span style={{ fontSize: '0.75rem' }}>⏱</span>
                                    延迟: <span style={{ 
                                        fontWeight: 600,
                                        color: conn.latency < 100 ? '#4CAF50' : conn.latency < 300 ? '#FF9800' : '#F44336'
                                    }}>{conn.latency.toFixed(0)}ms</span>
                                </Typography>
                            )}
                            {conn.latency === null && conn.status !== 'disabled' && (
                                <Typography sx={{
                                    color: 'text.disabled',
                                    fontSize: '0.85rem',
                                    mt: 0.5,
                                    fontStyle: 'italic'
                                }}>
                                    延迟: 无法测量
                                </Typography>
                            )}
                        </Box>

                        {/* 子数据源状态展示 */}
                        {conn.sub_sources && Object.keys(conn.sub_sources).length > 0 ? (
                            <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid', borderColor: 'rgba(0,0,0,0.15)' }}>
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
                                    <Typography variant="caption" sx={{ opacity: 0.8, fontSize: '12px', fontWeight: 600, letterSpacing: '0.5px', textTransform: 'uppercase' }}>
                                        启用的子数据源详情
                                    </Typography>
                                    <Typography variant="caption" sx={{ opacity: 0.6, fontSize: '11px', fontWeight: 600 }}>
                                        {Object.values(conn.sub_sources).filter(Boolean).length} / {Object.keys(conn.sub_sources).length}
                                    </Typography>
                                </Box>
                                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                                    {Object.entries(conn.sub_sources)
                                        .sort(([, a], [, b]) => (a === b ? 0 : a ? -1 : 1))
                                        .map(([key, enabled]) => {
                                        const friendlyName = window.formatSourceName ? window.formatSourceName(key) : key;
                                        
                                        return (
                                            <Box key={key} sx={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                p: 1,
                                                borderRadius: '8px',
                                                bgcolor: enabled ? 'var(--md-sys-color-surface)' : 'rgba(0,0,0,0.03)',
                                                border: '1px solid',
                                                borderColor: enabled ? 'rgba(76, 175, 80, 0.15)' : 'transparent',
                                                transition: 'all 0.2s'
                                            }}>
                                                <Box sx={{
                                                    width: 6,
                                                    height: 6,
                                                    borderRadius: '50%',
                                                    bgcolor: enabled ? '#4CAF50' : '#BDBDBD',
                                                    mr: 1.5,
                                                    flexShrink: 0,
                                                }} />
                                                <Typography sx={{
                                                    fontSize: '12px',
                                                    fontWeight: enabled ? 600 : 400,
                                                    color: enabled ? 'text.primary' : 'text.secondary',
                                                    flex: 1,
                                                    lineHeight: 1.2
                                                }}>
                                                    {friendlyName}
                                                </Typography>
                                                {!enabled && (
                                                    <Typography sx={{
                                                        fontSize: '10px',
                                                        color: 'text.disabled',
                                                        fontWeight: 600,
                                                        bgcolor: 'rgba(0,0,0,0.05)',
                                                        px: 0.8,
                                                        py: 0.2,
                                                        borderRadius: '4px'
                                                    }}>
                                                        OFF
                                                    </Typography>
                                                )}
                                            </Box>
                                        );
                                    })}
                                </Box>
                            </Box>
                        ) : (
                            conn.status !== 'disabled' && (
                                <Typography variant="caption" sx={{ color: 'text.secondary', fontStyle: 'italic', opacity: 0.7 }}>
                                    无详细子数据源信息
                                </Typography>
                            )
                        )}
                    </Box>
                );
            })}
        </div>
    );
}
