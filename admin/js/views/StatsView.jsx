const { Box } = MaterialUI;

function StatsView() {
    const { state } = useAppContext();
    const { stats } = state;
    
    const sources = stats && stats.dataSources ? stats.dataSources : [];
    const eqRegions = stats && stats.earthquakeRegions ? stats.earthquakeRegions : [];
    const weatherTypes = stats && stats.weatherTypes ? stats.weatherTypes : [];
    const weatherRegions = stats && stats.weatherRegions ? stats.weatherRegions : [];

    return (
        <Box>
            <div className="dashboard-grid">
                {/* 第一行：左侧震级图，右侧统计卡片和最大地震 */}
                {/* 使用 grid 嵌套，强制左边大卡片和右边两个小卡片组等高 */}
                <div style={{ gridColumn: 'span 12', display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '24px', alignItems: 'stretch' }}>
                    <div style={{ gridColumn: 'span 8', display: 'flex' }}>
                        <div style={{ width: '100%', display: 'flex', flexDirection: 'column' }}>
                            <MagnitudeChart style={{ flex: 1 }} />
                        </div>
                    </div>
                    <div style={{ gridColumn: 'span 4', display: 'flex', flexDirection: 'column', gap: '24px' }}>
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                            <StatsCard style={{ flex: 1, height: '100%' }} />
                        </div>
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                             <MaxMagCard />
                        </div>
                    </div>
                </div>

                {/* 时间维度统计：趋势图和热力图 */}
                <div className="span-12">
                    <TrendChart style={{ height: '100%', minHeight: '300px' }} />
                </div>
                <div className="span-12">
                    <CalendarHeatmap style={{ height: '100%', minHeight: '220px' }} />
                </div>

                {/* 第二行：三个 Top 榜单 (地震地区、气象类型、数据源) */}
                <div className="span-4">
                    <TopListCard title="国内地震高发地 (TOP 10)" icon="📍" data={eqRegions} color="#FF9800" />
                </div>
                <div className="span-4">
                    <TopListCard title="气象预警类型 (TOP 10)" icon="⛈️" data={weatherTypes} color="#4CAF50" />
                </div>
                <div className="span-4">
                    <TopListCard title="数据源贡献 (TOP 10)" icon="📡" data={sources} color="#2196F3" />
                </div>

                {/* 第三行：新增气象地区、气象级别、日志统计 */}
                <div className="span-4">
                    <TopListCard title="气象预警地区分布 (TOP 10)" icon="🗺️" data={weatherRegions} color="#00ACC1" />
                </div>
                <div className="span-4">
                    <WeatherLevelCard />
                </div>
                <div className="span-4">
                    <LogStatsCard />
                </div>

                <div className="span-12">
                    <div className="card" style={{ background: 'var(--md-sys-color-primary-container)', color: 'var(--md-sys-color-on-primary-container)', border: 'none' }}>
                        <h4 style={{ fontWeight: 800, marginBottom: '12px' }}>📊 数据摘要</h4>
                        <p style={{ fontSize: '14px', opacity: 0.8, lineHeight: 1.6 }}>
                            统计信息会自动实时更新。您可以从这些图表中直观的观察到灾害活动的强度分布和频率。
                        </p>
                    </div>
                </div>
            </div>
        </Box>
    );
}
