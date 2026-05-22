(() => {
    /**
     * 配置管理模块的接口定义类。
     * 
     * 主要方法：
     * - getConfigSchema: 获取表单中每个项的中文说明、控件类型、默认值及折叠嵌套路径信息。
     * - getFullConfig: 获取全局配置参数。
     * - updateConfig: 全量更新并保存全局配置。
     * - listSessionConfigs: 拉取所有配置了覆盖参数的群组列表。
     * - getSessionConfig: 拉取特定群组的覆盖配置详情。
     * - updateSessionConfig: 保存特定群组的覆盖配置。
     * - resetSessionConfig: 一键删除特定群组的覆盖配置，回归继承全局。
     */
    const client = window.DisasterApiClient;

    const configApi = {
        getConfigSchema: () => client.request('/config-schema'),
        getFullConfig: () => client.request('/full-config'),
        updateConfig: (config) => client.request('/full-config', {
            method: 'POST',
            body: config,
        }),
        listSessionConfigs: () => client.request('/session-config/sessions'),
        getSessionConfig: (umo) => client.request(`/session-config/${encodeURIComponent(umo)}`),
        updateSessionConfig: (umo, payload) => client.request(`/session-config/${encodeURIComponent(umo)}`, {
            method: 'POST',
            body: payload,
        }),
        resetSessionConfig: (umo) => client.request(`/session-config/${encodeURIComponent(umo)}`, {
            method: 'DELETE',
        }),
    };

    window.DisasterConfigApi = configApi;
})();
