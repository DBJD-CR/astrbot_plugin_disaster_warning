const { Box, Typography, Button, Paper, CircularProgress } = MaterialUI;
const { useRef, useLayoutEffect, useEffect } = React;

/**
 * 核心配置渲染器组件 (ConfigRenderer)
 * 作为全局配置管理视图的主入口，它不进行具体的业务逻辑计算，
 * 而是依靠 `useConfigEditor` ViewModel 钩子接管并消费包括：
 * 加载骨架屏、配置异常排版、全局/会话差异化模式切换、展开折叠列表状态、表单保存、草稿控制、以及滚动条记忆持久化等全部状态。
 */
function ConfigRenderer() {
    // 实例化轻量 Toast 控制器
    const { showToast } = useToast();
    
    // 驱动配置视图状态的主驱动 ViewModel Hook
    const editor = useConfigEditor(showToast);
    
    // 指向可滚动主区域容器的 React Ref，用于控制和恢复滚动条的垂直位移
    const scrollContainerRef = useRef(null);

    // 解构获取 ViewModel 提供出来的所有控制器与交互状态
    const {
        schema,
        config,
        setConfig,
        expandedKeys,
        loading,
        saving,
        loadError,
        mode,
        setMode,
        sessions,
        selectedSession,
        setSelectedSession,
        sessionLoading,
        selectedSessionMeta,
        visibleSchema,
        initializePage,
        handleToggleExpand,
        handleToggleAll,
        handleSave,
        handleResetOverride,
        handleRestoreDefaults,
        handleRevert,
        restoreScrollPosition,
        bindScrollPersistence,
    } = editor;

    // 布局同步副作用：在加载完毕或切换模式/会话后，同步恢复先前滚动条所处的高度，杜绝闪烁和视线丢失
    useLayoutEffect(() => {
        if (!loading && scrollContainerRef.current) {
            restoreScrollPosition();
        }
    }, [loading, mode, selectedSession, restoreScrollPosition]);

    // 滚动监听副作用：监听滚动容器的滚动偏移并写入 SessionStorage
    useEffect(() => {
        const el = scrollContainerRef.current;
        if (!el) return;
        return bindScrollPersistence(el);
    }, [bindScrollPersistence, loading, mode, selectedSession]);

    // 1. 状态：正在从服务端加载配置或 Schema 时，渲染全局齿轮图标以及转圈圈加载动画
    if (loading) {
        return (
            <Box className="config-renderer-state config-renderer-state--loading" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 0' }}>
                <Box className="config-renderer-state__icon">⚙️</Box>
                <CircularProgress size={28} style={{ marginBottom: '16px' }} />
                <Typography variant="body2" color="text.secondary">正在加载配置，请稍候...</Typography>
            </Box>
        );
    }

    // 2. 状态：数据包为空或请求发生故障时，渲染友好、附带重试按钮的错误卡片
    if (!schema || !config) {
        return (
            <Box className="config-renderer-error-shell">
                <Paper elevation={0} className="config-renderer-error-card">
                    <Box className="config-renderer-error-card__icon">⚠️</Box>
                    <Typography variant="h6" color="error" className="config-renderer-error-card__title">
                        配置加载失败
                    </Typography>
                    <Typography variant="body2" color="text.secondary" className="config-renderer-error-card__message">
                        {loadError || '未能从服务端获取有效的配置 Schema 或配置对象。'}
                    </Typography>
                    <Box className="config-renderer-error-card__actions">
                        <Button 
                            variant="contained" 
                            onClick={initializePage} 
                            startIcon={<span>🔄</span>} 
                            className="config-renderer-error-card__btn"
                        >
                            重新加载配置
                        </Button>
                        <Button 
                            variant="outlined" 
                            onClick={() => { setMode('global'); setSelectedSession(''); initializePage(); }} 
                            startIcon={<span>🏠</span>} 
                            className="config-renderer-error-card__btn"
                        >
                            回到全局配置重试
                        </Button>
                    </Box>
                </Paper>
            </Box>
        );
    }

    // 会话覆盖特有排版排序：当处于 session 模式时，将 `push_enabled` (是否启用差异覆盖) 强制提升置顶，使其位于风琴面板顶端
    const visibleSchemaEntries = Object.entries(visibleSchema || {}).sort(([keyA], [keyB]) => {
        if (mode === 'session') {
            if (keyA === 'push_enabled') return -1;
            if (keyB === 'push_enabled') return 1;
        }
        return 0;
    });

    return (
        <Box className="config-renderer-shell">
            {/* 顶栏：全局配置与特定会话筛选切换条 */}
            <ConfigModeToolbar
                mode={mode}
                setMode={setMode}
                sessions={sessions}
                selectedSession={selectedSession}
                setSelectedSession={setSelectedSession}
                selectedSessionMeta={selectedSessionMeta}
                sessionLoading={sessionLoading}
            />

            {/* 中间：带有滚动持久化的可拖拽表单滚动区域 */}
            <Box ref={scrollContainerRef} className="config-renderer-scroll-area">
                <Box className="config-renderer-field-list">
                    {visibleSchemaEntries.map(([key, subSchema]) => (
                        <Box key={key} className="config-renderer-field-item">
                            <ConfigField
                                fieldKey={key}
                                schema={subSchema}
                                value={config[key]}
                                // 交互回调：深拷贝当前草稿 config 并单项覆写，同时同步回 React State
                                onChange={(newValue) => setConfig((prev) => ({ ...prev, [key]: newValue }))}
                                path=""
                                expandedKeys={expandedKeys}
                                onToggleExpand={handleToggleExpand}
                            />
                        </Box>
                    ))}
                </Box>
            </Box>

            {/* 底栏：全局动作交互控制栏 */}
            <ConfigActionBar
                visibleCount={visibleSchemaEntries.length}
                expandedKeys={expandedKeys}
                onToggleAll={handleToggleAll}
                saving={saving}
                mode={mode}
                selectedSession={selectedSession}
                onRestoreDefaults={handleRestoreDefaults}
                onRevert={handleRevert}
                onResetOverride={handleResetOverride}
                onSave={handleSave}
            />
        </Box>
    );
}
