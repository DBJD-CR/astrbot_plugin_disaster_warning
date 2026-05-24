const { Box, Typography, CircularProgress, Select, MenuItem, FormControl } = MaterialUI;
const { useState, useEffect, useMemo, useRef, useLayoutEffect } = React;

/**
 * 历史活动日历热力图组件 (CalendarHeatmap)
 * 仿照 GitHub Contribution Graph 风格开发。
 * 横向展示整年里每一天系统捕获并处理的自然灾害预警/速报次数的分布图。
 * 核心逻辑与特色：
 * 1. 年份过滤：支持选择 2025 年至今的历史年份数据，并使用 Material-UI Select 切换。
 * 2. 实时通信：接收 WebSocket 实时广播，收到同年度的新事件时触发 2 秒延迟防抖重载。
 * 3. 自动滑行：在数据首载或切换年份后，图表容器自动横向滚动到最右侧最新日期处。
 * 4. 动态阈值：热力图格子的紫色深浅根据当前所选年份单日最大计数值进行“四分位”自适应生成。
 * 5. 悬浮动效：鼠标 Hover 热力图单元格时展现缩放与边框细节，并伴随原生 HTML tooltip。
 *
 * @param {Object} props
 * @param {Object} [props.style] 外部样式
 * @param {string} [props.className=''] 外部 CSS 类
 */
