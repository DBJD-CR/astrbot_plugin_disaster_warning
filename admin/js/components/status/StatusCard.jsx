const { Box, Typography } = MaterialUI;

/**
 * 服务状态摘要指标展示卡片组件 (StatusCard)
 * 用于展示预警系统核心进程的运行状态（运行中、已停止）、
 * 宿主程序运行以来的累计运行时长 (Uptime)、活跃长连接与总连接比例、
 * 以及当前全局配置已启用的子数据源总比例。
 */
function StatusCard() {
    const { state } = useAppContext();
    const { status, dataLoaded } = state;

    // 1. 状态：当连接数据尚未加载完毕前，渲染骨架条
    if (!dataLoaded) {
        return (
            <div className="card status-card-fill">
                <Box className="status-card-header">
                    <div className="status-card-icon status-card-icon--service">⚡</div>
                    <Typography variant="h6" className="status-card-title">服务状态</Typography>
                </Box>
                <Box className="status-card-skeleton-stack">
                    <div className="skeleton status-skeleton-line"></div>
                    <div className="skeleton status-skeleton-line"></div>
                    <div className="skeleton status-skeleton-line"></div>
                </Box>
            </div>
        );
    }

    return (
        <div className="card status-card-fill">
            {/* 卡片头部标题与图标 */}
            <Box className="status-card-header">
                <div className="status-card-icon status-card-icon--service">⚡</div>
                <Typography variant="h6" className="status-card-title">服务状态</Typography>
            </Box>

            {/* 卡片主状态数值内容区 */}
            <Box className="status-card-body">
                {/* A. 核心程序运行状态指示标签 */}
                <div className="status-card-row status-card-row--center">
                    <Typography variant="body2" className="status-card-label">运行状态</Typography>
                    <span className={`badge ${status.running ? 'badge-success' : 'badge-error'}`}>
                        {status.running ? '运行中' : '已停止'}
                    </span>
                </div>
                
                <div className="status-card-separator"></div>

                {/* B. 系统累计持续运行时长 (Uptime)，由前端时钟同步累加 */}
                <div className="status-card-row">
                    <Typography variant="body2" className="status-card-label">运行时长</Typography>
                    <Typography variant="body2" className="status-card-value">
                        {status.uptime || '00:00:00'}
                    </Typography>
                </div>

                {/* C. WebSocket 实时活跃连接/总连接数 */}
                <div className="status-card-row">
                    <Typography variant="body2" className="status-card-label">活跃连接</Typography>
                    <Typography variant="body2" className="status-card-value">
                        {status.activeConnections} <span className="status-card-ratio-separator">/</span> {status.totalConnections}
                    </Typography>
                </div>

                {/* D. 全局子数据源已启用详情比例统计 */}
                {status.subSourceStatus && (
                    <div className="status-card-row">
                        <Typography variant="body2" className="status-card-label">启用的子数据源</Typography>
                        <Typography variant="body2" className="status-card-value">
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
