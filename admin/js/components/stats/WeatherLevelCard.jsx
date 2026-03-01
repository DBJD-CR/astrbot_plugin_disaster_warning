const { Typography } = MaterialUI;

function WeatherLevelCard({ style }) {
    const { state } = useAppContext();
    const { stats } = state;
    const rawWeatherLevels = stats && stats.weatherLevels ? stats.weatherLevels : [];
    const weatherLevels = (Array.isArray(rawWeatherLevels) ? rawWeatherLevels : [])
        .map(item => {
            const count = Number(item?.count);
            return {
                level: item?.level || '未知级别',
                count: Number.isFinite(count) && count > 0 ? count : 0
            };
        })
        .filter(item => item.count > 0);

    if (weatherLevels.length === 0) {
        return (
            <div className="card" style={{ height: '100%', minHeight: '200px', ...style }}>
                <div className="chart-card-header">
                    <span style={{ fontSize: '20px' }}>🎨</span>
                    <Typography variant="h6">气象预警级别</Typography>
                </div>
                <Typography variant="body2" sx={{ opacity: 0.5, textAlign: 'center', py: 4 }}>暂无数据</Typography>
            </div>
        );
    }

    const total = weatherLevels.reduce((acc, curr) => acc + curr.count, 0);
    let currentAngle = 0;

    if (total <= 0) {
        return (
            <div className="card" style={{ height: '100%', minHeight: '200px', ...style }}>
                <div className="chart-card-header">
                    <span style={{ fontSize: '20px' }}>🎨</span>
                    <Typography variant="h6">气象预警级别</Typography>
                </div>
                <Typography variant="body2" sx={{ opacity: 0.5, textAlign: 'center', py: 4 }}>暂无有效统计数据</Typography>
            </div>
        );
    }

    // 颜色映射
    const getColor = (level) => {
        const text = String(level || '');
        if (text.includes('红')) return '#F94543';
        if (text.includes('橙')) return '#FF7639';
        if (text.includes('黄')) return '#FCD952';
        if (text.includes('蓝')) return '#1982C1';
        if (text.includes('白')) return '#e5e7eb'; // 白色预警，使用浅灰色
        return '#9ca3af';
    };

    return (
        <div className="card" style={{ height: '100%', minHeight: '200px', display: 'flex', flexDirection: 'column', ...style }}>
            <div className="chart-card-header">
                <span style={{ fontSize: '20px' }}>🎨</span>
                <Typography variant="h6">气象预警级别</Typography>
            </div>
            
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', padding: '16px 0' }}>
                {/* CSS Conic Gradient Pie Chart */}
                <div style={{
                    width: '160px',
                    height: '160px',
                    borderRadius: '50%',
                    background: `conic-gradient(${weatherLevels.map(item => {
                        const start = currentAngle;
                        const percentage = (item.count / total) * 100;
                        currentAngle += percentage;
                        return `${getColor(item.level)} ${start}% ${currentAngle}%`;
                    }).join(', ')})`,
                    position: 'relative',
                    marginBottom: '32px'
                }}>
                    {/* 中空圆环效果 */}
                    <div style={{
                        position: 'absolute',
                        top: '50%',
                        left: '50%',
                        transform: 'translate(-50%, -50%)',
                        width: '60%',
                        height: '60%',
                        background: 'var(--md-sys-color-surface)',
                        // 强制叠加一层白色（在亮色模式下）以确保不透明，或者使用混合模式
                        // 这里简单粗暴地用 box-shadow 填补可能的透明缝隙，或者直接指定一个 fallback 颜色
                        backgroundColor: '#e5e7eb', // 先设为白色
                        backgroundImage: 'linear-gradient(var(--md-sys-color-surface), var(--md-sys-color-surface))', // 再叠加上主题色
                        borderRadius: '50%',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center'
                    }}>
                        <Typography variant="h5" sx={{ fontWeight: 800, lineHeight: 1 }}>{total}</Typography>
                        <Typography variant="caption" sx={{ opacity: 0.6, fontSize: '11px', mt: 0.5 }}>预警总数</Typography>
                    </div>
                </div>

                <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {weatherLevels.map((item, index) => (
                        <div key={index} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '13px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ fontWeight: 600, opacity: 0.9 }}>{item.level}</span>
                            </div>
                            <div style={{ display: 'flex', gap: '8px' }}>
                                <span style={{ fontWeight: 700 }}>{item.count}</span>
                                <span style={{ opacity: 0.5, minWidth: '45px', textAlign: 'right' }}>
                                    {((item.count / total) * 100).toFixed(2)}%
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
