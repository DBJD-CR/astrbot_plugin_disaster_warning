const { Box, Typography } = MaterialUI;
const { useMemo } = React;

/**
 * 连接状态网格组件 (ConnectionsGrid)
 * 显示主流数据源（FAN Studio / P2P / Wolfx / Global Quake）与 HTTP 辅助通道
 * EQSC、NIED S-Net 的实时连接情况、TCP 延迟、重试次数以及启用的子数据源明细。
 *
 * 布局：
 * - 第 1 列：FAN Studio
 * - 第 2 列：P2P + NIED S-Net 上下堆叠（connection-stack）
 * - 第 3 列：Wolfx
 * - 第 4 列：Global Quake + EQSC API 上下堆叠
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
            // 多条命中时优先选“更像真实运行态”的条目，避免 catalog 占位
            // （status=未连接 / 无 connection_type）盖过 HTTP 通道的正式状态。
            const rankedEntries = matchedEntries.slice().sort((a, b) => {
                const infoA = a[1] || {};
                const infoB = b[1] || {};
                const score = (info) => {
                    let value = 0;
                    const statusText = String(info.status || '');
                    if (info.connection_type === 'http') value += 8;
                    if (statusText && statusText !== '未连接') value += 4;
                    if (Object.prototype.hasOwnProperty.call(info, 'access_token_valid')) value += 2;
                    if (info.connected) value += 1;
                    // 明确降权“未连接”占位，防止它抢到 primary
                    if (statusText === '未连接') value -= 10;
                    return value;
                };
                return score(infoB) - score(infoA);
            });

            const primary = rankedEntries[0][1] || {};
            connectionType = primary.connection_type || connectionType;
            circuitOpen = !!primary.circuit_open;
            if (primary.status) {
                statusLabel = String(primary.status);
            }

            // EQSC：若正式条目里带有 access_token_valid，强制用鉴权语义覆盖“未连接”占位
            if (target.id === 'eqsc') {
                const authEntry = rankedEntries.find(([, info]) =>
                    info && Object.prototype.hasOwnProperty.call(info, 'access_token_valid')
                );
                if (authEntry) {
                    const authInfo = authEntry[1] || {};
                    connectionType = authInfo.connection_type || 'http';
                    circuitOpen = !!authInfo.circuit_open;
                    if (authInfo.status) {
                        statusLabel = String(authInfo.status);
                    } else if (authInfo.access_token_valid) {
                        statusLabel = '可用';
                    } else if (authInfo.enabled) {
                        statusLabel = circuitOpen ? '熔断中' : '鉴权失效';
                    }
                }
            }

            const isEnabled = rankedEntries.some(([, info]) => !!info.enabled);
            if (isEnabled) {
                const isConnected = rankedEntries.some(([, info]) => !!info.connected);
                status = isConnected ? 'online' : 'offline';
            }

            // 后续 sub_sources / latency 也基于排序后的结果合并，避免脏占位优先。
            matchedEntries = rankedEntries;
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

        // EQSC 只展示业务子开关：台风富化 + 海啸轮询。
        // catalog 占位可能带上 jma_tsunami_eqsc（source_id），需要过滤掉，避免出现第三条重复海啸。
        if (target.id === 'eqsc') {
            const eqscAllowedKeys = new Set([
                'china_typhoon',
                'jma_tsunami',
                'japan_jma_tsunami',
            ]);
            Object.keys(allSubSources).forEach((key) => {
                if (!eqscAllowedKeys.has(key)) {
                    delete allSubSources[key];
                }
            });
        }

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

        // HTTP 通道（EQSC / S-Net）优先使用后端状态文案（可用 / 轮询中 / 离线 / 未启用）
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
                compact: true,
            },
            {
                id: 'snet',
                displayName: 'NIED S-Net',
                connectionType: 'http',
                matcher: (key) => {
                    const k = String(key || '').toLowerCase();
                    return k.includes('s-net') || k.includes('snet') || k.includes('nied');
                },
                compact: true,
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
                    const k = String(key || '').toLowerCase().trim();
                    // 优先匹配展示名；兼容历史原始键 eqsc，但排除其它误匹配。
                    return k === 'eqsc api' || k === 'eqsc';
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

        // 第 2 列：P2P 上 + S-Net 下；第 4 列：GQ 上 + EQSC 下
        return [
            { type: 'single', items: [normalized[0]] },
            { type: 'stack', items: [normalized[1], normalized[2]] },
            { type: 'single', items: [normalized[3]] },
            { type: 'stack', items: [normalized[4], normalized[5]] },
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
                china_cenc_intensity_report: '中国地震台网 (CENC) 烈度速报',
                cenc_ir_fanstudio: '中国地震台网 (CENC) 烈度速报',
                usgs_earthquake: '美国地质调查局 (USGS)',
                usa_shakealert: '美国 ShakeAlert 地震预警',
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
            'NIED S-Net': {
                snet_msil: '日本海沟 S-Net 海底震度计',
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
                // 与 P2P 子源展示名一致，仅展示一个海啸入口
                jma_tsunami: '日本气象厅: 海啸予报',
                japan_jma_tsunami: '日本气象厅: 海啸予报',
            },
        };

        const scopedName = scopedSourceMap[connectionName]?.[rawKey];
        if (scopedName) return scopedName;

        const formattedName = window.formatSourceName
            ? window.formatSourceName(rawKey)
            : rawKey;

        return String(formattedName)
            .replace(/\s+-\s+(Fan|P2P|Wolfx|EQSC|S-Net|SNET)$/i, '')
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
                                .sort(([keyA, enabledA], [keyB, enabledB]) => {
                                    // EQSC：台风在上、海啸在下；其余仍优先展示已启用项
                                    if (conn.name === 'EQSC API') {
                                        const eqscOrder = {
                                            china_typhoon: 0,
                                            jma_tsunami: 1,
                                            japan_jma_tsunami: 1,
                                        };
                                        const orderA = eqscOrder[keyA];
                                        const orderB = eqscOrder[keyB];
                                        if (orderA !== undefined || orderB !== undefined) {
                                            return (orderA ?? 99) - (orderB ?? 99);
                                        }
                                    }
                                    return enabledA === enabledB ? 0 : enabledA ? -1 : 1;
                                })
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

    // 骨架屏：第 1/3 列单卡，第 2/4 列双卡堆叠（P2P+S-Net / GQ+EQSC）
    if (!dataLoaded) {
        return (
            <div className="connections-grid status-connections-grid">
                <div className="status-connection-skeleton-card">
                    <div className="status-skeleton-row">
                        <div className="skeleton status-skeleton-title"></div>
                        <div className="skeleton status-skeleton-badge"></div>
                    </div>
                    <div className="skeleton status-skeleton-subtitle"></div>
                    <div className="skeleton status-skeleton-subtitle status-skeleton-subtitle--short"></div>
                </div>
                <div className="connection-stack">
                    {[1, 2].map((i) => (
                        <div key={`stack-p2p-${i}`} className="status-connection-skeleton-card status-connection-skeleton-card--compact">
                            <div className="status-skeleton-row">
                                <div className="skeleton status-skeleton-title"></div>
                                <div className="skeleton status-skeleton-badge"></div>
                            </div>
                            <div className="skeleton status-skeleton-subtitle status-skeleton-subtitle--short"></div>
                        </div>
                    ))}
                </div>
                <div className="status-connection-skeleton-card">
                    <div className="status-skeleton-row">
                        <div className="skeleton status-skeleton-title"></div>
                        <div className="skeleton status-skeleton-badge"></div>
                    </div>
                    <div className="skeleton status-skeleton-subtitle"></div>
                    <div className="skeleton status-skeleton-subtitle status-skeleton-subtitle--short"></div>
                </div>
                <div className="connection-stack">
                    {[1, 2].map((i) => (
                        <div key={`stack-gq-${i}`} className="status-connection-skeleton-card status-connection-skeleton-card--compact">
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
