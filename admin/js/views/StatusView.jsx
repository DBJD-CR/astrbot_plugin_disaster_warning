const { Box, Button, Typography } = MaterialUI;

function StatusView({ onOpenSimulation }) {
    const refreshAll = () => {
        window.location.reload();
    };

    return (
        <Box>
            <div className="dashboard-grid">
                {/* 顶部跑马灯 */}
                <div className="span-12">
                    <NewsTicker />
                </div>

                <div className="span-4">
                    <StatusCard />
                </div>
                <div className="span-4">
                    <StatsCard />
                </div>
                <div className="span-4">
                    <div className="card" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
                            <div style={{ 
                                width: '40px', 
                                height: '40px', 
                                borderRadius: '10px', 
                                background: 'rgba(236, 72, 153, 0.1)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                fontSize: '20px'
                            }}>🚀</div>
                            <Typography variant="h6" sx={{ fontWeight: 700 }}>快捷操作</Typography>
                        </Box>
                        
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, justifyContent: 'center' }}>
                            <button className="btn btn-primary" onClick={onOpenSimulation} style={{ width: '100%' }}>
                                模拟预警仿真
                            </button>
                            <button className="btn" onClick={refreshAll} style={{ 
                                width: '100%', 
                                background: 'rgba(0,0,0,0.05)',
                                color: 'var(--md-sys-color-on-surface)'
                            }}>
                                刷新控制台数据
                            </button>
                        </Box>
                    </div>
                </div>

                {/* 重大事件时间轴 */}
                <div className="span-12">
                    <HorizontalTimeline />
                </div>

                <div className="span-12" style={{ marginTop: '12px' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2, ml: 1 }}>
                        <Typography variant="h6" sx={{ fontWeight: 700, opacity: 0.8 }}>活跃连接</Typography>
                        <div style={{ flex: 1, height: '1px', background: 'var(--md-sys-color-outline-variant)', marginLeft: '12px' }}></div>
                    </Box>
                    <ConnectionsGrid />
                </div>
            </div>
        </Box>
    );
}
