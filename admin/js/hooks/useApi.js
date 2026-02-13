/**
 * API 请求 Hook
 * 封装了所有与后端 REST API 交互的方法
 */
function useApi() {
    const API_BASE = '/api';

    // 通用数据获取函数，处理错误和JSON解析
    const fetchData = async (endpoint, options = {}) => {
        const response = await fetch(`${API_BASE}${endpoint}`, options);
        if (!response.ok) {
            throw new Error(`API Error: ${response.statusText}`);
        }
        return response.json();
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
        getHeatmap
    };
}
