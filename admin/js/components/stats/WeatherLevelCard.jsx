const { Typography } = MaterialUI;

/**
 * 气象预警级别环形比例图表组件 (WeatherLevelCard)
 * 该组件分析系统捕获的气象预警，按其危险警示等级颜色（红、橙、黄、蓝、白等）进行归类统计，
 * 并以圆环饼图 (CSS conic-gradient 实现) 与明细列表形式展示各自的比重。
 *
 * @param {Object} props
 * @param {Object} [props.style] 外部自定义样式
 * @param {string} [props.className=''] 外部类
 */
function WeatherLevelCard({ style, className = '' }) {
    const { state } = useAppContext();
    const { stats } = state;
    
    // 获取气象级别统计数组，过滤无计数的空档
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

    // 状态：若无任何气象统计数据，渲染空卡片
    if (weatherLevels.length === 0) {
        return (
            <div className={`card weather-level-card ${className}`} style={style}>
                <div className="chart-card-header">
                    <span className="stats-card-header-icon">🎨</span>
                    <Typography variant="h6">气象预警级别</Typography>
                </div>
                <Typography variant="body2" className="weather-level-card-empty-text">
                    暂无数据
                </Typography>
            </div>
        );
    }

    // 计算当前所有级别警报总条数
    const total = weatherLevels.reduce((acc, curr) => acc + curr.count, 0);
    
    // 用于 CSS conic-gradient 绘制时的累加起始度数百分比
    let currentAngle = 0;

    // 状态：若累计条数异常，同样渲染空卡片
    if (total <= 0) {
        return (
            <div className={`card weather-level-card ${className}`} style={style}>
                <div className="chart-card-header">
                    <span className="stats-card-header-icon">🎨</span>
                    <Typography variant="h6">气象预警级别</Typography>
                </div>
                <Typography variant="body2" className="weather-level-card-empty-text">
                    暂无有效统计数据
                </Typography>
            </div>
        );
    }

    /**
     * 预警危险等级颜色映射：将汉字级别绑定到 CSS 全局重置的 MD3 预警主题变量上
     */
    const getColor = (level) => {
        const text = String(level || '');
        if (text.includes('红')) return 'var(--weather-level-color-red)';
        if (text.includes('橙')) return 'var(--weather-level-color-orange)';
        if (text.includes('黄')) return 'var(--weather-level-color-yellow)';
        if (text.includes('蓝')) return 'var(--weather-level-color-blue)';
        if (text.includes('白')) return 'var(--weather-level-color-white)';
        return 'var(--weather-level-color-default)';
    };

    return (
        <div className={`card weather-level-card ${className}`} style={style}>
            {/* 卡片头部 */}
            <div className="chart-card-header">
                <span className="stats-card-header-icon">🎨</span>
                <Typography variant="h6">气象预警级别</Typography>
            </div>
            
            <div className="weather-level-card-body">
                {/* 1. 圆环图区：使用 conic-gradient 累加切分圆环弧度 */}
                <div
                    className="weather-level-card-donut"
                    style={{
                        background: `conic-gradient(${weatherLevels.map(item => {
                            const start = currentAngle;
                            const percentage = (item.count / total) * 100;
                            currentAngle += percentage; // 累加角度百分比
                            return `${getColor(item.level)} ${start}% ${currentAngle}%`;
                        }).join(', ')})`,
                    }}
                >
                    {/* 圆环中间掏空，陈列合计总数 */}
                    <div className="weather-level-card-donut-inner">
                        <Typography variant="h5" className="weather-level-card-total">
                            {total}
                        </Typography>
                        <Typography variant="caption" className="weather-level-card-total-label">
                            预警总数
                        </Typography>
                    </div>
                </div>

                {/* 2. 右侧明细数据列表 */}
                <div className="weather-level-card-list">
                    {weatherLevels.map((item, index) => (
                        <div key={index} className="weather-level-card-row">
                            {/* 等级名称以及左侧色条标识 */}
                            <div className="weather-level-card-row-label">
                                <span className="weather-level-card-level">{item.level}</span>
                            </div>
                            {/* 条目数及比重 */}
                            <div className="weather-level-card-row-metrics">
                                <span className="weather-level-card-count">{item.count}</span>
                                <span className="weather-level-card-ratio">
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
