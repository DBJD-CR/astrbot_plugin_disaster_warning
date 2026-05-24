/**
 * @file useConfigInitialization.js
 * @description 配置编辑视图的首次就绪初始化 Hook。
 * 
 * 逻辑执行顺序说明：
 * 1. 锁定 loading 状态，重置错误信息。
 * 2. 并发向后端请求插件的全局配置 Schema 声明。如果 Schema 解析失败或不合法，抛出异常。
 * 3. 异步拉取已配置差异覆盖的会话 (Session) 列表，并在此处根据先前的状态还原默认选择的群组。
 * 4. 完成上述核心字典拉取后，调用 loadConfig 按加载的模式加载特定的配置参数。
 */
function useConfigInitialization({
    api,                 // 后台 API 工具包
    mode,                // 模式：global / session
    selectedSession,     // 选中的 Session ID
    showToast,           // 消息通知
    isValidSchemaObject, // 判定 Schema 校验函数
    loadSessions,        // 异步载入会话列表函数
    loadConfig,          // 加载特定配置函数
    setSchema,           // Schema 更新器
    setConfig,           // 配置体更新器
    setLoadError,        // 异常说明更新器
    setLoading,          // 加载遮罩控制器
}) {
    /**
     * 并发初始化页面声明
     */
    const initializePage = React.useCallback(async () => {
        setLoading(true);
        setLoadError('');
        try {
            // Step 1: 加载底层 Schema 表单元素描述规则
            const schemaData = await api.getConfigSchema();
            if (!isValidSchemaObject(schemaData)) {
                throw new Error(schemaData?.error || '配置 Schema 加载失败，服务端返回了无效数据');
            }
            setSchema(schemaData);

            // Step 2: 载入覆写会话列表
            const sessionList = await loadSessions();
            
            // Step 3: 根据历史 Session 匹配回填激活项，若无则默认指向列表第一个或清空
            const resolvedSession = selectedSession && sessionList.some((item) => item.session === selectedSession)
                ? selectedSession
                : (sessionList[0]?.session || '');
            
            // Step 4: 拉取对应状态的具体配置参数值
            await loadConfig(mode, resolvedSession, schemaData);
        } catch (e) {
            console.error('初始化配置页失败', e);
            setSchema(null);
            setConfig(null);
            setLoadError(e?.message || '初始化配置页失败，请检查后端配置接口');
            showToast('初始化配置页失败,请检查控制台', 'error');
            setLoading(false);
        }
    }, [api, isValidSchemaObject, loadConfig, loadSessions, mode, selectedSession, setConfig, setLoadError, setLoading, setSchema, showToast]);

    const initializedRef = React.useRef(false);

    // 仅在组件首次挂载且 initializedRef.current 为 false 时触发一次自执行
    React.useEffect(() => {
        if (initializedRef.current) {
            return;
        }
        initializedRef.current = true;
        initializePage();
    }, [initializePage]);

    return {
        initializePage,
        initializedRef,
    };
}
