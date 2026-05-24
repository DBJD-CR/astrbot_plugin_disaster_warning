(() => {
    /**
     * 通知中心与文档浏览页面的接口定义类。
     * 
     * 主要方法：
     * - getNotifications: 异步拉取后台累计的消息通知。
     * - readNotification: 将指定的某条通知标记为已读。
     * - readAllNotifications: 一键清空并将所有通知置为已读。
     * - refreshNotifications: 手动触发后端拉取和整理最新未读通知。
     * - listMarkdownFiles: 拉取本地离线帮助文档路径的注册列表。
     * - getMarkdownFile: 根据相对路径获取某篇具体说明书的 Markdown 文本内容。
     */
    const client = window.DisasterApiClient;

    const notificationApi = {
        getNotifications: () => client.request('/notifications'),
        readNotification: (id) => client.request('/notifications/read', {
            method: 'POST',
            body: { id },
        }),
        readAllNotifications: () => client.request('/notifications/read-all', {
            method: 'POST',
            body: {},
        }),
        refreshNotifications: () => client.request('/notifications/refresh', {
            method: 'POST',
            body: {},
        }),
        listMarkdownFiles: () => client.request('/markdown-files'),
        getMarkdownFile: (path) => client.request(`/markdown-files/${encodeURIComponent(path)}`),
    };

    window.DisasterNotificationApi = notificationApi;
})();
