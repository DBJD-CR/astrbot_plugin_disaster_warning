/**
 * @file useAuthReadyState.js
 * @description 管理与 AstrBot 的鉴权状态同步钩子。
 * 
 * 核心机制说明：
 * 1. 鉴权等待：如果 AstrBot 面板的鉴权流程尚未就绪 (window.__ASTRBOT_AUTH_PENDING 为 true)，
 *    则拦截后续视图加载，直到触发自定义事件 auth-ready。
 * 2. 热重载拦截：一旦系统收到鉴权过期的 auth-required 信号，立即强制刷新页面以便重定向到登录页面。
 */
function useAuthReadyState() {
    // 依据全局挂载的鉴权挂起状态来决定初始的就绪状态
    const [ready, setReady] = React.useState(() => !window.__ASTRBOT_AUTH_PENDING);

    React.useEffect(() => {
        if (ready) return;
        const handleReady = () => setReady(true);
        
        // 注册 AstrBot 框架广播的鉴权就绪事件监听器
        window.addEventListener('auth-ready', handleReady);
        
        // 双重检查防线：在监听期间，若状态已被其他宏任务置为就绪，则直接解开就绪状态
        if (!window.__ASTRBOT_AUTH_PENDING) {
            setReady(true);
        }
        
        return () => window.removeEventListener('auth-ready', handleReady);
    }, [ready]);

    React.useEffect(() => {
        // 监听到 token 失效或需要鉴权时，通过 reload 重塑页面上下文
        const handleAuthRequired = () => window.location.reload();
        window.addEventListener('auth-required', handleAuthRequired);
        return () => window.removeEventListener('auth-required', handleAuthRequired);
    }, []);

    return ready;
}
