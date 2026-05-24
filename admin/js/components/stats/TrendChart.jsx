const { Box, Typography, CircularProgress, ToggleButton, ToggleButtonGroup } = MaterialUI;
const { useState, useEffect, useMemo } = React;

/**
 * 预警事件趋势变化图表组件 (TrendChart)
 * 渲染一条平滑顺畅的 SVG 预警次数波动曲线图，并覆盖半透明渐变面积阴影。
 * 核心设计亮点：
 * 1. 跨度切换：提供 24h (按小时) 和 7d (按天) 的波动数据拉取与平滑渲染。
 * 2. 贝塞尔曲线：对点位序列执行 Cubic Bezier 平滑三次插值算法生成二次曲线而非生硬折线。
 * 3. 悬浮浮层：监听 SVG 上的鼠标位移，计算最近的数据节点并渲染垂直虚线准星与悬浮信息胶囊。
 * 4. 骨架指示：加载过程呈现 Circular 骨架屏，防止加载导致的闪烁。
 *
 * @param {Object} props
 * @param {Object} [props.style] 外部样式
 * @param {string} [props.className=''] 额外类
 */
function TrendChart({ style, className = '' }) {
    const { getTrend } = window.DisasterStatusApi;
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    // 可选范围：24 (小时) 或 168 (7天)
    const [range, setRange] = useState(24);
    // 鼠标在图表上悬浮时的最近节点索引值
    const [hoveredIndex, setHoveredIndex] = useState(null);

    // 监听时间跨度状态，重载趋势数据
    useEffect(() => {
        fetchData();
    }, [range]);

    // 对获取的图表时序数据进行格式化整理
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

    /**
     * 发起趋势查询 API
     */
    const fetchData = async () => {
        setLoading(true);
        try {
            const trendItems = await getTrend(range);
            const normalizedItems = Array.isArray(trendItems?.data)
                ? trendItems.data
                : (Array.isArray(trendItems) ? trendItems : []);
            setData(normalizedItems);
        } catch (error) {
            console.error('获取趋势数据失败:', error);
        } finally {
            setLoading(false);
        }
    };

    /**
     * 时间跨度单选切换
     */
    const handleRangeChange = (event, newRange) => {
        if (newRange !== null) {
            setRange(newRange);
            setHoveredIndex(null); // 清除悬浮标示，防止错位
        }
    };

    // 算法核心：等比换算坐标并在 SVG 画布上直接拼接三次贝塞尔平滑路径 (Path C)
    const chartParams = useMemo(() => {
        if (!normalizedData || normalizedData.length === 0) return null;

        const width = 1000;
        const height = 220;
        // 预留页边距给 X/Y 坐标轴上的数值标签
        const padding = { top: 20, right: 30, bottom: 30, left: 40 };
        
        // 计算最大上限，预留 20% 的顶部空间防止顶点顶格，最低水位定为 5
        const dataMax = Math.max(...normalizedData.map(d => d.count), 0);
        const maxCount = Math.max(dataMax * 1.2, 5);

        const denominator = Math.max(normalizedData.length - 1, 1);
        const xScale = (width - padding.left - padding.right) / denominator;
        const yScale = (height - padding.top - padding.bottom) / maxCount;

        // 换算每一个点在 SVG 内的物理坐标
        const points = normalizedData.map((d, i) => ({
            x: padding.left + i * xScale,
            y: height - padding.bottom - (d.count * yScale)
        }));

        // 构造三次贝塞尔曲线控制路径 (C 算子)
        let pathData = `M ${points[0].x} ${points[0].y}`;
        for (let i = 0; i < points.length - 1; i++) {
            const p0 = points[i];
            const p1 = points[i + 1];
            const cp1x = p0.x + (p1.x - p0.x) / 2; // 控制点定在两点水平的中点上
            pathData += ` C ${cp1x} ${p0.y}, ${cp1x} ${p1.y}, ${p1.x} ${p1.y}`;
        }
        
        // 构造闭合面积遮罩图路径 (由曲线、末尾拉垂直底、底部水平滑到原点底、原点底拉直连原点闭合)
        const bottomY = height - padding.bottom;
        const areaPathData = `${pathData} L ${points[points.length - 1].x} ${bottomY} L ${padding.left} ${bottomY} Z`;

        // 构造 Y 轴五个层级等分虚线及标签位
        const yTicks = [];
        for (let i = 0; i <= 4; i++) {
            const val = (maxCount / 4) * i;
            if (val % 1 === 0 || val > 5) {
                yTicks.push({
                    value: Math.round(val),
                    y: height - padding.bottom - (val * yScale)
                });
            }
        }

        // 构造 X 轴的时间点显示定位，总计展示 6-8 个，过滤拥堵
        const xTicks = [];
        const tickStep = Math.max(Math.floor(normalizedData.length / 7), 1);

        for (let i = 0; i < normalizedData.length; i += tickStep) {
            const rawTime = normalizedData[i]?.time || '--';
            const timeStr = String(rawTime).split(' ')[1] || String(rawTime);
            xTicks.push({
                label: timeStr,
                x: padding.left + i * xScale,
                y: height - padding.bottom + 15
            });
        }

        return { 
            width, height, pathData, areaPathData, points, maxCount, xScale, yScale, padding, yTicks, xTicks 
        };
    }, [normalizedData]);

    /**
     * 鼠标滑动交互：根据鼠标 X 位移自动计算在 xScale 下对应的最近点索引
     */
    const handleMouseMove = (e) => {
        if (!chartParams || !normalizedData.length) return;
        
        const svg = e.currentTarget;
        const rect = svg.getBoundingClientRect();
        // 换算相对于 SVG 物理定义宽度的坐标
        const mouseX = ((e.clientX - rect.left) / rect.width) * chartParams.width;
        
        const index = Math.round((mouseX - chartParams.padding.left) / chartParams.xScale);
        if (index >= 0 && index < normalizedData.length) {
            setHoveredIndex(index);
        }
    };

    /**
     * 鼠标离图清除悬浮点
     */
    const handleMouseLeave = () => {
        setHoveredIndex(null);
    };

    return (
        <div className={`card trend-chart-card ${className}`} style={style}>
            {/* 页头及实时交互浮点状态胶囊 */}
            <div className="chart-card-header trend-chart-header">
                <div className="trend-chart-title">
                    <span className="stats-card-header-icon">📈</span>
                    <Typography variant="h6">预警趋势</Typography>
                </div>
                
                {/* 悬浮交互胶囊信息区，使用 visibility 以避免突然出现时拉伸挤压布局 */}
                <div className={`trend-chart-hover-slot ${hoveredIndex !== null && normalizedData[hoveredIndex] ? 'is-visible' : ''}`}>
                    {hoveredIndex !== null && normalizedData[hoveredIndex] && (
                        <div className="trend-chart-hover-pill">
                            <span>{normalizedData[hoveredIndex].time || '--'}</span>
                            <span className="trend-chart-hover-separator">|</span>
                            <span>{normalizedData[hoveredIndex].count || 0} 次</span>
                        </div>
                    )}
                </div>

                {/* 跨度控制切换按钮组 */}
                <ToggleButtonGroup
                    value={range}
                    exclusive
                    onChange={handleRangeChange}
                    size="small"
                    className="trend-chart-range-toggle"
                >
                    <ToggleButton value={24} className="trend-chart-range-toggle__option">24h</ToggleButton>
                    <ToggleButton value={168} className="trend-chart-range-toggle__option">7d</ToggleButton>
                </ToggleButtonGroup>
            </div>

            {/* SVG 画布主体 */}
            <div className="trend-chart-body">
                {loading ? (
                    <Box className="trend-chart-state trend-chart-state--loading">
                        <CircularProgress size={24} />
                    </Box>
                ) : chartParams ? (
                    <svg
                        viewBox={`0 0 ${chartParams.width} ${chartParams.height}`}
                        preserveAspectRatio="none"
                        className="trend-chart-svg"
                        onMouseMove={handleMouseMove}
                        onMouseLeave={handleMouseLeave}
                    >
                        {/* 渐变遮罩定义 */}
                        <defs>
                            <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="var(--md-sys-color-primary)" stopOpacity="0.3" />
                                <stop offset="100%" stopColor="var(--md-sys-color-primary)" stopOpacity="0" />
                            </linearGradient>
                        </defs>
                        
                        {/* Y 轴单位 */}
                        <text
                            x={chartParams.padding.left}
                            y={chartParams.padding.top - 8}
                            textAnchor="middle"
                            fill="var(--md-sys-color-on-surface-variant)"
                            className="trend-chart-axis-label"
                        >
                            预警数量
                        </text>

                        {/* Y 轴刻度及水平等分线 */}
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
                                    className="trend-chart-grid-line"
                                />
                                <text
                                    x={chartParams.padding.left - 5}
                                    y={tick.y}
                                    dy="0.32em"
                                    textAnchor="end"
                                    fill="var(--md-sys-color-on-surface-variant)"
                                    className="trend-chart-tick-label"
                                >
                                    {tick.value}
                                </text>
                            </g>
                        ))}
                        
                        {/* X 轴刻度文本 */}
                        {chartParams.xTicks.map((tick, i) => (
                            <g key={`x-${i}`}>
                                <text
                                    x={tick.x}
                                    y={tick.y}
                                    textAnchor="middle"
                                    fill="var(--md-sys-color-on-surface-variant)"
                                    className="trend-chart-tick-label"
                                >
                                    {tick.label}
                                </text>
                            </g>
                        ))}

                        {/* X 轴单位 */}
                        <text
                            x={chartParams.width - 15}
                            y={chartParams.height - chartParams.padding.bottom + 5}
                            textAnchor="end"
                            fill="var(--md-sys-color-on-surface-variant)"
                            className="trend-chart-axis-label"
                        >
                            时间
                        </text>

                        {/* 1. 平滑填充渐变面积 */}
                        <path
                            d={chartParams.areaPathData}
                            fill="url(#trendGradient)"
                            stroke="none"
                        />
                        
                        {/* 2. 贝塞尔主波动曲线 */}
                        <path
                            d={chartParams.pathData}
                            fill="none"
                            stroke="var(--md-sys-color-primary)"
                            strokeWidth="3"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            className="trend-chart-line"
                        />
                        
                        {/* 3. 实时交互十字虚线准星与数据点高亮圈（仅在悬浮状态渲染） */}
                        {hoveredIndex !== null && chartParams.points[hoveredIndex] && (
                            <g className="trend-chart-hover-layer">
                                {/* 垂直虚线准星 */}
                                <line
                                    x1={chartParams.points[hoveredIndex].x}
                                    y1={chartParams.padding.top}
                                    x2={chartParams.points[hoveredIndex].x}
                                    y2={chartParams.height - chartParams.padding.bottom}
                                    stroke="var(--md-sys-color-primary)"
                                    strokeWidth="1"
                                    strokeDasharray="4 4"
                                />
                                {/* 高亮数据点圈套 */}
                                <circle
                                    cx={chartParams.points[hoveredIndex].x}
                                    cy={chartParams.points[hoveredIndex].y}
                                    r="6"
                                    fill="var(--md-sys-color-surface)"
                                    stroke="var(--md-sys-color-primary)"
                                    strokeWidth="2"
                                />
                                <circle
                                    cx={chartParams.points[hoveredIndex].x}
                                    cy={chartParams.points[hoveredIndex].y}
                                    r="3"
                                    fill="var(--md-sys-color-primary)"
                                />
                            </g>
                        )}
                        
                        {/* 坐标轴 X 物理实线 */}
                        <line
                            x1={chartParams.padding.left} y1={chartParams.height - chartParams.padding.bottom}
                            x2={chartParams.width - chartParams.padding.right} y2={chartParams.height - chartParams.padding.bottom}
                            stroke="var(--md-sys-color-outline)"
                            strokeWidth="1"
                            className="trend-chart-axis-line"
                        />
                        
                        {/* 坐标轴 Y 物理实线 */}
                        <line
                            x1={chartParams.padding.left} y1={chartParams.padding.top}
                            x2={chartParams.padding.left} y2={chartParams.height - chartParams.padding.bottom}
                            stroke="var(--md-sys-color-outline)"
                            strokeWidth="1"
                            className="trend-chart-axis-line"
                        />
                    </svg>
                ) : (
                    <Box className="trend-chart-state trend-chart-state--empty">
                        <Typography variant="body2" className="trend-chart-empty-text">暂无趋势数据</Typography>
                    </Box>
                )}
            </div>
        </div>
    );
}
