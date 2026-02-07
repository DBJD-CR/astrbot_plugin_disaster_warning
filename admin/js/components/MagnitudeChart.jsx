const { Box, Typography } = MaterialUI;
const { useMemo } = React;

function MagnitudeChart() {
    const { state } = useAppContext();
    const { magnitudeDistribution } = state;

    const magnitudeOrder = [
        "< M3.0", "M3.0 - M3.9", "M4.0 - M4.9", "M5.0 - M5.9", "M6.0 - M6.9", "M7.0 - M7.9", ">= M8.0"
    ];

    const chartData = useMemo(() => {
        const data = magnitudeOrder.map(label => ({
            label,
            value: magnitudeDistribution[label] || 0
        }));

        const maxValue = Math.max(...data.map(d => d.value), 1);
        return data.map(d => ({
            ...d,
            percentage: (d.value / maxValue) * 100
        }));
    }, [magnitudeDistribution]);

    if (Object.keys(magnitudeDistribution).length === 0) {
        return (
            <div className="card" style={{ textAlign: 'center', padding: '60px' }}>
                <Typography variant="body2" sx={{ opacity: 0.5 }}>统计数据加载中...</Typography>
            </div>
        );
    }

    return (
        <div className="card">
            <div className="chart-card-header">
                <span style={{ fontSize: '20px' }}>📈</span>
                <Typography variant="h6">震级分布统计</Typography>
            </div>

            <div className="mag-stats-container">
                {chartData.map((item, index) => (
                    <div key={index} className="mag-row">
                        <div className="mag-label">{item.label}</div>
                        <div className="mag-bar-container">
                            <div 
                                className="mag-bar" 
                                style={{ width: `${item.percentage}%` }}
                            ></div>
                        </div>
                        <div className="mag-value">{item.value}</div>
                    </div>
                ))}
            </div>
        </div>
    );
}
