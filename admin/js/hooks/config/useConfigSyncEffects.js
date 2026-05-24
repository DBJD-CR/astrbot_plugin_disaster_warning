/**
 * @file useConfigSyncEffects.js
 * @description 配置编辑器底层依赖状态改变与本地草稿自动同步写入的 React 副作用协调器。
 * 
 * 核心副作用依赖模型：
 * 1. 深度配置加载同步：当且仅当配置 Schema 加载完成，且初始化 Bootstrap 宣告就绪，
 *    并且用户的 mode、selectedSession 或全量重载 Token reloadToken 发生变化时，
 *    触发一次全新的配置载入任务。通过防重 key 阻止状态抖动时的多余并发网络调度。
 * 2. 脏草稿实时备份：在管理员对表单进行任何修改时，立即捕获最新的 config 对象快照并写入本地 JSON 缓存。
 * 3. 交互结构体保存：每当手风琴 expandedKeys 展开项集发生改变时，将其即时存储。
 */
function useConfigSyncEffects({
    schema,          // 表单 Schema 描述
    mode,            // global / session 模式
    selectedSession, // 选中的会话 ID
    config,          // 内存配置数据体
    expandedKeys,    // 展开状态的面板 Key 路径数组
    draft,           // 持久化存储工具集
    isDirtyRef,      // 标记表单是否存在脏修改的可变引用
    loadConfig,      // 重新载入配置的方法
    initializedRef,  // 页面首次 Bootstrap 是否就绪的引用
    reloadToken,     // 强行刷新的标志计数器
}) {
    const lastLoadedKeyRef = React.useRef('');

    React.useEffect(() => {
        // 未加载 Schema，或尚未经过初始化冷启动，不进行网络请求
        if (!schema || !initializedRef?.current) {
            return;
        }

        const currentKey = `${mode}::${selectedSession || ''}::${reloadToken || 0}`;
        if (lastLoadedKeyRef.current === currentKey) {
            return; // 阻止在渲染抖动下的重复 fetch 请求
        }

        lastLoadedKeyRef.current = currentKey;
        loadConfig(mode, selectedSession, schema);
    }, [initializedRef, loadConfig, mode, reloadToken, schema, selectedSession]);

    React.useEffect(() => {
        // 只有在检测到 config 存在且该修改被 markConfigChanged 确认为“脏更改”时才同步写入草稿
        if (config && isDirtyRef.current) {
            draft.writeJson(draft.getDraftKey(), config);
        }
    }, [config, draft, isDirtyRef]);

    React.useEffect(() => {
        if (schema) {
            // 手动保存折叠展开痕迹，防止切换 Tab 后重新载入页面丢失记忆
            draft.writeJson(draft.getExpandedKey(), expandedKeys);
        }
    }, [draft, expandedKeys, schema]);
}