function CalendarHeatmap({ style, className = '' }) {
    // 调取宿主进程或控制台提供的热力图查询 API
    const { getHeatmap } = window.DisasterStatusApi;
    // 从上下文获取全局状态，监听 WebSocket 实时变化
    const { state } = useAppContext(); 
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    
    // 年份维护：默认选中当前年
    const currentYear = new Date().getFullYear();
    const [selectedYear, setSelectedYear] = useState(currentYear);
    const scrollContainerRef = useRef(null);
    const lastEvent = state.lastEvent; // 实时推送监听
    
    // 生成从 2025 年起至当前年的年份倒序数组
    const startYear = 2025;
    const years = useMemo(() => {
        const arr = [];
        for (let y = startYear; y <= currentYear; y++) {
            arr.push(y);
        }
        return arr.reverse(); // 最新年份排前
    }, [currentYear]);

    // 初始加载及年份变更时触发查询
    useEffect(() => {
        fetchData(selectedYear);
    }, [selectedYear]);

    // 监听 WebSocket 的实时推送，若事件年份符合当前年份则防抖重载
    useEffect(() => {
        if (!lastEvent) return;
        
        const eventTime = new Date(lastEvent.time || lastEvent.event_time || Date.now());
        if (eventTime.getFullYear() === selectedYear) {
            // 设置 2000ms 防抖，防范短时间地震多报更新连续触发刷新
            const timer = setTimeout(() => {
                fetchData(selectedYear, false); // 静默重载，关闭大屏骨架进度
            }, 2000);
            return () => clearTimeout(timer);
        }
    }, [lastEvent, selectedYear]);

    /**
     * 发起 API 请求，获取指定年份的活跃热力数据
     */
    const fetchData = async (year, showLoading = true) => {
        if (showLoading) setLoading(true);
        try {
            const heatmapItems = await getHeatmap(0, year);
            const normalizedItems = Array.isArray(heatmapItems?.data)
                ? heatmapItems.data
                : (Array.isArray(heatmapItems) ? heatmapItems : []);
            setData(normalizedItems);
        } catch (error) {
            console.error('获取热力图数据失败:', error);
        } finally {
            if (showLoading) setLoading(false);
        }
    };

    // 数据装载或年份切换后，同步将滚动条推送到最右端最新日期上
    useLayoutEffect(() => {
        if (scrollContainerRef.current) {
            scrollContainerRef.current.scrollLeft = scrollContainerRef.current.scrollWidth;
        }
    }, [data, loading, selectedYear]);

    // 算法核心：构建整年份 53 周（Sun - Sat）的格子网格，以及对应的月份左位移标签
    const { weeks, monthLabels } = useMemo(() => {
        // 将活跃数据数组以 "YYYY-MM-DD" => count 进行 Map 快速映射
        const dataMap = new Map();
        if (Array.isArray(data) && data.length > 0) {
            data.forEach(d => dataMap.set(d.date, Number.isFinite(Number(d?.count)) ? Number(d.count) : 0));
        }

        const weeksArr = [];
        const monthLabelsArr = [];
        const months = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];

        // 确定该年份的边界
        const yearStart = new Date(selectedYear, 0, 1);
        let yearEnd = new Date(selectedYear, 11, 31);

        // 如果是今年，限制右边界为今天，防止渲染未来大片无效空白格子
        const now = new Date();
        if (selectedYear === now.getFullYear()) {
            yearEnd = now;
        }

        // 定位起点：从 1月1日 所在的周日开始回溯（获取 1月1日前最近的一个周日）
        let currentDate = new Date(yearStart);
        const dayOfWeek = currentDate.getDay(); // 0 表示周日，6 表示周六
        currentDate.setDate(currentDate.getDate() - dayOfWeek);

        let currentWeek = [];
        let weekIndex = 0;
        
        while (true) {
            // 当循环日期已越过年末 且 当前存储的周数组已被排空清算，退出循环
            if (currentDate > yearEnd && currentWeek.length === 0) break;

            const year = currentDate.getFullYear();
            const month = String(currentDate.getMonth() + 1).padStart(2, '0');
            const day = String(currentDate.getDate()).padStart(2, '0');
            const dateStr = `${year}-${month}-${day}`;
            
            // 剔除定位周日时引入的前一年末无效格子
            const isWithinYear = currentDate.getFullYear() === selectedYear;
            
            const count = (isWithinYear && dataMap.has(dateStr)) ? dataMap.get(dateStr) : 0;
            
            // 月份标签智能推导：当检测到某月 1号 在这一周内出现，则标记该周列为对应的月份标签
            if (currentWeek.length === 0) {
                let labelMonth = -1;
                
                // 第一周强制标记为 1月
                if (weekIndex === 0) {
                    labelMonth = 0;
                } else {
                    const checkDate = new Date(currentDate);
                    for (let i = 0; i < 7; i++) {
                        if (checkDate.getDate() === 1 && checkDate.getFullYear() === selectedYear) {
                            labelMonth = checkDate.getMonth();
                            break;
                        }
                        checkDate.setDate(checkDate.getDate() + 1);
                    }
                }

                if (labelMonth !== -1) {
                    const exists = monthLabelsArr.some(m => m.month === labelMonth);
                    if (!exists) {
                        monthLabelsArr.push({
                            label: months[labelMonth],
                            index: weekIndex,
                            month: labelMonth
                        });
                    }
                }
            }

            // 推入当前周的格子描述
            currentWeek.push({
                date: dateStr,
                count: count,
                isValid: isWithinYear,
                obj: new Date(currentDate)
            });

            // 步进至下一天
            currentDate.setDate(currentDate.getDate() + 1);

            // 凑满 7 天，打包为一周推入周序列
            if (currentWeek.length === 7) {
                weeksArr.push(currentWeek);
                currentWeek = [];
                weekIndex++;
            }
        }
        
        return { weeks: weeksArr, monthLabels: monthLabelsArr };
    }, [data, selectedYear]);

    // 算法核心：根据所选年份单日预警频次的最高值，动态划定四分位颜色区间
    const thresholds = useMemo(() => {
        if (!Array.isArray(data) || data.length === 0) return [1, 2, 3];
        
        const maxCount = Math.max(...data.map(d => {
            const count = Number(d?.count);
            return Number.isFinite(count) ? count : 0;
        }), 0);
        
        // 若最大频次极低，采用硬编码 [1, 2, 3] 步长
        if (maxCount < 4) return [1, 2, 3];
        
        // 四分位分界线计算
        const t1 = Math.max(1, Math.ceil(maxCount * 0.25));
        const t2 = Math.max(t1 + 1, Math.ceil(maxCount * 0.5));
        const t3 = Math.max(t2 + 1, Math.ceil(maxCount * 0.75));
        
        return [t1, t2, t3];
    }, [data]);

    /**
     * 映射对应计数的渲染颜色底色，主题为优雅的紫色调
     */
    const getColor = (count) => {
        if (count === 0) return 'var(--md-sys-color-surface-variant)';
        if (count <= thresholds[0]) return 'rgba(147, 112, 219, 0.3)'; // 浅紫 (Level 1)
        if (count <= thresholds[1]) return 'rgba(147, 112, 219, 0.5)'; // 中紫 (Level 2)
        if (count <= thresholds[2]) return 'rgba(147, 112, 219, 0.7)'; // 深紫 (Level 3)
        return 'rgba(147, 112, 219, 1)'; // 纯紫高亮 (Level 4)
    };

    // 格子物理像素尺寸及间距
    const cellSize = 11;
    const cellGap = 3;
    const cellStep = cellSize + cellGap;

    return (
        <div className={`card calendar-heatmap-card ${className}`} style={style}>
            {/* 卡片头部：包含标题、年份下拉与图例 */}
            <div className="chart-card-header calendar-heatmap-header">
                <Box className="calendar-heatmap-title-group">
                    <span className="stats-card-header-icon">🗓️</span>
                    <Typography variant="h6">历史活动热力图</Typography>
                </Box>
                
                <div className="calendar-heatmap-header-spacer"></div>

                {/* 年份切换选择下拉框 */}
                <FormControl variant="standard" className="calendar-heatmap-year-control" size="small">
                    <Select
                        value={selectedYear}
                        onChange={(e) => setSelectedYear(e.target.value)}
                        disableUnderline
                        className="calendar-heatmap-year-select"
                    >
                        {years.map(year => (
                            <MenuItem key={year} value={year}>{year}年</MenuItem>
                        ))}
                    </Select>
                </FormControl>

                {/* 渐变级别图例说明 */}
                <div className="calendar-heatmap-legend">
                    <Typography variant="caption" className="calendar-heatmap-legend-label">Less</Typography>
                    <div className="calendar-heatmap-legend-cells">
                        <div className="calendar-heatmap-legend-cell" style={{ background: getColor(0) }} title="0"></div>
                        <div className="calendar-heatmap-legend-cell" style={{ background: getColor(thresholds[0]) }} title={`≤ ${thresholds[0]}`}></div>
                        <div className="calendar-heatmap-legend-cell" style={{ background: getColor(thresholds[1]) }} title={`≤ ${thresholds[1]}`}></div>
                        <div className="calendar-heatmap-legend-cell" style={{ background: getColor(thresholds[2]) }} title={`≤ ${thresholds[2]}`}></div>
                        <div className="calendar-heatmap-legend-cell" style={{ background: getColor(thresholds[2] + 1) }} title={`> ${thresholds[2]}`}></div>
                    </div>
                    <Typography variant="caption" className="calendar-heatmap-legend-label">More</Typography>
                </div>
            </div>

            {/* 可滚动的 SVG 热力图画布主体 */}
            <div ref={scrollContainerRef} className="calendar-heatmap-scroll">
                {loading ? (
                    <Box className="calendar-heatmap-state calendar-heatmap-state--loading">
                        <CircularProgress size={24} />
                    </Box>
                ) : (
                    <div className="calendar-heatmap-canvas">
                        {/* 1. 顶部月份标签栏，根据 weekIndex 计算左偏移像素 */}
                        <div className="calendar-heatmap-month-row">
                            {monthLabels.map((m, idx) => (
                                <Typography
                                    key={idx}
                                    variant="caption"
                                    className="calendar-heatmap-month-label"
                                    style={{ '--calendar-heatmap-label-left': `${m.index * cellStep}px` }}
                                >
                                    {m.label}
                                </Typography>
                            ))}
                        </div>

                        {/* 2. 贡献网格格子阵列 (由 53 列周容器排列，每列包含 7 天) */}
                        <div className="calendar-heatmap-grid" style={{ '--heatmap-cell-gap': `${cellGap}px` }}>
                            {weeks.map((week, wIndex) => (
                                <div key={wIndex} className="calendar-heatmap-week" style={{ '--heatmap-cell-gap': `${cellGap}px` }}>
                                    {week.map((day, dIndex) => (
                                        <div
                                            key={dIndex}
                                            title={day.isValid ? `${day.date}: ${day.count} 次预警` : ''}
                                            style={{
                                                width: `${cellSize}px`,
                                                height: `${cellSize}px`,
                                                borderRadius: '2px',
                                                backgroundColor: day.isValid ? getColor(day.count) : 'transparent',
                                                opacity: day.isValid ? 1 : 0,
                                                transition: 'all 0.1s',
                                                cursor: (day.isValid && day.count > 0) ? 'pointer' : 'default',
                                                border: (day.isValid && day.count > 0) ? '1px solid rgba(255,255,255,0.1)' : 'none'
                                            }}
                                            onMouseEnter={(e) => {
                                                if (day.isValid) {
                                                    e.target.style.transform = 'scale(1.2)';
                                                    e.target.style.zIndex = 10;
                                                }
                                            }}
                                            onMouseLeave={(e) => {
                                                if (day.isValid) {
                                                    e.target.style.transform = 'scale(1)';
                                                    e.target.style.zIndex = 'auto';
                                                }
                                            }}
                                        ></div>
                                    ))}
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
            
            <Typography variant="caption" className="calendar-heatmap-caption">
                {selectedYear} 年的预警活跃程度
            </Typography>
        </div>
    );
}
