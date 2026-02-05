const { Box, Typography, Card, CardContent } = MaterialUI;
const { useMemo } = React;

function MagnitudeChart() {
    const { state } = useAppContext();
    const { magnitudeDistribution } = state;

    const magnitudeOrder = [
        "< M3.0", "M3.0 - M3.9", "M4.0 - M4.9", "M5.0 - M5.9", "M6.0 - M6.9", "M7.0 - M7.9", ">= M8.0"
    ];

    const chartData = useMemo(() => {
        const data = magnitudeOrder.map(label => ({
            label,
            value: magnitudeDistribution[label] || 0
        }));

        const maxValue = Math.max(...data.map(d => d.value), 1);
        return data.map(d => ({
            ...d,
            percentage: (d.value / maxValue) * 100
        }));
    }, [magnitudeDistribution]);

    if (Object.keys(magnitudeDistribution).length === 0) {
        return (
            <Box sx={{ my: 2 }}>
                <Typography variant="h6" gutterBottom>📈 震级分布</Typography>
                <Card>
                    <CardContent>
                        <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 5 }}>
                            加载中...
                        </Typography>
                    </CardContent>
                </Card>
            </Box>
        );
    }

    return (
        <Box sx={{ my: 2 }}>
            <Typography variant="h6" gutterBottom>📈 震级分布</Typography>
            <Card>
                <CardContent>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                        {chartData.map((item, index) => (
                            <Box key={index}>
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                                    <Typography variant="caption" color="text.secondary">
                                        {item.label}
                                    </Typography>
                                    <Typography variant="caption" sx={{ fontWeight: 600 }}>
                                        {item.value}
                                    </Typography>
                                </Box>
                                <Box sx={{
                                    width: '100%',
                                    height: 8,
                                    bgcolor: 'divider',
                                    borderRadius: 1,
                                    overflow: 'hidden'
                                }}>
                                    <Box sx={{
                                        width: `${item.percentage}%`,
                                        height: '100%',
                                        bgcolor: 'primary.main',
                                        transition: 'width 0.3s ease'
                                    }} />
                                </Box>
                            </Box>
                        ))}
                    </Box>
                </CardContent>
            </Card>
        </Box>
    );
}
