const { Card, CardContent, Typography, Box, Chip } = MaterialUI;

function StatusCard() {
    const { state } = useAppContext();
    const { status } = state;

    return (
        <Card>
            <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                    <span style={{ fontSize: '24px' }}>🔄</span>
                    <Typography variant="h6">服务状态</Typography>
                </Box>

                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="body2">运行状态</Typography>
                        <Chip
                            label={status.running ? '运行中' : '已停止'}
                            color={status.running ? 'success' : 'error'}
                            size="small"
                        />
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2" color="text.secondary">运行时长</Typography>
                        <Typography variant="body2">{status.uptime}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2" color="text.secondary">活跃连接</Typography>
                        <Typography variant="body2">{status.activeConnections} / {status.totalConnections}</Typography>
                    </Box>
                </Box>
            </CardContent>
        </Card>
    );
}
