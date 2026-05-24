const { Box, TextField, ToggleButton, ToggleButtonGroup, MenuItem, Typography, Chip } = MaterialUI;

/**
 * 配置模式切换工具栏组件 (ConfigModeToolbar)
 * 渲染于配置视图的最顶部。用户可以通过该组件快速在“全局配置”与“会话差异配置”之间做无缝切换。
 * 当处于会话差异配置时，允许通过下拉框选择已注册的 IM 聊天会话 (例如 QQ 群、频道等)，
 * 并展示该会话当前是否已启用推送、以及有哪些字段已配置了差异化覆写。
 *
 * @param {Object} props
 * @param {string} props.mode 当前选中的配置模式 ('global' | 'session')
 * @param {Function} props.setMode 更改配置模式的回调函数
 * @param {Array<{session: string}>} props.sessions 服务端拉取到的所有活跃会话列表
 * @param {string} props.selectedSession 当前已选定的特定会话 ID
 * @param {Function} props.setSelectedSession 变更目标会话 ID 的回调函数
 * @param {Object} props.selectedSessionMeta 当前所选会话在服务端的元数据详情（包含覆写的字段列表等）
 * @param {boolean} props.sessionLoading 标识当前是否正在单独拉取特定会话的配置草稿
 */
function ConfigModeToolbar({ 
    mode, 
    setMode, 
    sessions, 
    selectedSession, 
    setSelectedSession, 
    selectedSessionMeta, 
    sessionLoading 
}) {
    return (
        <Box className="config-mode-toolbar">
            {/* 首行：模式切换按钮组与会话过滤字段 */}
            <Box className="config-mode-toolbar__row">
                {/* 切换全局/会话差异化配置的双态按钮组 */}
                <ToggleButtonGroup 
                    exclusive 
                    size="small" 
                    value={mode} 
                    onChange={(e, val) => { if (val) setMode(val); }}
                >
                    <ToggleButton value="global">全局配置</ToggleButton>
                    <ToggleButton value="session">会话差异配置</ToggleButton>
                </ToggleButtonGroup>

                {/* 仅在“会话差异配置”模式下，动态呈现会话选择下拉框及状态标签 */}
                {mode === 'session' && (
                    <>
                        {/* 目标会话选择下拉列表 */}
                        <TextField 
                            select 
                            size="small" 
                            label="目标会话" 
                            value={selectedSession} 
                            onChange={(e) => setSelectedSession(e.target.value)} 
                            className="config-mode-toolbar__session-field"
                        >
                            {sessions.map((item) => (
                                <MenuItem key={item.session} value={item.session}>
                                    {item.session}
                                </MenuItem>
                            ))}
                        </TextField>

                        {/* 如果该会话已经保存了覆盖项，显式用高亮 Chip 提醒 */}
                        {selectedSessionMeta?.has_override && (
                            <Chip size="small" color="primary" label="已存在差异覆写" />
                        )}

                        {/* 单独加载特定会话时的骨架加载提示 */}
                        {sessionLoading && (
                            <Typography variant="caption" color="text.secondary" className="config-mode-toolbar__loading">
                                会话配置加载中...
                            </Typography>
                        )}
                    </>
                )}
            </Box>

            {/* 次行：仅在会话差异化配置模式且已选中会话时渲染，展示当前会话详细覆写状态说明 */}
            {mode === 'session' && selectedSessionMeta && (
                <Typography variant="caption" color="text.secondary" className="config-mode-toolbar__meta">
                    当前会话：{selectedSessionMeta.session} ｜ push_enabled：{selectedSessionMeta.push_enabled ? '开启' : '关闭'} ｜ override字段：{(selectedSessionMeta.override_keys || []).join(', ') || '无'}
                </Typography>
            )}
        </Box>
    );
}
