/**
 * 认证工具
 * 全局拦截 fetch 请求，自动附加 Authorization 头并处理 401 未授权响应
 */
(function () {
    // 本地存储中保存鉴权令牌的键名
    const TOKEN_KEY = 'astrbot_auth_token';

    // 导出全局鉴权读取、写入及清除的工具对象
    window.AuthUtil = {
        getToken: () => localStorage.getItem(TOKEN_KEY),
        setToken: (token) => localStorage.setItem(TOKEN_KEY, token),
        clearToken: () => localStorage.removeItem(TOKEN_KEY),
    };

    // 保存原生的 fetch 接口指针以供重载调用
    const origFetch = window.fetch.bind(window);
    
    // 重载全局 fetch 接口以实现身份验证切面注入
    window.fetch = function (url, options) {
        options = options || {};
        const token = window.AuthUtil.getToken();
        const urlStr = typeof url === 'string' ? url : (url && url.url) || '';

        // 解析 URL，支持相对路径和绝对路径，基于 pathname 判断是否为 /api/* 请求
        let parsedUrl;
        try {
            parsedUrl = new URL(urlStr, window.location.origin);
        } catch (e) {
            parsedUrl = null;
        }
        
        // 安全拦截：仅对同源且为 api 开头的请求附加 token 令牌，防止泄漏身份至三方服务
        const isSameOrigin = parsedUrl && parsedUrl.origin === window.location.origin;
        const isApiPath = parsedUrl && parsedUrl.pathname.startsWith('/api');

        if (token && token !== 'no-auth' && isSameOrigin && isApiPath) {
            options = Object.assign({}, options, {
                headers: Object.assign({}, options.headers || {}, {
                    'Authorization': 'Bearer ' + token, // 拼装标准 Bearer 格式的头部字段
                }),
            });
        }

        // 调用原生接口发送请求并截获响应
        return origFetch(url, options).then(function (response) {
            // 若接口报错 401 且不属于登录 API，说明令牌失效，清除本地令牌并抛出 auth-required 事件
            if (response.status === 401 && isSameOrigin && isApiPath && parsedUrl.pathname !== '/api/login') {
                window.AuthUtil.clearToken();
                window.dispatchEvent(new Event('auth-required')); // 广播重登信号，触发前端页面刷新跳转
            }
            return response;
        });
    };
})();
