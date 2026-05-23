const { Box, Typography } = MaterialUI;
const { useMemo } = React;

/**
 * 连接状态网格组件 (ConnectionsGrid)
 * 显示各个主流数据源（如 FAN Studio, P2P 地震情報, Wolfx, Global Quake）的实时连接情况、
 * 握手延迟/网络 Ping 值、TCP 重连重试次数以及启用的子数据源明细。
 * 
 * 核心逻辑：
 * 1. 声明四个监控的重点 API 服务平台及 key 正则匹配器。
 * 2. 扫描 connections 数据，融合同一平台下的多个长连接，拉取最大重试数与判定在线状态。
 * 3. 规范并展示接口延迟，根据 getLatencyTone 将延迟划分评级：
 *    - < 150ms 评为 fast (绿色)
 *    - < 460ms 评为 medium (黄色)
 *    - 其它 评为 slow (红色)
 * 4. 循环输出各平台已启用/禁用的子数据源中文对照清单（支持将后台 key 转换为友好地名名称）。
 */
function ConnectionsGrid() {
    const { state } = useAppContext();
    const { connections, dataLoaded } = state;

    // 解析过滤 connections 数据
    const displayConnections = useMemo(() => {
        // 定义需要监控的目标数据源及其匹配规则
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
            // 优先以后端注入的 enabled 字段为准；若所有匹配项均未启用则视为 disabled
            let status = 'disabled';
            if (matchedEntries.length > 0) {
                const isEnabled = matchedEntries.some(([, info]) => !!info.enabled);
                if (isEnabled) {
                    const isConnected = matchedEntries.some(([, info]) => !!info.connected);
                    status = isConnected ? 'online' : 'offline';
                }
            }
            
            // 聚合重试次数 (取匹配项中的最大值)
            const retryCount = matchedEntries.reduce((max, [, info]) => Math.max(max, info.retry_count || 0), 0);

            // 聚合所有已启用的子数据源
            const allSubSources = {};
            matchedEntries.forEach(([, info]) => {
                if (info.sub_sources) {
                    Object.assign(allSubSources, info.sub_sources);
                }
            });

            // 获取延迟信息，兼容 latency / latency_ms / ping 等不同接口字段，并规范为 number | null | undefined
            const rawLatency = matchedEntries.length > 0
                ? (matchedEntries[0][1].latency ?? matchedEntries[0][1].latency_ms ?? matchedEntries[0][1].ping)
                : undefined;
            let latency = undefined;
            if (rawLatency === null) {
                latency = null;
            } else if (rawLatency !== undefined && rawLatency !== '') {
                const normalizedLatency = Number(rawLatency);
                latency = Number.isFinite(normalizedLatency) ? normalizedLatency : null;
            }

            return {
                name: target.displayName,
                status: status, // 'online' | 'offline' | 'disabled'
                retry_count: retryCount,
                sub_sources: allSubSources,
                latency: latency  // 延迟值 (ms)
            };
        });
    }, [connections]);

    // 状态中文对照映射
    const statusLabels = {
        online: '在线',
        offline: '离线',
        disabled: '未启用'
    };

    /**
     * 网络延迟区间着色器类映射
     */
    const getLatencyTone = (latency) => {
        if (latency < 150) return 'fast';
        if (latency < 460) return 'medium';
        return 'slow';
    };

    // 1. 状态：异步连接详情尚未拉取完毕前，渲染骨架卡片矩阵
    if (!dataLoaded) {
        return (
            <div className="connections-grid status-connections-grid">
                {[1, 2, 3, 4].map(i => (
                    <div key={i} className="status-connection-skeleton-card">
                        <div className="status-skeleton-row">
                            <div className="skeleton status-skeleton-title"></div>
                            <div className="skeleton status-skeleton-badge"></div>
                        </div>
                        <div className="skeleton status-skeleton-subtitle"></div>
                        <div className="skeleton status-skeleton-subtitle status-skeleton-subtitle--short"></div>
                    </div>
                ))}
            </div>
        );
    }

    return (
        <div className="connections-grid status-connections-grid">
            {displayConnections.map((conn) => {
                return (
                    <Box key={conn.name} className={`connection-item connection-item-${conn.status}`}>
                        {/* 顶栏：服务名与重连次数、状态指示灯 */}
                        <Box className="connection-card-header">
                            <Typography className="connection-title">
                                {conn.name}
                            </Typography>
                            
                            <Box className="connection-status-cluster">
                                {conn.retry_count > 0 && conn.status !== 'disabled' && (
                                    <Typography variant="caption" className="connection-retry-count">
                                        重试: {conn.retry_count}
                                    </Typography>
                                )}
                                {/* 状态指示呼吸灯点 */}
                                <div className="connection-indicator"></div>
                            </Box>
                        </Box>

                        {/* 中部：状态文本与网络延迟 */}
                        <Box className="connection-summary">
                            <Typography className="connection-status-label">
                                {statusLabels[conn.status]}
                            </Typography>
                            
                            {/* 仅在已启用的服务上展示网络响应延时 */}
                            {conn.status !== 'disabled' && (
                                <Typography className={`connection-latency-line ${conn.latency === undefined || conn.latency === null ? 'is-pending' : ''}`}>
                                    <span className="connection-latency-icon">⏱</span>
                                    延迟:
                                    {conn.latency !== undefined && conn.latency !== null ? (
                                        <span className={`connection-latency-value connection-latency-value--${getLatencyTone(conn.latency)}`}>
                                            {conn.latency.toFixed(0)}ms
                                        </span>
                                    ) : conn.latency === null ? (
                                        <span>无法测量</span>
                                    ) : (
                                        <span>测量中...</span>
                                    )}
                                </Typography>
                            )}
                        </Box>

                        {/* 尾部：该连接服务旗下已订阅的子数据源（CEA地震、USGS、气象预警等）汉化对照清单 */}
                        {conn.sub_sources && Object.keys(conn.sub_sources).length > 0 ? (
                            <Box className="connection-sub-source-section">
                                <Box className="connection-sub-source-header">
                                    <Typography variant="caption" className="connection-sub-source-title">
                                        启用的子数据源详情
                                    </Typography>
                                    <Typography variant="caption" className="connection-sub-source-count">
                                        {Object.values(conn.sub_sources).filter(Boolean).length} / {Object.keys(conn.sub_sources).length}
                                    </Typography>
                                </Box>
                                <Box className="connection-sub-source-list">
                                    {Object.entries(conn.sub_sources)
                                        .sort(([, a], [, b]) => (a === b ? 0 : a ? -1 : 1)) // 启用的优先排列在顶部
                                        .map(([key, enabled]) => {
                                            /**
                                             * 内部子数据源 ID => 中文可读机构对照字典
                                             */
                                            const getScopedSourceName = (sourceKey, connectionName) => {
                                                const rawKey = String(sourceKey || '').trim();
                                                if (!rawKey) return rawKey;

                                                const scopedSourceMap = {
                                                    'FAN Studio': {
                                                        china_earthquake_warning: '中国地震预警网 (CEA)',
                                                        china_earthquake_warning_provincial: '中国地震预警网 (省级)',
                                                        taiwan_cwa_earthquake: '台湾中央气象署: 强震即时警报',
                                                        taiwan_cwa_report: '台湾中央气象署: 地震报告',
                                                        china_cenc_earthquake: '中国地震台网 (CENC)',
                                                        usgs_earthquake: '美国地质调查局 (USGS)',
                                                        china_weather_alarm: '中国气象局: 气象预警',
                                                        china_tsunami: '自然资源部海啸预警中心',
                                                        japan_jma_eew: '日本气象厅: 紧急地震速报'
                                                    },
                                                    'P2P地震情報': {
                                                        japan_jma_eew: '日本气象厅: 紧急地震速报',
                                                        japan_jma_earthquake: '日本气象厅: 地震情报',
                                                        japan_jma_tsunami: '日本气象厅: 海啸予报'
                                                    },
                                                    'Wolfx': {
                                                        japan_jma_eew: '日本气象厅: 紧急地震速报',
                                                        china_cenc_eew: '中国地震预警网 (CEA)',
                                                        taiwan_cwa_eew: '台湾中央气象署: 强震即时警报',
                                                        japan_jma_earthquake: '日本气象厅地震情报',
                                                        china_cenc_earthquake: '中国地震台网地震测定'
                                                    },
                                                    'Global Quake': {
                                                        enabled: '实时数据流'
                                                    }
                                                };

                                                const scopedName = scopedSourceMap[connectionName]?.[rawKey];
                                                if (scopedName) return scopedName;

                                                const formattedName = window.formatSourceName
                                                    ? window.formatSourceName(rawKey)
                                                    : rawKey;

                                                // 过滤多余的后缀平台名
                                                return String(formattedName)
                                                    .replace(/\s+-\s+(Fan|P2P|Wolfx)$/i, '')
                                                    .trim();
                                            };

                                            const friendlyName = getScopedSourceName(key, conn.name);

                                            return (
                                                <Box 
                                                    key={key} 
                                                    className={`connection-sub-source-item ${enabled ? '' : 'is-disabled'}`}
                                                >
                                                    <Box className="connection-sub-source-dot" />
                                                    <Typography className="connection-sub-source-name">
                                                        {friendlyName}
                                                    </Typography>
                                                    {!enabled && (
                                                        <Typography className="connection-sub-source-off-badge">
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
                                <Typography variant="caption" className="connection-empty-detail">
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
