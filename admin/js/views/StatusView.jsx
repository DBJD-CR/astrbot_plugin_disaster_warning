const { Box, Button, Typography } = MaterialUI;

function StatusView({ onOpenSimulation }) {
    const { state, refreshData, fetchConnections, fetchConfig } = useAppContext();
    const { status, wsConnected } = state; // 获取 wsConnected 状态
    const [reconnecting, setReconnecting] = React.useState(false);
    const [refreshing, setRefreshing] = React.useState(false);
    const { sendMessage } = useWebSocket(); // 获取 WebSocket 发送消息函数
    const { showToast } = useToast(); // 使用 Toast 提示

    const refreshAll = async () => {
        setRefreshing(true);
        try {
            // 1. 通过 HTTP API 刷新状态
            await Promise.all([
                refreshData(),
                fetchConnections(),
                fetchConfig()
            ]);
            
            // 2. 通过 WebSocket 请求完整更新（如果连接正常）
            if (wsConnected) {
                const sent = sendMessage({ type: 'refresh' });
                if (!sent) {
                    console.warn('[StatusView] WebSocket 未连接，跳过实时刷新请求');
                }
            } else {
                console.warn('[StatusView] WebSocket 未连接，仅通过 HTTP API 刷新');
            }
            
            // 3. 延迟一点点关闭刷新状态，让动画更明显
            await new Promise(resolve => setTimeout(resolve, 500));
        } catch (e) {
            console.error('刷新数据失败:', e);
        } finally {
            // 清理刷新状态，使 UI 与实际刷新生命周期保持一致
            setRefreshing(false);
        }
    };

    const handleReconnect = async () => {
        // 如果所有连接都正常，提示用户确认
        if (status.activeConnections === status.totalConnections && status.totalConnections > 0) {
            if (!confirm('当前所有连接均正常，确定要强制执行重连操作吗？\n这可能会导致短暂的连接中断。')) {
                return;
            }
        }

        setReconnecting(true);
        try {
            const response = await fetch(`${state.config.apiUrl || ''}/api/reconnect`, {
                method: 'POST'
            });
            const result = await response.json();
            
            if (result.success) {
                // 成功后延迟一点刷新数据，给重连一些时间
                setTimeout(() => {
                    refreshData();
                    setReconnecting(false);
                    showToast(result.message || '重连操作已触发', 'success');
                }, 1000);
            } else {
                showToast('重连失败: ' + (result.error || '未知错误'), 'error');
                setReconnecting(false);
            }
        } catch (e) {
            console.error('Reconnect failed:', e);
            showToast('请求失败，请检查网络连接', 'error');
            setReconnecting(false);
        }
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
                            <button
                                className="btn btn-action"
                                onClick={onOpenSimulation}
                            >
                                <span style={{ fontSize: '18px' }}>🧪</span>
                                模拟预警仿真
                            </button>
                            
                            <button
                                className="btn btn-action"
                                onClick={handleReconnect}
                                disabled={reconnecting || !status.running}
                                style={{
                                    opacity: status.running ? 1 : 0.5,
                                    cursor: status.running ? 'pointer' : 'not-allowed'
                                }}
                                title="强制重连所有已启用但离线的数据源"
                            >
                                {reconnecting ? (
                                    <>
                                        <span className="spinner" style={{
                                            width: '14px',
                                            height: '14px',
                                            border: '2px solid rgba(0,0,0,0.2)',
                                            borderTopColor: 'var(--md-sys-color-primary)',
                                            borderRadius: '50%'
                                        }}></span>
                                        处理中...
                                    </>
                                ) : (
                                    <>
                                        <span style={{ fontSize: '18px' }}>🔌</span>
                                        手动重连数据源
                                    </>
                                )}
                            </button>

                            <button
                                className="btn btn-action"
                                onClick={refreshAll}
                                disabled={refreshing}
                            >
                                {refreshing ? (
                                    <>
                                        <span className="spinner" style={{
                                            width: '14px',
                                            height: '14px',
                                            border: '2px solid rgba(0,0,0,0.2)',
                                            borderTopColor: 'var(--md-sys-color-primary)',
                                            borderRadius: '50%'
                                        }}></span>
                                        刷新中...
                                    </>
                                ) : (
                                    <>
                                        <span style={{ fontSize: '18px' }}>🔄</span>
                                        刷新控制台数据
                                    </>
                                )}
                            </button>
                        </Box>
                    </div>
                </div>

                <div className="span-12">
                    <ConnectionsGrid />
                </div>
            </div>
        </Box>
    );
}
