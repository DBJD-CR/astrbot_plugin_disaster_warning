const { Box, Typography } = MaterialUI;

function StatsCard() {
    const { state } = useAppContext();
    const { stats } = state;

    return (
        <div className="card">
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

            <Box sx={{ py: 1 }}>
                <Typography variant="h2" sx={{ 
                    fontWeight: 800, 
                    color: 'var(--md-sys-color-primary)',
                    lineHeight: 1,
                    letterSpacing: '-2px'
                }}>
                    {stats.totalEvents}
                </Typography>
                <Typography variant="body2" sx={{ opacity: 0.6, fontWeight: 600, mt: 1, ml: 0.5 }}>
                    TOTAL EVENTS
                </Typography>
            </Box>

            <Box sx={{ display: 'flex', gap: 2, mt: 3, pt: 2, borderTop: '1px solid var(--md-sys-color-outline-variant)' }}>
                <Box sx={{ flex: 1 }}>
                    <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem' }}>{stats.earthquakeCount}</Typography>
                    <Typography variant="caption" sx={{ opacity: 0.5, fontWeight: 600 }}>EARTHQUAKE</Typography>
                </Box>
                <Box sx={{ flex: 1 }}>
                    <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem' }}>{stats.tsunamiCount}</Typography>
                    <Typography variant="caption" sx={{ opacity: 0.5, fontWeight: 600 }}>TSUNAMI</Typography>
                </Box>
                <Box sx={{ flex: 1 }}>
                    <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem' }}>{stats.weatherCount}</Typography>
                    <Typography variant="caption" sx={{ opacity: 0.5, fontWeight: 600 }}>WEATHER</Typography>
                </Box>
            </Box>
        </div>
    );
}
