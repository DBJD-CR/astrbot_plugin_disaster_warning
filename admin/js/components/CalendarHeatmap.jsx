const { Box, Typography, CircularProgress, Select, MenuItem, FormControl } = MaterialUI;
const { useState, useEffect, useMemo, useRef, useLayoutEffect } = React;

/**
 * 日历热力图组件 (GitHub Style)
 * 展示一年内每日预警数量的分布
 */
function CalendarHeatmap({ style }) {
    const { getHeatmap } = useApi();
    const { state } = useAppContext(); // 从 Context 获取状态
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    
    // 年份选择
    const currentYear = new Date().getFullYear();
    const [selectedYear, setSelectedYear] = useState(currentYear);
    const scrollContainerRef = useRef(null);
    const events = state.events; // 直接从 Context 获取 events，不需要单独调用 useWebSocket
    
    // 生成可选年份列表 (从2025开始)
    const startYear = 2025;
    const years = useMemo(() => {
        const arr = [];
        for (let y = startYear; y <= currentYear; y++) {
            arr.push(y);
        }
        return arr.reverse(); // 最近的年份在前
    }, [currentYear]);

    // 初始加载
    useEffect(() => {
        fetchData(selectedYear);
    }, [selectedYear]);

    // 监听 WebSocket 实时更新
    useEffect(() => {
        if (!events || !events.lastEvent) return; // 修复：增加对 events 的判空
        
        // 只有当收到新事件且事件时间属于当前选中年份时，才重新获取数据
        // 优化：实际上可以只更新本地状态，但为了数据一致性，重新获取也是可接受的，因为热力图数据量不大
        const eventTime = new Date(events.lastEvent.time || Date.now());
        if (eventTime.getFullYear() === selectedYear) {
            // 防抖，避免短时间频繁请求
            const timer = setTimeout(() => {
                fetchData(selectedYear, false); // false 表示不显示全屏 loading
            }, 2000);
            return () => clearTimeout(timer);
        }
    }, [events, selectedYear]); // 修复：依赖项包含 events 而不是 events.lastEvent (避免深度依赖问题)

    const fetchData = async (year, showLoading = true) => {
        if (showLoading) setLoading(true);
        try {
            const response = await getHeatmap(0, year);
            setData(response.data || []);
        } catch (error) {
            console.error('获取热力图数据失败:', error);
        } finally {
            if (showLoading) setLoading(false);
        }
    };

    // 数据变更或加载完成后，滚动到最右侧
    useLayoutEffect(() => {
        if (scrollContainerRef.current) {
            scrollContainerRef.current.scrollLeft = scrollContainerRef.current.scrollWidth;
        }
    }, [data, loading, selectedYear]);

    // 构建完整年份的周数据和月标签
    const { weeks, monthLabels } = useMemo(() => {
        // 数据映射 Map
        const dataMap = new Map();
        if (data && data.length > 0) {
            data.forEach(d => dataMap.set(d.date, d.count));
        }

        const weeksArr = [];
        const monthLabelsArr = [];
        const months = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];

        // 确定年份起止
        const yearStart = new Date(selectedYear, 0, 1);
        let yearEnd = new Date(selectedYear, 11, 31);

        // 如果是当前年份，只显示到今天，避免右侧出现大量空白
        const now = new Date();
        if (selectedYear === now.getFullYear()) {
            yearEnd = now;
        }

        // 从当年的 1月1日 所在的周日开始 (或者 1月1日 之前的周日)
        // GitHub 风格：列是周 (Sun - Sat)
        let currentDate = new Date(yearStart);
        const dayOfWeek = currentDate.getDay(); // 0 is Sunday
        currentDate.setDate(currentDate.getDate() - dayOfWeek);

        let currentWeek = [];
        let weekIndex = 0;
        
        // 循环直到超过该年最后一天
        while (true) {
            // 如果当前周的开始日期已经超过了年末，且 currentWeek 为空，则结束
            if (currentDate > yearEnd && currentWeek.length === 0) break;

            const dateStr = currentDate.toISOString().split('T')[0]; // UTC Date String
            
            // 判断是否是该年内的日期
            // 注意：因为 currentDate 是本地时间对象（但在构建时我们假设它是 UTC 0点，或者本地0点）
            // 简单起见，我们比较 getFullYear
            const isWithinYear = currentDate.getFullYear() === selectedYear;
            
            // 获取数据
            const count = (isWithinYear && dataMap.has(dateStr)) ? dataMap.get(dateStr) : 0;
            
            // 检测是否需要添加月份标签
            // 规则：如果某个月的 1 号出现在本周内，则在该列上方标记该月
            // 或者是第一周，标记 1月
            if (currentWeek.length === 0) {
                // 检查本周 (currentDate ~ currentDate + 6) 是否包含某月 1 号
                let labelMonth = -1;
                
                // 第一周特殊处理
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
                    // 避免重复标记（通常不会，但为了保险）
                    const exists = monthLabelsArr.some(m => m.month === labelMonth);
                    if (!exists) {
                        monthLabelsArr.push({
                            label: months[labelMonth],
                            index: weekIndex
                        });
                    }
                }
            }

            currentWeek.push({
                date: dateStr,
                count: count,
                isValid: isWithinYear,
                obj: new Date(currentDate) // 复制日期对象
            });

            // 下一天
            currentDate.setDate(currentDate.getDate() + 1);

            if (currentWeek.length === 7) {
                weeksArr.push(currentWeek);
                currentWeek = [];
                weekIndex++;
            }
        }
        
        return { weeks: weeksArr, monthLabels: monthLabelsArr };
    }, [data, selectedYear]);

    // 计算热力图颜色阈值 (基于最大值动态四分位)
    const thresholds = useMemo(() => {
        if (!data || data.length === 0) return [1, 2, 3];
        
        // 找出最大值
        const maxCount = Math.max(...data.map(d => d.count), 0);
        
        // 如果数据很少(max < 4)，直接使用默认步长1
        if (maxCount < 4) return [1, 2, 3];
        
        // 动态计算三个分界点，将非零数据区间分为4段
        // Level 1: [1, t1]
        // Level 2: (t1, t2]
        // Level 3: (t2, t3]
        // Level 4: (t3, max]
        const t1 = Math.max(1, Math.ceil(maxCount * 0.25));
        const t2 = Math.max(t1 + 1, Math.ceil(maxCount * 0.5));
        const t3 = Math.max(t2 + 1, Math.ceil(maxCount * 0.75));
        
        return [t1, t2, t3];
    }, [data]);

    const getColor = (count) => {
        if (count === 0) return 'var(--md-sys-color-surface-variant)';
        // 使用 <= 逻辑，确保边界值包含在下级
        if (count <= thresholds[0]) return 'rgba(147, 112, 219, 0.3)'; // 浅紫 (Level 1)
        if (count <= thresholds[1]) return 'rgba(147, 112, 219, 0.5)'; // 中紫 (Level 2)
        if (count <= thresholds[2]) return 'rgba(147, 112, 219, 0.7)'; // 深紫 (Level 3)
        return 'rgba(147, 112, 219, 1)'; // 最深紫 (Level 4)
    };

    // 单元格大小配置
    const cellSize = 11;
    const cellGap = 3;
    const cellStep = cellSize + cellGap;

    return (
        <div className="card" style={{ ...style, display: 'flex', flexDirection: 'column' }}>
            <div className="chart-card-header" style={{ marginBottom: '8px' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <span style={{ fontSize: '20px' }}>🗓️</span>
                    <Typography variant="h6">历史活动热力图</Typography>
                </Box>
                
                <div style={{ flex: 1 }}></div>

                {/* 年份选择器 */}
                <FormControl variant="standard" sx={{ m: 0, minWidth: 80, mr: 2 }} size="small">
                    <Select
                        value={selectedYear}
                        onChange={(e) => setSelectedYear(e.target.value)}
                        disableUnderline
                        sx={{
                            fontSize: '0.9rem',
                            fontWeight: 600,
                            color: 'primary.main',
                            '& .MuiSelect-select': { py: 0.5 }
                        }}
                    >
                        {years.map(year => (
                            <MenuItem key={year} value={year}>{year}年</MenuItem>
                        ))}
                    </Select>
                </FormControl>

                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Typography variant="caption" sx={{ opacity: 0.5 }}>Less</Typography>
                    <div style={{ display: 'flex', gap: '2px' }}>
                        {/* Level 0 (0) */}
                        <div style={{ width: '10px', height: '10px', borderRadius: '2px', background: getColor(0) }} title="0"></div>
                        
                        {/* Level 1 (<= t1) */}
                        <div style={{ width: '10px', height: '10px', borderRadius: '2px', background: getColor(thresholds[0]) }} title={`≤ ${thresholds[0]}`}></div>
                        
                        {/* Level 2 (<= t2) */}
                        <div style={{ width: '10px', height: '10px', borderRadius: '2px', background: getColor(thresholds[1]) }} title={`≤ ${thresholds[1]}`}></div>
                        
                        {/* Level 3 (<= t3) */}
                        <div style={{ width: '10px', height: '10px', borderRadius: '2px', background: getColor(thresholds[2]) }} title={`≤ ${thresholds[2]}`}></div>
                        
                        {/* Level 4 (> t3) */}
                        <div style={{ width: '10px', height: '10px', borderRadius: '2px', background: getColor(thresholds[2] + 1) }} title={`> ${thresholds[2]}`}></div>
                    </div>
                    <Typography variant="caption" sx={{ opacity: 0.5 }}>More</Typography>
                </div>
            </div>

            {/* 可滚动区域 */}
            <div
                ref={scrollContainerRef}
                style={{
                    flex: 1,
                    overflowX: 'auto',
                    padding: '8px 0',
                    position: 'relative',
                    scrollbarWidth: 'thin', // Firefox
                }}
            >
                {loading ? (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', width: '100%', height: '140px' }}>
                        <CircularProgress size={24} />
                    </Box>
                ) : (
                    <div style={{ position: 'relative', minWidth: 'max-content', paddingRight: '16px' }}>
                        {/* 月份标签行 */}
                        <div style={{
                            display: 'flex',
                            marginBottom: '6px',
                            height: '14px',
                            position: 'relative'
                        }}>
                            {monthLabels.map((m, idx) => (
                                <Typography
                                    key={idx}
                                    variant="caption"
                                    sx={{
                                        position: 'absolute',
                                        left: `${m.index * cellStep}px`,
                                        fontSize: '10px',
                                        opacity: 0.7,
                                        whiteSpace: 'nowrap'
                                    }}
                                >
                                    {m.label}
                                </Typography>
                            ))}
                        </div>

                        {/* 热力图网格 */}
                        <div style={{ display: 'flex', gap: `${cellGap}px` }}>
                            {weeks.map((week, wIndex) => (
                                <div key={wIndex} style={{ display: 'flex', flexDirection: 'column', gap: `${cellGap}px` }}>
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
            
            <Typography variant="caption" sx={{ opacity: 0.5, mt: 1 }}>
                {selectedYear} 年的预警活跃程度
            </Typography>
        </div>
    );
}
