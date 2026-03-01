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

    const normalizedData = useMemo(() => {
        const source = Array.isArray(data) ? data : [];
        return source.map(item => {
            const count = Number(item?.count);
            return {
                ...item,
                time: item?.time ? String(item.time) : '--',
                count: Number.isFinite(count) ? count : 0
            };
        });
    }, [data]);

    const fetchData = async () => {
        setLoading(true);
        try {
            const response = await getTrend(range);
            setData(Array.isArray(response.data) ? response.data : []);
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
        if (!normalizedData || normalizedData.length === 0) return null;

        const width = 1000;
        const height = 220; // 稍微增加高度以容纳X轴标签
        // 增加边距，为坐标轴留出空间
        const padding = { top: 20, right: 30, bottom: 30, left: 40 };
        
        // 计算最大值，保证至少为 5，且略微留白
        const dataMax = Math.max(...normalizedData.map(d => d.count), 0);
        const maxCount = Math.max(dataMax * 1.2, 5); // 留出 20% 顶部空间

        const denominator = Math.max(normalizedData.length - 1, 1);
        const xScale = (width - padding.left - padding.right) / denominator;
        const yScale = (height - padding.top - padding.bottom) / maxCount;

        // 生成路径点
        const points = normalizedData.map((d, i) => ({
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
        
        // 生成面积图闭合路径，注意底部边界需要减去 padding.bottom
        const bottomY = height - padding.bottom;
        const areaPathData = `${pathData} L ${points[points.length - 1].x} ${bottomY} L ${padding.left} ${bottomY} Z`;

        // 生成Y轴刻度 (5个刻度)
        const yTicks = [];
        for (let i = 0; i <= 4; i++) {
            const val = (maxCount / 4) * i;
            // 只有整数刻度或者数值较大时才有意义
            if (val % 1 === 0 || val > 5) {
                yTicks.push({
                    value: Math.round(val),
                    y: height - padding.bottom - (val * yScale)
                });
            }
        }

        // 生成X轴刻度 (每隔几个点显示一个时间)
        const xTicks = [];
        // 根据数据量动态决定步长，保证显示约6-8个标签
        const tickStep = Math.max(Math.floor(normalizedData.length / 7), 1);

        for (let i = 0; i < normalizedData.length; i += tickStep) {
            // 简单处理时间显示，只取 HH:mm
            const rawTime = normalizedData[i]?.time || '--';
            const timeStr = String(rawTime).split(' ')[1] || String(rawTime);
            xTicks.push({
                label: timeStr,
                x: padding.left + i * xScale,
                y: height - padding.bottom + 15
            });
        }

        return { width, height, pathData, areaPathData, points, maxCount, xScale, yScale, padding, yTicks, xTicks };
    }, [normalizedData]);

    const handleMouseMove = (e) => {
        if (!chartParams || !normalizedData.length) return;
        
        const svg = e.currentTarget;
        const rect = svg.getBoundingClientRect();
        const mouseX = ((e.clientX - rect.left) / rect.width) * chartParams.width;
        
        // 计算最近的点索引
        const index = Math.round((mouseX - chartParams.padding.left) / chartParams.xScale);
        if (index >= 0 && index < normalizedData.length) {
            setHoveredIndex(index);
        }
    };

    const handleMouseLeave = () => {
        setHoveredIndex(null);
    };

    return (
        <div className="card" style={{ ...style, position: 'relative', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div className="chart-card-header" style={{ marginBottom: '8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '20px' }}>📈</span>
                    <Typography variant="h6">预警趋势</Typography>
                </div>
                
                {/* 
                   中间固定区域显示悬浮信息 
                   使用 visibility 控制显示隐藏，而不是条件渲染，防止布局跳动
                */}
                <div style={{ 
                    flex: 1, 
                    display: 'flex', 
                    justifyContent: 'center', 
                    visibility: hoveredIndex !== null && normalizedData[hoveredIndex] ? 'visible' : 'hidden',
                    opacity: hoveredIndex !== null && normalizedData[hoveredIndex] ? 1 : 0,
                    transition: 'opacity 0.2s',
                    height: '24px' // 固定高度占位
                }}>
                    {hoveredIndex !== null && normalizedData[hoveredIndex] && (
                        <div style={{ 
                            background: 'var(--md-sys-color-primary-container)',
                            color: 'var(--md-sys-color-on-primary-container)',
                            padding: '2px 12px',
                            borderRadius: '20px',
                            fontSize: '13px',
                            fontWeight: 700,
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                        }}>
                            <span>{normalizedData[hoveredIndex].time || '--'}</span>
                            <span style={{ opacity: 0.5 }}>|</span>
                            <span>{normalizedData[hoveredIndex].count || 0} 次</span>
                        </div>
                    )}
                </div>

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
                        
                        {/* 坐标轴单位 - Y轴 */}
                        <text
                            x={chartParams.padding.left}
                            y={chartParams.padding.top - 8}
                            textAnchor="middle"
                            fill="var(--md-sys-color-on-surface-variant)"
                            style={{ fontSize: '10px', opacity: 0.5, fontWeight: 600 }}
                        >
                            预警数量
                        </text>

                        {/* 坐标轴辅助线 - Y轴 */}
                        {chartParams.yTicks.map((tick, i) => (
                            <g key={`y-${i}`}>
                                <line
                                    x1={chartParams.padding.left}
                                    y1={tick.y}
                                    x2={chartParams.width - chartParams.padding.right}
                                    y2={tick.y}
                                    stroke="var(--md-sys-color-outline-variant)"
                                    strokeWidth="1"
                                    strokeDasharray="3 3"
                                    style={{ opacity: 0.2 }}
                                />
                                <text
                                    x={chartParams.padding.left - 5}
                                    y={tick.y}
                                    dy="0.32em"
                                    textAnchor="end"
                                    fill="var(--md-sys-color-on-surface-variant)"
                                    style={{ fontSize: '10px', opacity: 0.7 }}
                                >
                                    {tick.value}
                                </text>
                            </g>
                        ))}
                        
                        {/* 坐标轴辅助线 - X轴 */}
                        {chartParams.xTicks.map((tick, i) => (
                            <g key={`x-${i}`}>
                                <text
                                    x={tick.x}
                                    y={tick.y}
                                    textAnchor="middle"
                                    fill="var(--md-sys-color-on-surface-variant)"
                                    style={{ fontSize: '10px', opacity: 0.7 }}
                                >
                                    {tick.label}
                                </text>
                            </g>
                        ))}

                        {/* 坐标轴单位 - X轴 */}
                        <text
                            x={chartParams.width - 15}
                            y={chartParams.height - chartParams.padding.bottom + 5}
                            textAnchor="end"
                            fill="var(--md-sys-color-on-surface-variant)"
                            style={{ fontSize: '10px', opacity: 0.5, fontWeight: 600 }}
                        >
                            时间
                        </text>

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
                                    y1={chartParams.padding.top}
                                    x2={chartParams.points[hoveredIndex].x}
                                    y2={chartParams.height - chartParams.padding.bottom}
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
                        
                        {/* 坐标轴底线 */}
                        <line 
                            x1={chartParams.padding.left} y1={chartParams.height - chartParams.padding.bottom} 
                            x2={chartParams.width - chartParams.padding.right} y2={chartParams.height - chartParams.padding.bottom} 
                            stroke="var(--md-sys-color-outline)" 
                            strokeWidth="1" 
                            style={{ opacity: 0.5 }}
                        />
                        
                         {/* 坐标轴左线 */}
                         <line 
                            x1={chartParams.padding.left} y1={chartParams.padding.top} 
                            x2={chartParams.padding.left} y2={chartParams.height - chartParams.padding.bottom} 
                            stroke="var(--md-sys-color-outline)" 
                            strokeWidth="1" 
                            style={{ opacity: 0.5 }}
                        />
                    </svg>
                ) : (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                        <Typography variant="body2" sx={{ opacity: 0.5 }}>暂无趋势数据</Typography>
                    </Box>
                )}
            </div>
        </div>
    );
}
