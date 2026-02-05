const { Box, Typography, Paper } = MaterialUI;
const { useMemo } = React;

function ConnectionsGrid() {
    const { state } = useAppContext();
    const { connections } = state;

    const sortedConnections = useMemo(() => {
        return Object.entries(connections).sort((a, b) => a[0].localeCompare(b[0]));
    }, [connections]);

    if (sortedConnections.length === 0) {
        return (
            <Box sx={{ my: 2 }}>
                <Typography variant="h6" gutterBottom>📡 数据源连接状态</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 2 }}>
                    暂无连接
                </Typography>
            </Box>
        );
    }

    return (
        <Box sx={{ my: 2 }}>
            <Typography variant="h6" gutterBottom>📡 数据源连接状态</Typography>
            <Box sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                gap: 1.5
            }}>
                {sortedConnections.map(([name, info]) => (
                    <Paper
                        key={name}
                        sx={{
                            p: 1.5,
                            border: 1,
                            borderColor: info.connected ? 'success.main' : 'divider',
                            bgcolor: info.connected ? 'rgba(76, 175, 80, 0.05)' : 'background.paper',
                            opacity: info.connected ? 1 : 0.75
                        }}
                    >
                        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                            {name}
                        </Typography>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5 }}>
                            <Typography variant="caption" color={info.connected ? 'success.main' : 'error.main'}>
                                {info.connected ? '✅ 在线' : '❌ 离线'}
                            </Typography>
                            {info.retry_count > 0 && (
                                <Typography variant="caption" color="text.secondary">
                                    重试: {info.retry_count}
                                </Typography>
                            )}
                        </Box>
                    </Paper>
                ))}
            </Box>
        </Box>
    );
}
