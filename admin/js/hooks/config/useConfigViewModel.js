/**
 * @file useConfigViewModel.js
 * @description 处理配置页高级交互视图模型的辅助状态派发 Hook。
 * 
 * 核心能力：
 * 1. 群组元数据解构：在切换不同聊天会话群组时，在 Sessions 列表中缓存群名片、通知通道、会话状态等元数据描述信息。
 * 2. 一键展开与折叠控制：全局控制手风琴状态，当检测到已有展开面板时，清空为 [] 实现全局一键折叠；
 *    若已是全部折叠状态，则提取 Schema 树下的所有有效对象容器路径并赋值，实现全局一键展开。
 */
function useConfigViewModel({
    sessions,              // 从服务器拉取的差异会话群组配置元数组
    selectedSession,       // 当前活跃选择的 Session Key
    getVisibleSchema,      // 模式下可暴露给前台表单的 Schema 过滤器
    getAllExpandablePaths, // 抽取 Schema 所有合法可折叠分支路径的算法
    setExpandedKeys,       // 设定手风琴展开路径的 React Setter 接口
}) {
    // 采用 useMemo 精准提取当前会话的元数据对象，避免列表遍历导致的渲染效率退化
    const selectedSessionMeta = React.useMemo(() => (
        sessions.find((item) => item.session === selectedSession)
    ), [selectedSession, sessions]);

    /**
     * 一键全局切换手风琴面板的展开与合拢
     */
    const handleToggleAll = React.useCallback(() => {
        setExpandedKeys((prev) => (
            prev.length > 0 ? [] : getAllExpandablePaths(getVisibleSchema())
        ));
    }, [getAllExpandablePaths, getVisibleSchema, setExpandedKeys]);

    return {
        selectedSessionMeta, // 暴露给顶层工具栏以渲染当前群组的角标与状态
        handleToggleAll,     // 暴露给配置栏的一键收合 Button 点击事件
    };
}
