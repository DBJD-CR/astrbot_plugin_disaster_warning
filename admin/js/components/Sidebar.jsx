const { Box, Typography } = MaterialUI;

function Sidebar({ currentView, onViewChange }) {
    const menuItems = [
        { id: 'status', label: '运行状态', icon: '📊' },
        { id: 'events', label: '事件列表', icon: '🔔' },
        { id: 'stats', label: '数据统计', icon: '📈' },
        { id: 'config', label: '配置管理', icon: '⚙️' },
    ];

    return (
        <div className="sidebar">
            {/* Logo */}
            <div className="sidebar-header">
                <div className="sidebar-logo">⚠️</div>
                <div>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
                        灾害预警
                    </Typography>
                    <Typography variant="caption" sx={{ opacity: 0.6 }}>
                        Admin Console
                    </Typography>
                </div>
            </div>

            {/* Navigation Menu */}
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

            {/* Footer */}
            <Box sx={{ p: 1, opacity: 0.5 }}>
                <Typography variant="caption" sx={{ display: 'block', mb: 0.5 }}>
                    AstrBot Plugin v1.2.0
                </Typography>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#4CAF50' }}></div>
                    <Typography variant="caption">System Ready</Typography>
                </div>
            </Box>
        </div>
    );
}
