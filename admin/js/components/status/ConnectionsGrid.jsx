const { Box, Typography } = MaterialUI;
const { useMemo } = React;

/**
 * 连接状态网格组件 (ConnectionsGrid)
 * 显示主流数据源（FAN Studio / P2P / Wolfx / Global Quake）与 HTTP 辅助通道 EQSC 的
 * 实时连接情况、TCP 延迟、重试次数以及启用的子数据源明细。
 *
 * 布局：
 * - 前三列：FAN / P2P / Wolfx 独立卡片
 * - 第四列：Global Quake 与 EQSC API 上下堆叠（connection-stack）
 *
 * 延迟评级：
 * - < 150ms  fast (绿色)
 * - < 460ms  medium (黄色)
 * - 其它 评为 slow (红色)
 */
function ConnectionsGrid() {
    const { state } = useAppContext();
    const { connections, dataLoaded } = state;

    /**
     * 将后端连接条目规范为前端展示模型。
     */
    const normalizeConnection = (target, matchedEntries) => {
        let status = 'disabled';
        let statusLabel = null;
        let circuitOpen = false;
        let connectionType = target.connectionType || 'websocket';

        if (matchedEntries.length > 0) {
            const primary = matchedEntries[0][1] || {};
            connectionType = primary.connection_type || connectionType;
            circuitOpen = !!primary.circuit_open;
            if (primary.status) {
                statusLabel = String(primary.status);
            }

            const isEnabled = matchedEntries.some(([, info]) => !!info.enabled);
            if (isEnabled) {
                const isConnected = matchedEntries.some(([, info]) => !!info.connected);
                status = isConnected ? 'online' : 'offline';
            }
        }

        const retryCount = matchedEntries.reduce(
            (max, [, info]) => Math.max(max, info.retry_count || 0),
            0
        );

        const allSubSources = {};
        matchedEntries.forEach(([, info]) => {
            if (info.sub_sources) {
                Object.assign(allSubSources, info.sub_sources);
            }
        });

        const rawLatency = matchedEntries.length > 0
            ? (matchedEntries[0][1].latency
                ?? matchedEntries[0][1].latency_ms
                ?? matchedEntries[0][1].ping)
            : undefined;
        let latency = undefined;
        if (rawLatency === null) {
            latency = null;
        } else if (rawLatency !== undefined && rawLatency !== '') {
            const normalizedLatency = Number(rawLatency);
            latency = Number.isFinite(normalizedLatency) ? normalizedLatency : null;
        }

        // EQSC HTTP 通道优先使用后端状态文案（可用 / 熔断中 / 离线 / 未启用）
        if (!statusLabel) {
            if (status === 'online') {
                statusLabel = connectionType === 'http' ? '可用' : '在线';
            } else if (status === 'offline') {
                statusLabel = circuitOpen ? '熔断中' : '离线';
            } else {
                statusLabel = '未启用';
            }
        }

        return {
            id: target.id,
            name: target.displayName,
            status,
            status_label: statusLabel,
            retry_count: retryCount,
            sub_sources: allSubSources,
            latency,
            connection_type: connectionType,
            circuit_open: circuitOpen,
            compact: !!target.compact,
        };
    };

    // 解析过滤 connections 数据
    const displayColumns = useMemo(() => {
        const targets = [
            {
                id: 'fan',
                displayName: 'FAN Studio',
                matcher: (key) => {
                    const k = String(key || '').toLowerCase();
                    return k.includes('fan') && !k.includes('eqsc');
                },
            },
            {
                id: 'p2p',
                displayName: 'P2P地震情報',
                matcher: (key) => String(key || '').toLowerCase().includes('p2p'),
            },
            {
                id: 'wolfx',
                displayName: 'Wolfx',
                matcher: (key) => {
                    const k = String(key || '').toLowerCase();
                    return key === 'wolfx_all' || k.includes('wolfx');
                },
            },
            {
                id: 'gq',
                displayName: 'Global Quake',
                matcher: (key) => {
                    const k = String(key || '').toLowerCase();
                    return k.includes('global') && !k.includes('eqsc');
                },
                compact: true,
            },
            {
                id: 'eqsc',
                displayName: 'EQSC API',
                connectionType: 'http',
                matcher: (key) => {
                    const k = String(key || '').toLowerCase();
                    return k === 'eqsc' || k.includes('eqsc');
                },
                compact: true,
            },
        ];

        const normalized = targets.map((target) => {
            const matchedEntries = Object.entries(connections || {}).filter(([key]) =>
                target.matcher(key)
            );
            return normalizeConnection(target, matchedEntries);
        });

        // 第 4 列：GQ 上 + EQSC 下，共享同一列高度
        return [
            { type: 'single', items: [normalized[0]] },
            { type: 'single', items: [normalized[1]] },
            { type: 'single', items: [normalized[2]] },
            { type: 'stack', items: [normalized[3], normalized[4]] },
        ];
    }, [connections]);

    /**
     * 网络延迟区间着色器类映射
     */
    const getLatencyTone = (latency) => {
        if (latency < 150) return 'fast';
        if (latency < 460) return 'medium';
        return 'slow';
    };

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
                china_typhoon: '中国气象局：实时活跃台风',
                typhoon_fanstudio: '中国气象局：实时活跃台风',
                japan_jma_eew: '日本气象厅: 紧急地震速报',
            },
            'P2P地震情報': {
                japan_jma_eew: '日本气象厅: 紧急地震速报',
                japan_jma_earthquake: '日本气象厅: 地震情报',
                japan_jma_tsunami: '日本气象厅: 海啸予报',
            },
            Wolfx: {
                japan_jma_eew: '日本气象厅: 紧急地震速报',
                china_cenc_eew: '中国地震预警网 (CEA)',
                taiwan_cwa_eew: '台湾中央气象署: 强震即时警报',
                japan_jma_earthquake: '日本气象厅地震情报',
                china_cenc_earthquake: '中国地震台网地震测定',
            },
            'Global Quake': {
                enabled: '实时数据流',
            },
            'EQSC API': {
                china_typhoon: '中国气象局：实时活跃台风',
            },
        };

        const scopedName = scopedSourceMap[connectionName]?.[rawKey];
        if (scopedName) return scopedName;

        const formattedName = window.formatSourceName
            ? window.formatSourceName(rawKey)
            : rawKey;

        return String(formattedName)
            .replace(/\s+-\s+(Fan|P2P|Wolfx|EQSC)$/i, '')
            .trim();
    };

    /**
     * 渲染单张连接卡片
     */
    const renderConnectionCard = (conn) => {
        const compactClass = conn.compact ? ' connection-item--compact' : '';
        return (
            <Box
                key={conn.id || conn.name}
                className={`connection-item connection-item-${conn.status}${compactClass}`}
            >
                {/* 顶栏：服务名与重连次数、状态指示灯 */}
                <Box className="connection-card-header">
                    <Typography className="connection-title">
                        {conn.name}
                    </Typography>

                    <Box className="connection-status-cluster">
                        {conn.retry_count > 0 && conn.status !== 'disabled' && conn.connection_type !== 'http' && (
                            <Typography variant="caption" className="connection-retry-count">
                                重试: {conn.retry_count}
                            </Typography>
                        )}
                        {conn.circuit_open && conn.status !== 'disabled' && (
                            <Typography variant="caption" className="connection-retry-count">
                                熔断
                            </Typography>
                        )}
                        <div className="connection-indicator"></div>
                    </Box>
                </Box>

                {/* 中部：状态文本与网络延迟 */}
                <Box className="connection-summary">
                    <Typography className="connection-status-label">
                        {conn.status_label}
                    </Typography>

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

                {/* 尾部：子数据源清单 */}
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
                                .sort(([, a], [, b]) => (a === b ? 0 : a ? -1 : 1))
                                .map(([key, enabled]) => {
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
    };

    // 骨架屏：前三列单卡 + 第四列双卡堆叠
    if (!dataLoaded) {
        return (
            <div className="connections-grid status-connections-grid">
                {[1, 2, 3].map((i) => (
                    <div key={i} className="status-connection-skeleton-card">
                        <div className="status-skeleton-row">
                            <div className="skeleton status-skeleton-title"></div>
                            <div className="skeleton status-skeleton-badge"></div>
                        </div>
                        <div className="skeleton status-skeleton-subtitle"></div>
                        <div className="skeleton status-skeleton-subtitle status-skeleton-subtitle--short"></div>
                    </div>
                ))}
                <div className="connection-stack">
                    {[1, 2].map((i) => (
                        <div key={`stack-${i}`} className="status-connection-skeleton-card status-connection-skeleton-card--compact">
                            <div className="status-skeleton-row">
                                <div className="skeleton status-skeleton-title"></div>
                                <div className="skeleton status-skeleton-badge"></div>
                            </div>
                            <div className="skeleton status-skeleton-subtitle status-skeleton-subtitle--short"></div>
                        </div>
                    ))}
                </div>
            </div>
        );
    }

    return (
        <div className="connections-grid status-connections-grid">
            {displayColumns.map((column, columnIndex) => {
                if (column.type === 'stack') {
                    return (
                        <div key={`column-stack-${columnIndex}`} className="connection-stack">
                            {column.items.map((conn) => renderConnectionCard(conn))}
                        </div>
                    );
                }
                return column.items.map((conn) => renderConnectionCard(conn));
            })}
        </div>
    );
}
