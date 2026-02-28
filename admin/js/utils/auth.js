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

        // 仅对 /api/* 路径附加 token
        if (token && token !== 'no-auth' && urlStr.startsWith('/api')) {
            options = Object.assign({}, options, {
                headers: Object.assign({}, options.headers || {}, {
                    'Authorization': 'Bearer ' + token,
                }),
            });
        }

        return origFetch(url, options).then(function (response) {
            if (response.status === 401 && urlStr.startsWith('/api') && urlStr !== '/api/login') {
                window.AuthUtil.clearToken();
                window.dispatchEvent(new Event('auth-required'));
            }
            return response;
        });
    };
})();
