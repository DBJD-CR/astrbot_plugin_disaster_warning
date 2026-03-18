const { Box, Typography } = MaterialUI;

/**
 * EEW 查询状态卡片
 * - 展示内容与 /地震预警查询 保持一致
 * - 无 EEW 时长本地每秒跳秒
 * - 状态数据通过 AppContext 的 status.eewQueryStatus 实时更新
 */
function EewStatusCard() {
    const { state } = useAppContext();
    const { status, dataLoaded } = state;
    const eewQueryStatus = status.eewQueryStatus || null;

    // 本地秒级 ticker（用于“无 EEW”时长实时跳秒）
    const [tickNowMs, setTickNowMs] = React.useState(Date.now());
    React.useEffect(() => {
        const timer = setInterval(() => {
            setTickNowMs(Date.now());
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    const parseDateSafe = React.useCallback((value) => {
        if (!value) return null;
        const d = new Date(value);
        return Number.isNaN(d.getTime()) ? null : d;
    }, []);

    const formatElapsed = React.useCallback((seconds) => {
        const total = Math.max(0, Math.floor(Number(seconds) || 0));
        const days = Math.floor(total / 86400);
        const hours = Math.floor((total % 86400) / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const secs = total % 60;

        if (days > 0) return `${days}天${hours}时${minutes}分${secs}秒`;
        if (hours > 0) return `${hours}时${minutes}分${secs}秒`;
        if (minutes > 0) return `${minutes}分${secs}秒`;
        return `${secs}秒`;
    }, []);

    const renderData = React.useMemo(() => {
        const institutions = Array.isArray(eewQueryStatus?.institutions)
            ? eewQueryStatus.institutions
            : [];

        const activeLines = [];
        const inactiveItems = [];
        const noDataLines = [];
        const unavailableLines = [];

        for (const item of institutions) {
            const displayName = item?.display_name || '未知机构';
            const activeName = item?.active_name || displayName;
            const statusText = item?.status;

            if (statusText === 'unavailable') {
                unavailableLines.push(`- ${displayName}：未启用对应数据源开关，无法计算无 EEW 时间`);
                continue;
            }

            if (statusText === 'no_data') {
                noDataLines.push(`- ${displayName}：已启用数据源，但暂无可计算历史数据`);
                continue;
            }

            if (statusText === 'active') {
                const magnitude = item?.magnitude;
                const place = item?.place || '未知地点';
                let magText = '?';
                if (magnitude !== null && magnitude !== undefined) {
                    const num = Number(magnitude);
                    magText = Number.isFinite(num) ? num.toFixed(1) : String(magnitude);
                }
                activeLines.push(`[${activeName}] 当前正在发布地震预警：M ${magText} ${place}`);
                continue;
            }

            // inactive / 其他：实时计算 elapsed（优先 issued_at）
            const issuedAt = parseDateSafe(item?.issued_at);
            let elapsedSeconds = Number(item?.elapsed_seconds) || 0;
            if (issuedAt) {
                elapsedSeconds = Math.max(0, Math.floor((tickNowMs - issuedAt.getTime()) / 1000));
            }
            inactiveItems.push({
                elapsedSeconds,
                text: `${formatElapsed(elapsedSeconds)} 无 ${displayName}`,
            });
        }

        inactiveItems.sort((a, b) => a.elapsedSeconds - b.elapsedSeconds);

        return {
            activeLines,
            inactiveLines: inactiveItems.map((x) => x.text),
            noDataLines,
            unavailableLines,
        };
    }, [eewQueryStatus, tickNowMs, formatElapsed, parseDateSafe]);

    // 骨架屏
    if (!dataLoaded) {
        return (
            <div className="card" style={{ height: '100%' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2.5 }}>
                    <div style={{
                        width: '40px',
                        height: '40px',
                        borderRadius: '10px',
                        background: 'rgba(103, 80, 164, 0.12)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '20px'
                    }}>📡</div>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>地震预警状态</Typography>
                </Box>
                <div className="skeleton" style={{ height: '20px', borderRadius: '6px', marginBottom: '8px' }}></div>
                <div className="skeleton" style={{ height: '20px', borderRadius: '6px', marginBottom: '8px', width: '85%' }}></div>
                <div className="skeleton" style={{ height: '20px', borderRadius: '6px', width: '70%' }}></div>
            </div>
        );
    }

    const { activeLines, inactiveLines, noDataLines, unavailableLines } = renderData;
    const hasStatusData = Array.isArray(eewQueryStatus?.institutions) && eewQueryStatus.institutions.length > 0;

    return (
        <div className="card" style={{ height: '100%' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2.5 }}>
                <div style={{
                    width: '40px',
                    height: '40px',
                    borderRadius: '10px',
                    background: 'rgba(103, 80, 164, 0.12)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '20px'
                }}>📡</div>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>地震预警状态</Typography>
            </Box>

            {!hasStatusData ? (
                <Typography variant="body2" sx={{ opacity: 0.75 }}>当前暂无地震预警状态数据</Typography>
            ) : (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.8 }}>
                    {activeLines.length === 0 ? (
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>当前没有正在生效的地震预警</Typography>
                    ) : (
                        activeLines.map((line, idx) => (
                            <Typography key={`active-${idx}`} variant="body2" sx={{ fontWeight: 600 }}>
                                {line}
                            </Typography>
                        ))
                    )}

                    {inactiveLines.length > 0 && (
                        <>
                            <Box sx={{ height: '8px' }} />
                            {inactiveLines.map((line, idx) => (
                                <Typography key={`inactive-${idx}`} variant="body2" sx={{ opacity: 0.92 }}>
                                    {line}
                                </Typography>
                            ))}
                        </>
                    )}

                    {noDataLines.length > 0 && (
                        <>
                            <Box sx={{ height: '8px' }} />
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>以下机构暂无可计算的历史 EEW 数据：</Typography>
                            {noDataLines.map((line, idx) => (
                                <Typography key={`nodata-${idx}`} variant="body2" sx={{ opacity: 0.85 }}>
                                    {line}
                                </Typography>
                            ))}
                        </>
                    )}

                    {unavailableLines.length > 0 && (
                        <>
                            <Box sx={{ height: '8px' }} />
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>以下机构因数据源开关未启用，无法参与计算：</Typography>
                            {unavailableLines.map((line, idx) => (
                                <Typography key={`unavailable-${idx}`} variant="body2" sx={{ opacity: 0.85 }}>
                                    {line}
                                </Typography>
                            ))}
                        </>
                    )}
                </Box>
            )}
        </div>
    );
}
