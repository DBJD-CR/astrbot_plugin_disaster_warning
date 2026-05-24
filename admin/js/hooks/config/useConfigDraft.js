/**
 * @file useConfigDraft.js
 * @description 管理配置编辑器草稿、折叠状态与滚动位置的本地持久化 Key 发生器及解析器。
 * 
 * 核心设计目标与业务逻辑：
 * 1. 差异化隔离：系统支持“全局配置模式”与“会话覆写配置模式”。
 *    本 Hook 负责生成区分会话 ID 的专属 localStorage 存储 Key，保证管理员在编辑不同会话配置时草稿不会相互覆盖。
 * 2. 状态保存：主要维护三大持久化指标：
 *    - Draft：未保存的表单草稿。
 *    - Expanded Keys：折叠面板展开路径集合，避免切换页面或刷新后已展开的配置项全部闭合。
 *    - Scroll Position：表单垂直滚动偏移量，刷新后自动直达上一次的位置。
 */
function useConfigDraft(mode, selectedSession) {
    /**
     * 生成配置草稿的 localStorage 键名
     */
    const getDraftKey = React.useCallback((currentMode = mode, currentSession = selectedSession) => {
        if (currentMode === 'session' && currentSession) return `astrbot_plugin_dw_draft_config_session_${currentSession}`;
        return 'astrbot_plugin_dw_draft_config_global';
    }, [mode, selectedSession]);

    /**
     * 生成风琴面板展开状态的 localStorage 键名
     */
    const getExpandedKey = React.useCallback((currentMode = mode, currentSession = selectedSession) => {
        if (currentMode === 'session' && currentSession) return `astrbot_plugin_dw_expanded_keys_session_${currentSession}`;
        return 'astrbot_plugin_dw_expanded_keys_global';
    }, [mode, selectedSession]);

    /**
     * 生成表单滚动位置的 localStorage 键名
     */
    const getScrollKey = React.useCallback((currentMode = mode, currentSession = selectedSession) => {
        if (currentMode === 'session' && currentSession) return `astrbot_scroll_config_list_session_${currentSession}`;
        return 'astrbot_scroll_config_list_global';
    }, [mode, selectedSession]);

    /**
     * 健壮地读取本地 JSON 缓存，若发生解析错误或为空则退化到 fallback 默认值
     */
    const readJson = React.useCallback((key, fallback = null) => {
        const raw = localStorage.getItem(key);
        if (!raw) return fallback;
        try { return JSON.parse(raw); } catch (e) { console.error('解析本地缓存失败:', e); return fallback; }
    }, []);

    /**
     * 写入 JSON 缓存
     */
    const writeJson = React.useCallback((key, value) => {
        localStorage.setItem(key, JSON.stringify(value));
    }, []);

    /**
     * 读取先前的滚动垂直高度，进行合理的数值安全断言
     */
    const readScrollPosition = React.useCallback((currentMode = mode, currentSession = selectedSession) => {
        const savedPos = localStorage.getItem(getScrollKey(currentMode, currentSession));
        if (!savedPos) return 0;
        const pos = parseInt(savedPos, 10);
        return Number.isFinite(pos) && pos > 0 ? pos : 0;
    }, [getScrollKey, mode, selectedSession]);

    /**
     * 持续写入最新的滚动高度，拦截负数异常
     */
    const writeScrollPosition = React.useCallback((scrollTop, currentMode = mode, currentSession = selectedSession) => {
        localStorage.setItem(getScrollKey(currentMode, currentSession), String(Math.max(Number(scrollTop) || 0, 0)));
    }, [getScrollKey, mode, selectedSession]);

    return {
        getDraftKey,
        getExpandedKey,
        getScrollKey,
        readJson,
        writeJson,
        readScrollPosition,
        writeScrollPosition,
    };
}
