const { Typography } = MaterialUI;

/**
 * 区域/类型活跃度排行榜卡片组件 (TopListCard)
 * 用于在统计面板中以排名条形图的形式展示特定范围内的 Top 10 活跃分类。
 * 例如：地震活跃区域排行、气象预警类型排行、或者是数据源贡献率排行。
 * 排行条背景百分比宽度基于当前 Top 1 的最高计数自适应等比算得。
 *
 * @param {Object} props
 * @param {string} props.title 卡片的标题名称（如 '地震高发区域'）
 * @param {string} props.icon 标题前缀小图标/Emoji
 * @param {Array<{count: number, region?: string, type?: string, source?: string}>} props.data 排行榜原始数组数据
 * @param {string} [props.tone='primary'] 彩条的主题色调 (如 'primary' | 'secondary')
 * @param {string} [props.className=''] 外部 CSS 类
 */
function TopListCard({ title, icon, data, tone = 'primary', className = '' }) {
    // 过滤整理原始数组，确保 count 数值类型合规且非负
    const safeData = (Array.isArray(data) ? data : []).map(item => {
        const count = Number(item?.count);
        return {
            ...item,
            count: Number.isFinite(count) && count >= 0 ? count : 0
        };
    });

    // 状态：若无数据，渲染空提示卡片
    if (safeData.length === 0) {
        return (
            <div className={`card top-list-card top-list-card--${tone} ${className}`}>
                <div className="chart-card-header">
                    <span className="stats-card-header-icon">{icon}</span>
                    <Typography variant="h6">{title}</Typography>
                </div>
                <Typography variant="body2" className="top-list-empty-text">
                    暂无数据
                </Typography>
            </div>
        );
    }

    // 获取排第一的最高计数值作为 100% 比例分母基底
    const maxCount = Math.max(1, ...safeData.slice(0, 10).map(d => d.count));

    return (
        <div className={`card top-list-card top-list-card--${tone} ${className}`}>
            {/* 卡片头部 */}
            <div className="chart-card-header">
                <span className="stats-card-header-icon">{icon}</span>
                <Typography variant="h6">{title}</Typography>
            </div>

            {/* 渲染 Top 10 排行项 */}
            <div className="top-list-items">
                {safeData.slice(0, 10).map((item, index) => {
                    // 等比换算条形占比，微调基数防止在极小比例下彩条不可见
                    const percentage = (item.count / maxCount) * 100;

                    return (
                        <div 
                            key={index} 
                            className="top-list-row" 
                            style={{ '--top-list-percent': `calc(${percentage}% + 4px)` }}
                        >
                            {/* 条形填充条 */}
                            <div className="top-list-progress">
                                <div className="top-list-progress-bar"></div>
                            </div>

                            {/* 文字与数值区 */}
                            <div className="top-list-content">
                                <div className="top-list-label-wrap">
                                    {/* 前三名冠亚季军特殊渲染 podium 金银铜效果 */}
                                    <div className={`top-list-rank ${index < 3 ? 'top-list-rank--podium' : ''}`}>
                                        {index + 1}
                                    </div>
                                    <Typography variant="body2" noWrap className="top-list-label">
                                        {/* 智能向下兼容各种字段 key (区域名、事件类型、数据源标识) */}
                                        {item.region ? item.region : (item.type ? item.type : (item.source ? formatSourceName(item.source) : '未知分类'))}
                                    </Typography>
                                </div>
                                <Typography variant="caption" className="top-list-count">
                                    {item.count}
                                </Typography>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
