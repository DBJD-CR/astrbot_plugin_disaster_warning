const { Box, Typography } = MaterialUI;

function StatusCard() {
    const { state } = useAppContext();
    const { status } = state;

    return (
        <div className="card">
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
                <div style={{ 
                    width: '40px', 
                    height: '40px', 
                    borderRadius: '10px', 
                    background: 'rgba(59, 130, 246, 0.1)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '20px'
                }}>⚡</div>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>服务状态</Typography>
            </Box>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="body2" sx={{ opacity: 0.7, fontWeight: 500 }}>运行状态</Typography>
                    <span className={`badge ${status.running ? 'badge-success' : 'badge-error'}`}>
                        {status.running ? 'Running' : 'Stopped'}
                    </span>
                </div>
                
                <div style={{ height: '1px', background: 'var(--md-sys-color-outline-variant)' }}></div>

                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" sx={{ opacity: 0.7, fontWeight: 500 }}>运行时长</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{status.uptime || '00:00:00'}</Typography>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" sx={{ opacity: 0.7, fontWeight: 500 }}>活跃连接</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {status.activeConnections} <span style={{ opacity: 0.4 }}>/</span> {status.totalConnections}
                    </Typography>
                </div>
            </Box>
        </div>
    );
}
