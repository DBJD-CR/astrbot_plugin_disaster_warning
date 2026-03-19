const { Box, Typography } = MaterialUI;

/**
 * 统计信息卡片组件
 * 展示系统记录的各类事件总数，包括地震、预警、气象和海啸
 *
 * @param {Object} props
 * @param {Object} props.style - 自定义样式对象
 */
function StatsCard({ style }) {
    const { state } = useAppContext();
    const { stats, dataLoaded } = state;
    const safeStats = {
        totalEvents: 0,
        earthquakeCount: 0,
        warningCount: 0,
        weatherCount: 0,
        tsunamiCount: 0,
        ...(stats || {})
    };

    // 骨架屏
    if (!dataLoaded) {
        return (
            <div className="card" style={{ height: '100%', display: 'flex', flexDirection: 'column', ...(style || {}) }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                    <div style={{ 
                        width: '40px', 
                        height: '40px', 
                        borderRadius: '10px', 
                        background: 'rgba(139, 92, 246, 0.1)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '20px'
                    }}>📊</div>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>事件统计</Typography>
                </Box>
                <Box sx={{ py: 1, flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <div className="skeleton" style={{ height: '48px', borderRadius: '8px', marginBottom: '12px' }}></div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
                        <div className="skeleton" style={{ height: '64px', borderRadius: '8px' }}></div>
                        <div className="skeleton" style={{ height: '64px', borderRadius: '8px' }}></div>
                        <div className="skeleton" style={{ height: '64px', borderRadius: '8px' }}></div>
                        <div className="skeleton" style={{ height: '64px', borderRadius: '8px' }}></div>
                    </div>
                </Box>
            </div>
        );
    }

    return (
        <div className="card" style={{ height: '100%', display: 'flex', flexDirection: 'column', ...(style || {}) }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                <div style={{ 
                    width: '40px', 
                    height: '40px', 
                    borderRadius: '10px', 
                    background: 'rgba(139, 92, 246, 0.1)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '20px'
                }}>📊</div>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>事件统计</Typography>
            </Box>

            <Box sx={{ py: 1, flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                <Typography variant="h2" sx={{
                    fontWeight: 800,
                    color: 'var(--md-sys-color-primary)',
                    lineHeight: 1,
                    letterSpacing: '-2px'
                }}>
                    {safeStats.totalEvents}
                </Typography>
                <Typography variant="body2" sx={{ opacity: 0.6, fontWeight: 600, mt: 1, ml: 0.5 }}>
                    事件总数
                </Typography>
            </Box>

            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2, mt: 3, pt: 2, borderTop: '1px solid var(--md-sys-color-outline-variant)' }}>
                <Box>
                    <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem' }}>{safeStats.earthquakeCount}</Typography>
                    <Typography variant="caption" sx={{ opacity: 0.5, fontWeight: 600 }}>地震事件</Typography>
                </Box>
                <Box>
                    <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem' }}>
                        {(safeStats.warningCount !== undefined && safeStats.warningCount !== null) ? safeStats.warningCount : '-'}
                    </Typography>
                    <Typography variant="caption" sx={{ opacity: 0.5, fontWeight: 600 }}>地震预警</Typography>
                </Box>
                <Box>
                    <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem' }}>{safeStats.weatherCount}</Typography>
                    <Typography variant="caption" sx={{ opacity: 0.5, fontWeight: 600 }}>气象预警</Typography>
                </Box>
                <Box>
                    <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem' }}>{safeStats.tsunamiCount}</Typography>
                    <Typography variant="caption" sx={{ opacity: 0.5, fontWeight: 600 }}>海啸预警</Typography>
                </Box>
            </Box>
        </div>
    );
}
