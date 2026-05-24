/**
 * @file useConfigEditor.js
 * @description 配置编辑器页面的状态聚合与协调核心 Hook。
 * 
 * 架构模型与设计思想：
 * 1. 协调器模式 (Orchestrator Pattern)：该 Hook 本身不包含具体的 API 请求、存储读写或排版计算，
 *    而是作为一个超级控制器，将子 Hook 的状态与方法进行交叉绑定与统一导出。
 * 2. 状态原子化：管理着 Schema、当前草稿、折叠键集、加载态/保存态等元状态，
 *    并将其 setter 和 ref 暴露给负责具体切面（如加载、保存、滚动）的专用子钩子。
 */
function useConfigEditor(showToast) {
    const {
        getAllExpandablePaths,
        isValidSchemaObject,
        cleanConfig,
        generateDefaults,
        pickConfigBySchema,
        getVisibleSchema: deriveVisibleSchema,
    } = window.ConfigSchemaUtils;
    const configApi = window.DisasterConfigApi;
    
    // ==================== 核心状态状态管理 ====================
    const [schema, setSchema] = React.useState(null);              // 从后端获取的配置元 Schema
    const [config, setConfig] = React.useState(null);              // 当前编辑中的配置对象
    const [expandedKeys, setExpandedKeys] = React.useState([]);    // 折叠手风琴面板的展开路径 Key 数组
    const [loading, setLoading] = React.useState(true);            // 页面级骨架屏载入状态
    const [saving, setSaving] = React.useState(false);              // 保存配置时的 Button Pending 状态
    const [loadError, setLoadError] = React.useState('');          // 报错占位图的异常文本
    const [mode, setMode] = React.useState('global');              // 当前配置模式：'global' (全局) 或 'session' (会话差异)
    const [sessions, setSessions] = React.useState([]);            // 可选的聊天群组会话列表
    const [selectedSession, setSelectedSession] = React.useState(''); // 当前选中的会话 ID
    const [sessionLoading, setSessionLoading] = React.useState(false); // 会话切换时的局部 loading 状态
    
    // ==================== 可变引用维护 (Refs) ====================
    const loadConfigSeqRef = React.useRef(0);                      // 加载时序计数器，用于阻断失效的过时异步响应
    const isDirtyRef = React.useRef(false);                        // 标记表单是否存在未保存的脏更改 (Dirty State)
    const [reloadToken, setReloadToken] = React.useState(0);      // 触发全量强制重载的辅助 Token
    const draft = useConfigDraft(mode, selectedSession);          // 持久化存储工具集
    const configScrollRef = React.useRef(null);                    // 配置编辑表单视图容器的 DOM 引用

    /**
     * 基于当前模式过滤并获取对外暴露的可编辑 Schema 树
     */
    const getVisibleSchema = React.useCallback((currentMode = mode, schemaArg = schema) => (
        deriveVisibleSchema(schemaArg, currentMode)
    ), [deriveVisibleSchema, mode, schema]);

    // 子模块1：配置加载与拉取流
    const {
        loadSessions,
        loadConfig,
    } = useConfigLoader({
        api: configApi,
        draft,
        schema,
        mode,
        selectedSession,
        getVisibleSchema,
        getAllExpandablePaths,
        showToast,
        setConfig,
        setExpandedKeys,
        setLoading,
        setSessionLoading,
        setLoadError,
        setSessions,
        setSelectedSession,
        setDirty: (dirty) => {
            isDirtyRef.current = dirty;
        },
        loadConfigSeqRef,
    });

    // 子模块2：页面首次载入的生命周期协调
    const {
        initializePage,
        initializedRef,
    } = useConfigInitialization({
        api: configApi,
        mode,
        selectedSession,
        showToast,
        isValidSchemaObject,
        loadSessions,
        loadConfig,
        setSchema,
        setConfig,
        setLoadError,
        setLoading,
    });

    // 子模块3：草稿自动存储与状态同步的副作用链路
    useConfigSyncEffects({
        schema,
        mode,
        selectedSession,
        config,
        expandedKeys,
        draft,
        isDirtyRef,
        loadConfig,
        initializedRef,
        reloadToken,
    });

    /**
     * 表单字段值变更的回调函数
     */
    const markConfigChanged = React.useCallback((updater) => {
        isDirtyRef.current = true;
        setConfig(updater);
    }, []);

    /**
     * 手风琴节点展收切换
     */
    const handleToggleExpand = React.useCallback((path) => {
        setExpandedKeys((prev) => prev.includes(path) ? prev.filter((item) => item !== path) : [...prev, path]);
    }, []);

    // 子模块4：UI 交互视图模型适配
    const {
        selectedSessionMeta,
        handleToggleAll,
    } = useConfigViewModel({
        sessions,
        selectedSession,
        getVisibleSchema,
        getAllExpandablePaths,
        setExpandedKeys,
    });

    // 子模块5：保存、清空、恢复默认等持久化网络提交操作
    const {
        buildSavePayload,
        handleSave,
        handleResetOverride,
        handleRestoreDefaults,
        handleRevert,
    } = useConfigPersistence({
        api: configApi,
        draft,
        mode,
        selectedSession,
        config,
        getVisibleSchema,
        pickConfigBySchema,
        cleanConfig,
        generateDefaults,
        markConfigChanged,
        loadConfig,
        loadSessions,
        setConfig,
        setSaving,
        setDirty: (dirty) => {
            isDirtyRef.current = dirty;
        },
        showToast,
        triggerReload: () => setReloadToken((prev) => prev + 1),
    });

    // 子模块6：滚动条位置记忆保存还原
    const {
        restoreScrollPosition,
        bindScrollPersistence,
    } = useConfigScrollMemory({
        draft,
        loading,
        mode,
        selectedSession,
        configScrollRef,
    });

    return {
        schema, config, setConfig: markConfigChanged, expandedKeys, loading, saving, loadError,
        mode, setMode, sessions, selectedSession, setSelectedSession, sessionLoading,
        selectedSessionMeta,
        visibleSchema: getVisibleSchema(), getVisibleSchema, initializePage, loadConfig,
        handleToggleExpand, handleToggleAll, handleSave, handleResetOverride, handleRestoreDefaults, handleRevert,
        restoreScrollPosition, bindScrollPersistence,
        draft,
        triggerReload: () => setReloadToken((prev) => prev + 1),
    };
}
