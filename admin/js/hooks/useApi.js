function useApi() {
    const API_BASE = '/api';

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

    return {
        getStatus,
        getStatistics,
        getConnections,
        getConfigSchema,
        getFullConfig,
        updateConfig,
        sendSimulation,
        getSimulationParams,
        getGeoLocation
    };
}
