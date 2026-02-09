const { Box, Typography } = MaterialUI;
const { useMemo } = React;

/**
 * 连接状态网格组件
 * 显示各个数据源（如 FAN Studio, P2P, Wolfx, Global Quake）的连接状态、重试次数和子数据源启用情况
 */
function ConnectionsGrid() {
    const { state } = useAppContext();
    const { connections } = state;

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
            
            // 聚合状态
            // 只要有一个匹配项连接成功，视为在线
            const isConnected = matchedEntries.some(([, info]) => !!info.connected);
            
            // 聚合重试次数 (取最大值)
            const retryCount = matchedEntries.reduce((max, [, info]) => Math.max(max, info.retry_count || 0), 0);

            // 聚合所有已启用的子数据源
            // sub_sources 结构: { "fan_studio_cenc": true, ... }
            const allSubSources = {};
            matchedEntries.forEach(([, info]) => {
                if (info.sub_sources) {
                    Object.assign(allSubSources, info.sub_sources);
                }
            });

            return {
                name: target.displayName,
                connected: isConnected,
                retry_count: retryCount,
                sub_sources: allSubSources
            };
        });
    }, [connections]);

    return (
        <div className="connections-grid">
            {displayConnections.map((conn) => (
                <div key={conn.name} className={`connection-item ${conn.connected ? 'connected' : 'disconnected'}`} style={{ height: 'auto', minHeight: '100px' }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                        <Typography className="conn-name" sx={{ fontWeight: 700 }}>
                            {conn.name}
                        </Typography>
                        <div style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            background: conn.connected ? '#4CAF50' : '#F44336',
                            boxShadow: `0 0 6px ${conn.connected ? '#4CAF50' : '#F44336'}`
                        }}></div>
                    </Box>
                    <div className="conn-status">
                        <span>{conn.connected ? '在线' : '离线'}</span>
                        {conn.retry_count > 0 && (
                            <span style={{ opacity: 0.6 }}>重试: {conn.retry_count}</span>
                        )}
                    </div>

                    {/* 子数据源状态展示 */}
                    {conn.sub_sources && Object.keys(conn.sub_sources).length > 0 && (
                        <div style={{ marginTop: '12px', paddingTop: '8px', borderTop: '1px solid rgba(0,0,0,0.05)' }}>
                            <Typography variant="caption" sx={{ opacity: 0.5, display: 'block', mb: 0.5, fontSize: '10px' }}>
                                已启用数据源
                            </Typography>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                {Object.entries(conn.sub_sources).map(([key, enabled]) => {
                                    if (!enabled) return null;
                                    // 使用全局 formatSourceName (如果可用) 或回退到 key
                                    // 注意：formatSourceName 定义在 index.html 引入的 formatters.js 中
                                    const friendlyName = window.formatSourceName ? window.formatSourceName(key) : key;
                                    
                                    return (
                                        <span key={key} style={{
                                            fontSize: '10px',
                                            background: 'var(--md-sys-color-surface-variant)',
                                            padding: '2px 6px',
                                            borderRadius: '4px',
                                            opacity: 0.8,
                                            border: '1px solid rgba(0,0,0,0.05)',
                                            display: 'block',
                                            width: 'fit-content'
                                        }}>
                                            {friendlyName}
                                        </span>
                                    );
                                })}
                            </div>
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
}
