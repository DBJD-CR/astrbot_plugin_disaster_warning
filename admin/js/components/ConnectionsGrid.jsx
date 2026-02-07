const { Box, Typography } = MaterialUI;
const { useMemo } = React;

function ConnectionsGrid() {
    const { state } = useAppContext();
    const { connections } = state;

    const sortedConnections = useMemo(() => {
        return Object.entries(connections).sort((a, b) => a[0].localeCompare(b[0]));
    }, [connections]);

    if (sortedConnections.length === 0) {
        return (
            <div className="card" style={{ textAlign: 'center', padding: '40px' }}>
                <Typography variant="body1" sx={{ opacity: 0.5 }}>暂无活跃的数据源连接</Typography>
            </div>
        );
    }

    return (
        <div className="connections-grid">
            {sortedConnections.map(([name, info]) => (
                <div key={name} className={`connection-item ${info.connected ? 'connected' : 'disconnected'}`}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                        <Typography className="conn-name" sx={{ fontWeight: 700 }}>
                            {name}
                        </Typography>
                        <div style={{ 
                            width: '8px', 
                            height: '8px', 
                            borderRadius: '50%', 
                            background: info.connected ? '#4CAF50' : '#F44336',
                            boxShadow: `0 0 6px ${info.connected ? '#4CAF50' : '#F44336'}`
                        }}></div>
                    </Box>
                    <div className="conn-status">
                        <span>{info.connected ? 'ONLINE' : 'OFFLINE'}</span>
                        {info.retry_count > 0 && (
                            <span style={{ opacity: 0.6 }}>Retries: {info.retry_count}</span>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
}
