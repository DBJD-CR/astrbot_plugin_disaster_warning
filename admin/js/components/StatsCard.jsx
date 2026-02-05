const { Card, CardContent, Typography, Box, Divider } = MaterialUI;

function StatsCard() {
    const { state } = useAppContext();
    const { stats } = state;

    return (
        <Card>
            <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                    <span style={{ fontSize: '24px' }}>📊</span>
                    <Typography variant="h6">事件统计</Typography>
                </Box>

                <Typography variant="h3" color="primary" sx={{ fontWeight: 400 }}>
                    {stats.totalEvents}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
                    总事件数
                </Typography>

                <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <span style={{ fontSize: '14px' }}>🌍</span>
                        <Typography variant="caption">
                            <strong>{stats.earthquakeCount}</strong> 地震
                        </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <span style={{ fontSize: '14px' }}>🌊</span>
                        <Typography variant="caption">
                            <strong>{stats.tsunamiCount}</strong> 海啸
                        </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <span style={{ fontSize: '14px' }}>☁️</span>
                        <Typography variant="caption">
                            <strong>{stats.weatherCount}</strong> 气象
                        </Typography>
                    </Box>
                </Box>
            </CardContent>
        </Card>
    );
}
