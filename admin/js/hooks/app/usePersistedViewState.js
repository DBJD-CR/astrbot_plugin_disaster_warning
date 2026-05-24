/**
 * @file usePersistedViewState.js
 * @description 为管理后台的当前活动视图提供本地持久化存储同步的 Hook。
 * 
 * 业务语境：
 * - 用户在控制面板的侧边栏中切换导航 Tab（如从“服务状态”切换到“历史事件”或“配置编辑”）。
 * - 刷新页面时能够自动恢复之前的视图位置，提升管理员的交互连贯性。
 * - 持久化介质：localStorage。
 */
function usePersistedViewState(storageKey = 'currentView', fallbackView = 'status') {
    // 惰性状态初始化：仅在首次挂载时从本地存储提取先前保存的 View Key
    const [currentView, setCurrentView] = React.useState(() => {
        return localStorage.getItem(storageKey) || fallbackView;
    });

    // 副作用监听：一旦 currentView 发生变化，同步将新视图写入 localStorage
    React.useEffect(() => {
        localStorage.setItem(storageKey, currentView);
    }, [currentView, storageKey]);

    return {
        currentView,     // 当前处于激活状态的视图标识（如 status, events, config, stats 等）
        setCurrentView,  // 更新视图的 setter 方法，供侧边栏等导航组件调用
    };
}
