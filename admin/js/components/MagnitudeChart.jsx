const { Box, Typography } = MaterialUI;
const { useMemo } = React;

/**
 * 震级分布图表组件
 * 使用条形图展示不同震级范围的地震数量统计
 *
 * @param {Object} props
 * @param {Object} props.style - 自定义样式对象
 */
function MagnitudeChart({ style }) {
    const { state } = useAppContext();
    const { magnitudeDistribution } = state;

    const magnitudeOrder = [
        "< M3.0", "M3.0 - M3.9", "M4.0 - M4.9", "M5.0 - M5.9", "M6.0 - M6.9", "M7.0 - M7.9", ">= M8.0"
    ];

    // 计算图表数据
    // 将震级分布数据转换为包含百分比的数组，用于渲染条形图长度
    const chartData = useMemo(() => {
        // 计算总数
        const total = magnitudeOrder.reduce((acc, label) => acc + (magnitudeDistribution[label] || 0), 0);
        
        const data = magnitudeOrder.map(label => ({
            label,
            value: magnitudeDistribution[label] || 0
        }));

        // 计算最大值，用于计算百分比 (条形图长度)
        const maxValue = Math.max(...data.map(d => d.value), 1);
        
        return data.map(d => ({
            ...d,
            percentage: (d.value / maxValue) * 100, // 相对最长条的百分比
            ratio: total > 0 ? (d.value / total) * 100 : 0 // 占总数的百分比
        }));
    }, [magnitudeDistribution]);

    if (Object.keys(magnitudeDistribution).length === 0) {
        return (
            <div className="card" style={{ textAlign: 'center', padding: '60px', ...style }}>
                <Typography variant="body2" sx={{ opacity: 0.5 }}>统计数据加载中...</Typography>
            </div>
        );
    }

    return (
        <div className="card" style={style}>
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
                        {/* 增加 minWidth，防止百分比和数值拥挤 */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '100px', justifyContent: 'flex-end' }}>
                            <div className="mag-value" style={{ textAlign: 'right' }}>{item.value}</div>
                            <span style={{ fontSize: '12px', opacity: 0.6, fontWeight: 500, minWidth: '55px', textAlign: 'right' }}>
                                ({item.ratio > 0 ? `${item.ratio.toFixed(2)}%` : '0.00%'})
                            </span>
                        </div>
                    </div>
                ))}
            </div>
            
            <div style={{ marginTop: 'auto', paddingTop: '36px' }}>
                <div style={{
                    background: 'var(--md-sys-color-surface-variant)',
                    borderRadius: '12px',
                    padding: '16px',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px'
                }}>
                    <span style={{ fontSize: '18px', marginTop: '-2px' }}>ℹ️</span>
                    <Typography variant="body2" sx={{ opacity: 0.7, lineHeight: 1.6, textAlign: 'justify', fontSize: '14px' }}>
                        地震震级分布与最大地震的统计可能会不一致，这是由于对数据源的筛选逻辑不一样导致的，前者比较宽松，后者比较严格。
                    </Typography>
                </div>
            </div>
        </div>
    );
}
