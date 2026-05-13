/**
 * API 请求 Hook
 * 封装了所有与后端 REST API 交互的方法
 */
function useApi() {
    const API_BASE = '/api';

    const unwrapApiResponse = (payload) => {
        if (payload && typeof payload === 'object' && payload.success === true && payload.data !== undefined) {
            return payload.data;
        }
        return payload;
    };

    // 通用数据获取函数，处理错误和JSON解析
    const fetchData = async (endpoint, options = {}) => {
        const response = await fetch(`${API_BASE}${endpoint}`, options);
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload?.error || `API Error: ${response.statusText}`);
        }
        return unwrapApiResponse(payload);
    };

    const getStatus = () => fetchData('/status');
    const getStatistics = () => fetchData('/statistics');
    const getConnections = () => fetchData('/connections');
    const getConfigSchema = () => fetchData('/config-schema');
    const getFullConfig = () => fetchData('/full-config');

    const updateConfig = (config) => fetchData('/full-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
    });

    const sendSimulation = (data) => fetchData('/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });

    const getSimulationParams = () => fetchData('/simulation-params');

    const getGeoLocation = async () => fetchData('/geolocate');

    const getTrend = (hours = 24) => fetchData(`/trend?hours=${hours}`);
    const getHeatmap = (days = 180, year = null) => {
        let url = `/heatmap?days=${days}`;
        if (year) {
            url += `&year=${year}`;
        }
        return fetchData(url);
    };

    const resetStatistics = (password = '') => fetchData('/statistics/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
    });

    // 会话差异配置相关接口
    const listSessionConfigs = () => fetchData('/session-config/sessions');
    const getSessionConfig = (umo) => fetchData(`/session-config/${encodeURIComponent(umo)}`);
    const updateSessionConfig = (umo, payload) => fetchData(`/session-config/${encodeURIComponent(umo)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const resetSessionConfig = (umo) => fetchData(`/session-config/${encodeURIComponent(umo)}`, {
        method: 'DELETE'
    });

    const getNotifications = () => fetchData('/notifications');
    const readNotification = (id) => fetchData('/notifications/read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
    });
    const readAllNotifications = () => fetchData('/notifications/read-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    });
    const refreshNotifications = () => fetchData('/notifications/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    });
    const listMarkdownFiles = () => fetchData('/markdown-files');
    const getMarkdownFile = (path) => fetchData(`/markdown-files/${encodeURIComponent(path)}`);

    return {
        getStatus,
        getStatistics,
        getConnections,
        getConfigSchema,
        getFullConfig,
        updateConfig,
        sendSimulation,
        getSimulationParams,
        getGeoLocation,
        getTrend,
        getHeatmap,
        resetStatistics,
        listSessionConfigs,
        getSessionConfig,
        updateSessionConfig,
        resetSessionConfig,
        getNotifications,
        readNotification,
        readAllNotifications,
        refreshNotifications,
        listMarkdownFiles,
        getMarkdownFile
    };
}
