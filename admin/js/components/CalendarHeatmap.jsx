const { Box, Typography, CircularProgress, Tooltip } = MaterialUI;
const { useState, useEffect, useMemo } = React;

/**
 * 日历热力图组件 (GitHub Style)
 * 展示过去一段时间内每日预警数量的分布
 */
function CalendarHeatmap({ style }) {
    const { getHeatmap } = useApi();
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const response = await getHeatmap(180); // 获取过去半年数据
            setData(response.data || []);
        } catch (error) {
            console.error('获取热力图数据失败:', error);
        } finally {
            setLoading(false);
        }
    };

    // 将数据按周组织
    const weeks = useMemo(() => {
        if (!data || data.length === 0) return [];

        const weeksArr = [];
        let currentWeek = [];
        
        // 补齐第一周前面的空白 (如果不是周一)
        // 这里的 data 已经是按时间顺序排列的
        const firstDate = new Date(data[0].date);
        let firstDay = firstDate.getDay(); // 0 是周日
        if (firstDay === 0) firstDay = 7; // 调整为 1-7 (周一到周日)
        
        // 我们希望每周从周日或周一开始？GitHub 是从周日开始的。
        // 为了简单，我们直接按 7 天一组切分
        for (let i = 0; i < data.length; i++) {
            currentWeek.push(data[i]);
            if (currentWeek.length === 7 || i === data.length - 1) {
                weeksArr.push(currentWeek);
                currentWeek = [];
            }
        }
        
        return weeksArr;
    }, [data]);

    const getColor = (count) => {
        if (count === 0) return 'var(--md-sys-color-surface-variant)';
        if (count < 3) return 'rgba(147, 112, 219, 0.3)'; // 浅紫
        if (count < 6) return 'rgba(147, 112, 219, 0.5)';
        if (count < 10) return 'rgba(147, 112, 219, 0.7)';
        return 'rgba(147, 112, 219, 1)'; // 深紫
    };

    return (
        <div className="card" style={{ ...style, display: 'flex', flexDirection: 'column' }}>
            <div className="chart-card-header" style={{ marginBottom: '16px' }}>
                <span style={{ fontSize: '20px' }}>🗓️</span>
                <Typography variant="h6">历史活动热力图</Typography>
                <div style={{ flex: 1 }}></div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Typography variant="caption" sx={{ opacity: 0.5 }}>Less</Typography>
                    {[0, 2, 5, 8, 12].map(c => (
                        <div key={c} style={{ 
                            width: '10px', 
                            height: '10px', 
                            borderRadius: '2px', 
                            background: getColor(c) 
                        }}></div>
                    ))}
                    <Typography variant="caption" sx={{ opacity: 0.5 }}>More</Typography>
                </div>
            </div>

            <div style={{ flex: 1, overflowX: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '8px 0' }}>
                {loading ? (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', width: '100%', height: '100px' }}>
                        <CircularProgress size={24} />
                    </Box>
                ) : weeks.length > 0 ? (
                    <div style={{ display: 'flex', gap: '3px', margin: 'auto' }}>
                        {weeks.map((week, wIndex) => (
                            <div key={wIndex} style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                {week.map((day, dIndex) => (
                                    <div
                                        key={dIndex}
                                        title={`${day.date}: ${day.count} 次预警`}
                                        style={{
                                            width: '13px',
                                            height: '13px',
                                            borderRadius: '2px',
                                            backgroundColor: getColor(day.count),
                                            transition: 'transform 0.1s',
                                            cursor: 'pointer'
                                        }}
                                        onMouseEnter={(e) => e.target.style.transform = 'scale(1.2)'}
                                        onMouseLeave={(e) => e.target.style.transform = 'scale(1)'}
                                    ></div>
                                ))}
                            </div>
                        ))}
                    </div>
                ) : (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', width: '100%', height: '100px' }}>
                        <Typography variant="body2" sx={{ opacity: 0.5 }}>暂无活动数据</Typography>
                    </Box>
                )}
            </div>
            
            <Typography variant="caption" sx={{ opacity: 0.5, mt: 1 }}>
                显示过去 180 天的预警活跃程度。
            </Typography>
        </div>
    );
}
