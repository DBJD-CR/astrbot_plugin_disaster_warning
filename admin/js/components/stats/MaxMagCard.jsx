const { Box, Typography, Chip } = MaterialUI;

function MaxMagCard({ style }) {
    const { state } = useAppContext();
    const { stats, config } = state;
    const displayTimezone = config.displayTimezone || 'UTC+8';
    const maxMag = stats && stats.maxMagnitude ? stats.maxMagnitude : null;
    const magValue = Number(maxMag?.value);
    const displayMag = Number.isFinite(magValue) ? magValue.toFixed(1) : '--';
    const displayPlace = maxMag?.place_name || '暂无震中信息';

    // 格式化时间
    const formatTime = (time) => {
        if (!time) return '未知时间';
        return formatTimeWithZone(time, displayTimezone, true);
    };

    if (!maxMag) {
        return (
            <div className="card" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', minHeight: '200px', ...style }}>
                <span style={{ fontSize: '48px', opacity: 0.2 }}>📉</span>
                <Typography variant="body2" sx={{ opacity: 0.5, mt: 1 }}>暂无最大震级记录</Typography>
            </div>
        );
    }

    return (
        <div className="card" style={{
            background: 'linear-gradient(135deg, var(--md-sys-color-error-container) 0%, var(--md-sys-color-surface) 100%)',
            position: 'relative',
            overflow: 'hidden',
            height: '100%', // 确保填满容器
            ...style
        }}>
            <div style={{
                position: 'absolute',
                top: '-10px',
                right: '-10px',
                fontSize: '100px',
                opacity: 0.05,
                pointerEvents: 'none',
                userSelect: 'none'
            }}>🔥</div>

            <div className="chart-card-header" style={{ marginBottom: '16px' }}>
                <span style={{ fontSize: '20px' }}>🔥</span>
                <Typography variant="h6" sx={{ color: 'var(--md-sys-color-on-error-container)' }}>历史最大地震</Typography>
            </div>
            
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '8px' }}>
                <Typography variant="h3" sx={{
                    fontWeight: 800,
                    color: 'var(--md-sys-color-error)',
                    lineHeight: 1
                }}>
                    <span style={{ marginRight: '8px' }}>M</span>{displayMag}
                </Typography>
                {maxMag?.source && (
                    <Chip
                        label={formatSourceName(maxMag.source)}
                        size="small"
                        sx={{
                            height: '24px',
                            fontSize: '12px',
                            background: 'rgba(255,255,255,0.3)',
                            color: 'var(--md-sys-color-on-error-container)'
                        }} 
                    />
                )}
            </div>

            <Typography variant="body1" sx={{ fontWeight: 800, mb: 1, color: 'var(--md-sys-color-on-error-container)' }}>
                {displayPlace}
            </Typography>
            
            <Typography variant="body2" sx={{ opacity: 0.7, color: 'var(--md-sys-color-on-error-container)' }}>
                {formatTime(maxMag?.time)}
            </Typography>
        </div>
    );
}
