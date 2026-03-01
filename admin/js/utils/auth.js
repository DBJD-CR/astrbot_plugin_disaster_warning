/**
 * 认证工具
 * 全局拦截 fetch 请求，自动附加 Authorization 头并处理 401 未授权响应
 */
(function () {
    const TOKEN_KEY = 'astrbot_auth_token';

    window.AuthUtil = {
        getToken: () => localStorage.getItem(TOKEN_KEY),
        setToken: (token) => localStorage.setItem(TOKEN_KEY, token),
        clearToken: () => localStorage.removeItem(TOKEN_KEY),
    };

    const origFetch = window.fetch.bind(window);
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
        // 仅对同源 /api/* 请求附加 token，防止 token 泄露到其他站点
        const isSameOrigin = parsedUrl && parsedUrl.origin === window.location.origin;
        const isApiPath = parsedUrl && parsedUrl.pathname.startsWith('/api');

        if (token && token !== 'no-auth' && isSameOrigin && isApiPath) {
            options = Object.assign({}, options, {
                headers: Object.assign({}, options.headers || {}, {
                    'Authorization': 'Bearer ' + token,
                }),
            });
        }

        return origFetch(url, options).then(function (response) {
            if (response.status === 401 && isSameOrigin && isApiPath && parsedUrl.pathname !== '/api/login') {
                window.AuthUtil.clearToken();
                window.dispatchEvent(new Event('auth-required'));
            }
            return response;
        });
    };
})();
