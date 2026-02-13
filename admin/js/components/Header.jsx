const { Box, Typography, IconButton, Chip } = MaterialUI;
const { useState, useEffect } = React;

/**
 * 实时时钟组件
 */
function RealTimeClock({ timeZone }) {
    const [timeStr, setTimeStr] = useState('');

    useEffect(() => {
        const updateTime = () => {
            const now = new Date();
            // 使用自定义时区格式化
            const formatted = formatTimeWithZone(now.toISOString(), timeZone || 'UTC+8', true);
            // 补全秒数 (formatTimeWithZone 默认只到分)
            const seconds = String(now.getSeconds()).padStart(2, '0');
            setTimeStr(`${formatted}:${seconds}`);
        };

        updateTime();
        const timer = setInterval(updateTime, 1000);
        return () => clearInterval(timer);
    }, [timeZone]);

    // 如果还没有计算出时间，返回 null 或占位符，避免初始渲染闪烁
    if (!timeStr) return null;

    return (
        <div style={{
            // 移除原本强制指定的等宽字体，直接继承 body 的字体设置，与全站保持一致
            // 仅保留数字部分的等宽特性以避免跳动
            fontSize: '14px',
            fontWeight: 700,
            color: 'var(--md-sys-color-primary)',
            background: 'var(--md-sys-color-surface-variant)',
            padding: '4px 12px',
            borderRadius: '8px',
            border: '1px solid var(--md-sys-color-outline-variant)',
            boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginRight: '12px'
        }}>
            <span style={{ fontSize: '14px', opacity: 0.8, fontWeight: 600 }}>当前时间 🕒</span>
            <span style={{
                fontFamily: 'Monaco, Consolas, "Courier New", monospace', // 仅时间数字部分保留等宽字体，防止秒数跳动导致抖动
                fontSize: '15px',
                fontWeight: 800,
                letterSpacing: '0.5px'
            }}>
                {timeStr}
            </span>
        </div>
    );
}

/**
 * 页头组件
 * 显示当前视图标题、WebSocket 连接状态指示器和暗黑模式切换按钮
 *
 * @param {Object} props
 * @param {string} props.currentView - 当前激活的视图名称 ('status' | 'events' | 'stats' | 'config')
 */
function Header({ currentView }) {
    const { state, dispatch } = useAppContext();
    const { config } = state;
    const displayTimezone = config.displayTimezone || 'UTC+8';

    // 切换亮色/暗色主题
    const toggleTheme = () => {
        dispatch({ type: 'TOGGLE_THEME' });
    };

    // 视图标题映射
    const viewTitles = {
        'status': '运行状态',
        'events': '事件列表',
        'stats': '数据统计',
        'config': '配置管理'
    };

    return (
        <div className="top-bar">
            <Typography variant="h5" sx={{
                fontWeight: 800,
                color: 'text.primary',
                letterSpacing: '-0.5px'
            }}>
                {viewTitles[currentView] || viewTitles['status']}
            </Typography>
            
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {/* 实时时钟 */}
                <RealTimeClock timeZone={displayTimezone} />

                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '6px 16px',
                    background: state.wsConnected ? 'rgba(76, 175, 80, 0.1)' : 'rgba(244, 67, 54, 0.1)',
                    borderRadius: '12px',
                    border: `1px solid ${state.wsConnected ? 'rgba(76, 175, 80, 0.2)' : 'rgba(244, 67, 54, 0.2)'}`
                }}>
                    <div style={{
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        background: state.wsConnected ? '#4CAF50' : '#F44336',
                        boxShadow: `0 0 8px ${state.wsConnected ? '#4CAF50' : '#F44336'}`
                    }}></div>
                    <Typography variant="body2" sx={{
                        fontWeight: 600,
                        color: state.wsConnected ? '#4CAF50' : '#F44336',
                        fontSize: '13px'
                    }}>
                        {state.wsConnected ? '已连接' : '未连接'}
                    </Typography>
                </div>
                
                <IconButton 
                    onClick={toggleTheme}
                    sx={{
                        width: 44,
                        height: 44,
                        background: 'var(--md-sys-color-surface)',
                        border: '1px solid var(--glass-border)',
                        boxShadow: '0 2px 8px rgba(0,0,0,0.05)',
                        '&:hover': { background: 'var(--md-sys-color-surface-variant)' }
                    }}
                >
                    <span style={{ fontSize: '18px' }}>
                        {state.theme === 'dark' ? '🌞' : '🌙'}
                    </span>
                </IconButton>
            </Box>
        </div>
    );
}
