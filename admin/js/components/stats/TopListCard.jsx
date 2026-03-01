const { Typography } = MaterialUI;

function TopListCard({ title, icon, data, color, style }) {
    const safeData = (Array.isArray(data) ? data : []).map(item => {
        const count = Number(item?.count);
        return {
            ...item,
            count: Number.isFinite(count) && count >= 0 ? count : 0
        };
    });

    if (safeData.length === 0) {
        return (
            <div className="card" style={{ height: '100%', minHeight: '200px', ...style }}>
                <div className="chart-card-header">
                    <span style={{ fontSize: '20px' }}>{icon}</span>
                    <Typography variant="h6">{title}</Typography>
                </div>
                <Typography variant="body2" sx={{ opacity: 0.5, textAlign: 'center', py: 4 }}>
                    暂无数据
                </Typography>
            </div>
        );
    }

    // 计算最大值，用于比例条
    const maxCount = Math.max(1, ...safeData.slice(0, 10).map(d => d.count));

    return (
        <div className="card" style={{ height: '100%', minHeight: '200px', ...style }}>
            <div className="chart-card-header">
                <span style={{ fontSize: '20px' }}>{icon}</span>
                <Typography variant="h6">{title}</Typography>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {safeData.slice(0, 10).map((item, index) => {
                    const percentage = (item.count / maxCount) * 100;

                    return (
                        <div key={index} style={{ position: 'relative', padding: '6px 8px', borderRadius: '8px', zIndex: 1, overflow: 'hidden' }}>
                            {/* 进度条背景 - 从文字开始 (跳过数字标号)，稍微左移一点包裹文字 */}
                            <div style={{
                                position: 'absolute',
                                top: '4px',
                                bottom: '4px',
                                left: '40px', // 稍微往左移一点 (44px -> 40px)
                                right: '8px',
                                zIndex: -1,
                            }}>
                                <div style={{
                                    width: `calc(${percentage}% + 4px)`, // 稍微加宽一点补偿左移
                                    height: '100%',
                                    background: color,
                                    opacity: 0.2,
                                    borderRadius: '4px',
                                    transition: 'width 0.5s ease-out'
                                }}></div>
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', position: 'relative' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: 0, marginRight: '8px' }}>
                                    <div style={{
                                        width: '24px',
                                        height: '24px',
                                        borderRadius: '6px',
                                        background: index < 3 ? color : 'var(--md-sys-color-surface-variant)',
                                        color: index < 3 ? '#fff' : 'inherit',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        fontSize: '12px',
                                        fontWeight: 700,
                                        flexShrink: 0
                                    }}>
                                        {index + 1}
                                    </div>
                                    <Typography variant="body2" noWrap sx={{ fontWeight: 600, fontSize: '13px' }}>
                                        {item.region ? item.region : (item.type ? item.type : (item.source ? formatSourceName(item.source) : '未知分类'))}
                                    </Typography>
                                </div>
                                <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.7, flexShrink: 0 }}>
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
