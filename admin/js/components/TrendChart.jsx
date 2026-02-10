const { Box, Typography, CircularProgress, ToggleButton, ToggleButtonGroup } = MaterialUI;
const { useState, useEffect, useMemo } = React;

/**
 * 预警趋势图组件
 * 展示最近 24 小时或 7 天的预警数量变化
 */
function TrendChart({ style }) {
    const { getTrend } = useApi();
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [range, setRange] = useState(24); // 24 或 168 (7天)
    const [hoveredIndex, setHoveredIndex] = useState(null);

    useEffect(() => {
        fetchData();
    }, [range]);

    const fetchData = async () => {
        setLoading(true);
        try {
            const response = await getTrend(range);
            setData(response.data || []);
        } catch (error) {
            console.error('获取趋势数据失败:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleRangeChange = (event, newRange) => {
        if (newRange !== null) {
            setRange(newRange);
            setHoveredIndex(null);
        }
    };

    // SVG 绘图参数
    const chartParams = useMemo(() => {
        if (!data || data.length === 0) return null;

        const width = 1000;
        const height = 180;
        const padding = { top: 15, right: 5, bottom: 5, left: 5 };
        
        const maxCount = Math.max(...data.map(d => d.count), 5);
        const xScale = (width - padding.left - padding.right) / (data.length - 1);
        const yScale = (height - padding.top - padding.bottom) / maxCount;

        // 生成路径点
        const points = data.map((d, i) => ({
            x: padding.left + i * xScale,
            y: height - padding.bottom - (d.count * yScale)
        }));

        // 生成平滑曲线 (Spline) 的路径字符串
        let pathData = `M ${points[0].x} ${points[0].y}`;
        for (let i = 0; i < points.length - 1; i++) {
            const p0 = points[i];
            const p1 = points[i + 1];
            const cp1x = p0.x + (p1.x - p0.x) / 2;
            pathData += ` C ${cp1x} ${p0.y}, ${cp1x} ${p1.y}, ${p1.x} ${p1.y}`;
        }

        // 生成面积图闭合路径
        const areaPathData = `${pathData} L ${points[points.length - 1].x} ${height} L 0 ${height} Z`;

        return { width, height, pathData, areaPathData, points, maxCount, xScale, padding };
    }, [data]);

    const handleMouseMove = (e) => {
        if (!chartParams || !data.length) return;
        
        const svg = e.currentTarget;
        const rect = svg.getBoundingClientRect();
        const mouseX = ((e.clientX - rect.left) / rect.width) * chartParams.width;
        
        // 计算最近的点索引
        const index = Math.round((mouseX - chartParams.padding.left) / chartParams.xScale);
        if (index >= 0 && index < data.length) {
            setHoveredIndex(index);
        }
    };

    const handleMouseLeave = () => {
        setHoveredIndex(null);
    };

    return (
        <div className="card" style={{ ...style, position: 'relative', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div className="chart-card-header" style={{ marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '20px' }}>📈</span>
                    <Typography variant="h6">预警趋势</Typography>
                </div>
                {hoveredIndex !== null && data[hoveredIndex] && (
                    <div style={{ 
                        marginLeft: 'auto', 
                        marginRight: '12px',
                        background: 'var(--md-sys-color-primary-container)',
                        color: 'var(--md-sys-color-on-primary-container)',
                        padding: '2px 10px',
                        borderRadius: '20px',
                        fontSize: '12px',
                        fontWeight: 700,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        animation: 'fadeIn 0.2s'
                    }}>
                        <span>{data[hoveredIndex].time}</span>
                        <span style={{ opacity: 0.5 }}>|</span>
                        <span>{data[hoveredIndex].count} 次</span>
                    </div>
                )}
                <ToggleButtonGroup
                    value={range}
                    exclusive
                    onChange={handleRangeChange}
                    size="small"
                    sx={{ height: '28px' }}
                >
                    <ToggleButton value={24} sx={{ fontSize: '11px', px: 1.5 }}>24h</ToggleButton>
                    <ToggleButton value={168} sx={{ fontSize: '11px', px: 1.5 }}>7d</ToggleButton>
                </ToggleButtonGroup>
            </div>

            <div style={{ flex: 1, position: 'relative', minHeight: '120px', marginTop: '10px' }}>
                {loading ? (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                        <CircularProgress size={24} />
                    </Box>
                ) : chartParams ? (
                    <svg
                        viewBox={`0 0 ${chartParams.width} ${chartParams.height}`}
                        preserveAspectRatio="none"
                        style={{ width: '100%', height: '100%', display: 'block', cursor: 'crosshair' }}
                        onMouseMove={handleMouseMove}
                        onMouseLeave={handleMouseLeave}
                    >
                        <defs>
                            <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="var(--md-sys-color-primary)" stopOpacity="0.3" />
                                <stop offset="100%" stopColor="var(--md-sys-color-primary)" stopOpacity="0" />
                            </linearGradient>
                        </defs>
                        
                        {/* 面积填充 */}
                        <path
                            d={chartParams.areaPathData}
                            fill="url(#trendGradient)"
                            stroke="none"
                        />
                        
                        {/* 曲线线条 */}
                        <path
                            d={chartParams.pathData}
                            fill="none"
                            stroke="var(--md-sys-color-primary)"
                            strokeWidth="3"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            style={{ opacity: 0.8 }}
                        />
                        
                        {/* 悬浮交互层 */}
                        {hoveredIndex !== null && chartParams.points[hoveredIndex] && (
                            <g style={{ pointerEvents: 'none' }}>
                                {/* 垂直线 */}
                                <line
                                    x1={chartParams.points[hoveredIndex].x}
                                    y1="0"
                                    x2={chartParams.points[hoveredIndex].x}
                                    y2={chartParams.height}
                                    stroke="var(--md-sys-color-primary)"
                                    strokeWidth="1"
                                    strokeDasharray="4 4"
                                />
                                {/* 数据点外圈 */}
                                <circle
                                    cx={chartParams.points[hoveredIndex].x}
                                    cy={chartParams.points[hoveredIndex].y}
                                    r="6"
                                    fill="var(--md-sys-color-surface)"
                                    stroke="var(--md-sys-color-primary)"
                                    strokeWidth="2"
                                />
                                {/* 数据点中心 */}
                                <circle
                                    cx={chartParams.points[hoveredIndex].x}
                                    cy={chartParams.points[hoveredIndex].y}
                                    r="3"
                                    fill="var(--md-sys-color-primary)"
                                />
                            </g>
                        )}
                        
                        {/* 辅助参考线 */}
                        <line 
                            x1="0" y1={chartParams.height - 5} 
                            x2={chartParams.width} y2={chartParams.height - 5} 
                            stroke="var(--md-sys-color-outline-variant)" 
                            strokeWidth="1" 
                            strokeDasharray="4 4"
                            style={{ opacity: 0.3, pointerEvents: 'none' }}
                        />
                    </svg>
                ) : (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                        <Typography variant="body2" sx={{ opacity: 0.5 }}>暂无趋势数据</Typography>
                    </Box>
                )}
            </div>
            
            {!loading && data.length > 0 && (
                <div style={{ display: 'flex', justifyContent: 'space-between', mt: 1, opacity: 0.5 }}>
                    <Typography variant="caption">{data[0].time.split(' ')[1] || data[0].time}</Typography>
                    <Typography variant="caption">{data[data.length - 1].time.split(' ')[1] || data[data.length - 1].time}</Typography>
                </div>
            )}
        </div>
    );
}
