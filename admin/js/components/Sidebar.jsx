const { Box, Typography } = MaterialUI;

/**
 * 侧边栏导航组件
 * 提供应用的主要导航功能，包括状态概览、事件列表、统计信息和配置管理
 *
 * @param {Object} props
 * @param {string} props.currentView - 当前选中的视图ID
 * @param {Function} props.onViewChange - 视图切换回调函数
 */
function Sidebar({ currentView, onViewChange }) {
    const { state } = useAppContext();
    const { version } = state.status;
    const { showToast } = useToast(); // 使用 Toast 提示

    const menuItems = [
        { id: 'status', label: '运行状态', icon: '📊' },
        { id: 'events', label: '事件列表', icon: '🔔' },
        { id: 'stats', label: '数据统计', icon: '📈' },
        { id: 'config', label: '配置管理', icon: '⚙️' },
    ];

    return (
        <div className="sidebar">
            {/* Logo 图标 */}
            <div className="sidebar-header">
                <img src="/logo.png" alt="Logo" className="sidebar-logo-img" />
                <div>
                    <Typography variant="h6" sx={{ fontWeight: 800, lineHeight: 1.2, letterSpacing: '-0.5px' }}>
                        灾害预警
                    </Typography>
                    <Typography variant="caption" sx={{ opacity: 0.6, display: 'block', mt: 0.5 }}>
                        Admin Console
                    </Typography>
                </div>
            </div>

            {/* 导航菜单 */}
            <Box sx={{ flex: 1, mt: 4 }}>
                {menuItems.map((item) => (
                    <div 
                        key={item.id} 
                        className={`nav-item ${currentView === item.id ? 'active' : ''}`}
                        onClick={() => onViewChange(item.id)}
                    >
                        <span style={{ fontSize: '18px' }}>{item.icon}</span>
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>
                            {item.label}
                        </Typography>
                    </div>
                ))}
            </Box>

            {/* 底部信息栏 */}
            <Box sx={{ px: 2, pt: 0, pb: 0 }}>
                <button
                    className="btn"
                    onClick={() => {
                        fetch('/api/open-plugin-dir', { method: 'POST' })
                            .then(res => res.json())
                            .then(data => {
                                if (data.success) {
                                    // 成功则不打扰用户
                                } else {
                                    showToast(data.error || '打开失败', 'error');
                                }
                            })
                            .catch(err => showToast('请求失败: ' + err, 'error'));
                    }}
                    style={{
                        width: '100%',
                        marginBottom: '16px',
                        padding: '10px',
                        fontSize: '13px',
                        background: 'rgba(0, 0, 0, 0.05)',
                        color: 'var(--md-sys-color-on-surface)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '8px',
                        // 暗色模式下的内联样式覆盖
                        ...(state.theme === 'dark' ? {
                            background: 'rgba(255, 255, 255, 0.08)',
                            border: '1px solid rgba(255, 255, 255, 0.05)'
                        } : {})
                    }}
                >
                    <span style={{ fontSize: '16px', marginLeft: '-6px' }}>📂</span>
                    打开插件文件目录
                </button>
                
                <a
                    href="https://github.com/DBJD-CR/astrbot_plugin_disaster_warning"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="github-btn"
                    style={{ textDecoration: 'none' }}
                >
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px',
                        padding: '12px',
                        background: 'rgba(0, 0, 0, 0.03)',
                        borderRadius: '12px',
                        transition: 'all 0.2s ease',
                        border: '1px solid rgba(0, 0, 0, 0.06)',
                        cursor: 'pointer',
                        ...(state.theme === 'dark' ? {
                            background: 'rgba(255, 255, 255, 0.05)',
                            border: '1px solid rgba(255, 255, 255, 0.05)'
                        } : {})
                    }}>
                        {/* GitHub Logo - 适配暗色模式 */}
                        <svg height="28" width="28" viewBox="0 0 16 16" fill={state.theme === 'dark' ? '#E6E1E5' : '#000000'} style={{ flexShrink: 0 }}>
                            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
                        </svg>
                        
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', overflow: 'hidden' }}>
                            {/* 第一行: 作者与仓库信息 */}
                            <Typography variant="caption" sx={{
                                fontWeight: 700,
                                color: 'text.primary',
                                fontSize: '0.75rem',
                                lineHeight: 1.2,
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                display: 'block',
                                maxWidth: '170px'
                            }}>
                                @DBJD-CR & Aloys233
                            </Typography>
                            
                            {/* 第二行: 插件名称 + 版本号 */}
                            <Typography variant="caption" sx={{
                                display: 'block',
                                opacity: 0.6,
                                lineHeight: 1.2,
                                fontSize: '0.7rem',
                                color: 'text.secondary' // 强制使用次级文本颜色，避免受主题色影响
                            }}>
                                🔧 (灾害预警) {version || '...'}
                            </Typography>
                        </div>
                    </div>
                </a>
                <Typography variant="caption" sx={{ display: 'block', textAlign: 'center', mt: 1, opacity: 0.7, fontSize: '14px', fontWeight: 500 }}>
                    点个 Star 吧~ ⭐
                </Typography>
            </Box>
        </div>
    );
}
