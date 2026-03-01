const { Box, Typography } = MaterialUI;

/**
 * 系统状态卡片组件
 * 展示核心服务的运行状态、运行时长以及活跃连接数
 */
function StatusCard() {
    const { state } = useAppContext();
    const { status, dataLoaded } = state;

    // 骨架屏
    if (!dataLoaded) {
        return (
            <div className="card" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
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
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, justifyContent: 'center' }}>
                    <div className="skeleton" style={{ height: '24px', borderRadius: '6px' }}></div>
                    <div className="skeleton" style={{ height: '24px', borderRadius: '6px' }}></div>
                    <div className="skeleton" style={{ height: '24px', borderRadius: '6px' }}></div>
                </Box>
            </div>
        );
    }

    return (
        <div className="card" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
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

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, justifyContent: 'center' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="body2" sx={{ opacity: 0.7, fontWeight: 500 }}>运行状态</Typography>
                    <span className={`badge ${status.running ? 'badge-success' : 'badge-error'}`}>
                        {status.running ? '运行中' : '已停止'}
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

                {/* 启用的子数据源统计 */}
                {status.subSourceStatus && (
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2" sx={{ opacity: 0.7, fontWeight: 500 }}>启用的子数据源</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {(() => {
                                let enabledCount = 0;
                                let totalCount = 0;
                                Object.values(status.subSourceStatus).forEach(group => {
                                    Object.values(group).forEach(enabled => {
                                        totalCount++;
                                        if (enabled) enabledCount++;
                                    });
                                });
                                return `${enabledCount} / ${totalCount}`;
                            })()}
                        </Typography>
                    </div>
                )}
            </Box>
        </div>
    );
}
