(() => {
    /**
     * 灾害预警插件的通用网络请求工具。
     * 
     * 核心设计要点：
     * 1. 响应结构自动解包 (unwrapApiResponse)：为了简化前台业务组件对数据字典的读取，
     *    当检测到后端返回了标准的包裹式结构 { success: true, data: ... } 时，
     *    自动剥离外层的 success 状态并将核心的 data 部分解包返回；对于非标准数据则原样透传。
     * 2. 查询参数处理 (buildUrl)：支持解析数组形式的参数。例如多数据源多选 [A, B] 会被自动合并为 A,B 的字符串格式拼接，
     *    同时自动过滤空字符串、null 及 undefined 异常属性，保证请求 URL 地址整洁。
     * 3. 错误统一拦截：当网络响应状态码非 2xx 时，自动提取 JSON 回包中的具体错误文案并打包抛出，
     *    方便下级捕获后在界面渲染报错占位卡片。
     */
    const API_BASE = '/api';

    /**
     * 判定目标对象是否为普通对象类型
     */
    function isPlainObject(value) {
        return value !== null && typeof value === 'object' && !Array.isArray(value);
    }

    /**
     * 对网络返回数据进行提取和解包
     */
    function unwrapApiResponse(payload) {
        if (isPlainObject(payload) && payload.success === true && payload.data !== undefined) {
            return payload.data;
        }
        return payload;
    }

    /**
     * 构建带有查询参数的完整 API 请求路径
     */
    function buildUrl(endpoint, query = null, baseUrl = '') {
        const normalizedEndpoint = String(endpoint || '').startsWith('/')
            ? String(endpoint || '')
            : `/${String(endpoint || '')}`;
        const cleanBaseUrl = String(baseUrl || '').replace(/\/$/, '');
        const url = `${cleanBaseUrl}${API_BASE}${normalizedEndpoint}`;

        if (!query || typeof query !== 'object') {
            return url;
        }

        const params = new URLSearchParams();
        Object.entries(query).forEach(([key, value]) => {
            if (value === undefined || value === null || value === '') return;
            if (Array.isArray(value)) {
                if (value.length === 0) return;
                // 数据源等多选参数，转为逗号相接的序列
                params.set(key, value.join(','));
                return;
            }
            params.set(key, String(value));
        });

        const queryString = params.toString();
        return queryString ? `${url}?${queryString}` : url;
    }

    /**
     * 通用 Fetch 网络请求底层封装
     */
    async function request(endpoint, options = {}) {
        const {
            query,          // 查询参数字典
            baseUrl,        // 针对重定向等特需的接口前缀
            unwrap = true,  // 是否自动执行响应解包
            headers,
            body,
            ...fetchOptions
        } = options || {};

        const requestHeaders = { ...(headers || {}) };
        let requestBody = body;

        // 如果 body 为非表单数据的常规 JavaScript 对象，自动格式化并补全 Content-Type
        if (body !== undefined && body !== null && typeof body === 'object' && !(body instanceof FormData)) {
            requestHeaders['Content-Type'] = requestHeaders['Content-Type'] || 'application/json';
            requestBody = JSON.stringify(body);
        }

        const response = await fetch(buildUrl(endpoint, query, baseUrl), {
            ...fetchOptions,
            headers: requestHeaders,
            body: requestBody,
        });

        let payload = null;
        const contentType = response.headers && response.headers.get('content-type');
        
        // 解析响应内容
        if (contentType && contentType.includes('application/json')) {
            payload = await response.json();
        } else {
            const text = await response.text();
            payload = text ? { message: text } : null;
        }

        // 统一异常拦截处理
        if (!response.ok) {
            const error = new Error(payload?.error || payload?.message || `API Error: ${response.status} ${response.statusText}`);
            error.status = response.status;
            error.payload = payload;
            throw error;
        }

        return unwrap ? unwrapApiResponse(payload) : payload;
    }

    // 绑定至全局
    window.DisasterApiClient = {
        API_BASE,
        request,
        buildUrl,
        unwrapApiResponse,
    };
})();
