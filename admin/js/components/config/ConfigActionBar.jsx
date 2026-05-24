const { Box, Typography, Button } = MaterialUI;

/**
 * 配置保存操作栏组件 (ConfigActionBar)
 * 渲染于配置管理视图的最底部，为用户提供配置组展开/折叠状态统计、
 * 全局/会话差异化配置的保存、恢复默认、撤销更改及清空会话覆写等控制指令。
 *
 * @param {Object} props
 * @param {number} props.visibleCount 当前在界面上渲染的可见配置组总数
 * @param {string[]} props.expandedKeys 当前已处于展开状态的配置节点路径数组 (用于计算收起/展开文本)
 * @param {Function} props.onToggleAll 切换全部展开或收起状态的回调函数
 * @param {boolean} props.saving 标识当前是否正在与服务端通信保存中
 * @param {string} props.mode 当前配置模式 ('global' 全局配置 | 'session' 会话差异化配置)
 * @param {string} props.selectedSession 当前选中的特定会话 ID
 * @param {Function} props.onRestoreDefaults 恢复该模式下全局/当前会话默认配置的回调函数
 * @param {Function} props.onRevert 撤销未保存的本地草稿更改并重新载入服务端当前配置的回调函数
 * @param {Function} props.onResetOverride 清空当前选定会话的所有差异化覆写配置的回调函数
 * @param {Function} props.onSave 执行保存动作的回调函数
 */
function ConfigActionBar({ 
    visibleCount, 
    expandedKeys, 
    onToggleAll, 
    saving, 
    mode, 
    selectedSession, 
    onRestoreDefaults, 
    onRevert, 
    onResetOverride, 
    onSave 
}) {
    return (
        <Box className="config-action-bar">
            {/* 左侧：统计与批量展开/折叠控件 */}
            <Box className="config-action-bar__meta">
                <Typography variant="caption" color="text.secondary" className="config-action-bar__count">
                    {visibleCount} 个配置组
                </Typography>
                <Button 
                    onClick={onToggleAll} 
                    size="small" 
                    variant="text" 
                    className="config-action-bar__toggle-btn"
                >
                    {expandedKeys.length > 0 ? '全部收起' : '全部展开'}
                </Button>
            </Box>
            
            {/* 右侧：动作操作按钮序列 */}
            <Box className="config-action-bar__actions">
                {/* 恢复默认按钮 */}
                <Button 
                    onClick={onRestoreDefaults} 
                    disabled={saving} 
                    variant="outlined" 
                    color="error" 
                    size="medium" 
                    startIcon={<span>🗑️</span>} 
                    className="config-action-bar__btn"
                >
                    恢复默认
                </Button>

                {/* 撤销更改按钮 */}
                <Button 
                    onClick={onRevert} 
                    disabled={saving} 
                    variant="outlined" 
                    size="medium" 
                    startIcon={<span>↩️</span>} 
                    className="config-action-bar__btn"
                >
                    撤销更改
                </Button>

                {/* 会话覆盖特有：清空会话专属覆写项按钮 */}
                {mode === 'session' && (
                    <Button 
                        onClick={onResetOverride} 
                        disabled={saving || !selectedSession} 
                        variant="outlined" 
                        color="warning" 
                        size="medium" 
                        startIcon={<span>♻️</span>} 
                        className="config-action-bar__btn config-action-bar__btn--wide"
                    >
                        清空会话覆写
                    </Button>
                )}

                {/* 核心保存按钮 */}
                <Button 
                    variant="contained" 
                    onClick={onSave} 
                    disabled={saving} 
                    size="medium" 
                    startIcon={<span>💾</span>} 
                    className="config-action-bar__save-btn"
                >
                    {saving ? '保存中...' : (mode === 'session' ? '保存会话配置' : '保存配置')}
                </Button>
            </Box>
        </Box>
    );
}
