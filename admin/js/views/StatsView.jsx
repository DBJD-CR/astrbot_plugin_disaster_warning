const { Box } = MaterialUI;

function StatsView() {
    return (
        <Box>
            <div className="dashboard-grid">
                <div className="span-8">
                    <MagnitudeChart />
                </div>
                <div className="span-4">
                    <StatsCard />
                    <div className="card" style={{ marginTop: '24px', background: 'var(--md-sys-color-primary-container)', color: 'var(--md-sys-color-on-primary-container)', border: 'none' }}>
                        <h4 style={{ fontWeight: 800, marginBottom: '12px' }}>📊 数据摘要</h4>
                        <p style={{ fontSize: '14px', opacity: 0.8, lineHeight: 1.6 }}>
                            统计信息每 5 分钟自动更新一次。您可以从这些图表中观察到近期灾害活动的强度分布和频率趋势。
                        </p>
                    </div>
                </div>
            </div>
        </Box>
    );
}
