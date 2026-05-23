(() => {
/**
 * 模块名称：通知中心视图组件
 * 功能描述：通知中心主界面，负责从服务端拉取插件发布的事件更新、
 *          BUG修复及公告通知。提供未读通知高亮显示、行内确认已读以及一键全部已读等功能，
 *          同时内置了 Markdown 语法的编译器支持。
 */

const { Box, Typography, Button, Chip } = MaterialUI;

// 配置不同的通知类型所匹配的文字标签与 UI 视觉配色色调
const NOTIFICATION_TYPE_META = {
    UPDATE: { label: '更新通知', color: 'info' },
    BUGFIX: { label: '修复通知', color: 'success' },
    NOTICE: { label: '公告通知', color: 'warning' },
    SECURITY: { label: '安全通知', color: 'error' },
    TEST: { label: '测试通知', color: 'default' },
};

// 预警通知类型的简称/别名到标准化键值的映射转换字典
const NOTIFICATION_TYPE_ALIASES = {
    INFO: 'NOTICE',
};

/**
 * 依据类型标识转换出结构化的标签配色方案
 * @param {string} type 原始通知类型字串
 * @returns {object} 匹配到的样式和标签元数据配置
 */
function resolveNotificationTypeMeta(type) {
    const normalizedType = String(type || '').trim().toUpperCase();
    const canonicalType = NOTIFICATION_TYPE_ALIASES[normalizedType] || normalizedType;
    return NOTIFICATION_TYPE_META[canonicalType] || { label: '其他通知', color: 'default' };
}

/**
 * 编译并渲染通知的核心正文内容
 * 支持自动探测和解析 Markdown 语法元素
 * @param {object} item 通知数据对象
 */
function renderNotificationContent(item) {
    const markdownUtil = window.MarkdownRenderUtil;
    // 规范化通知内容，处理首尾换行符或占位符
    const content = markdownUtil
        ? markdownUtil.normalizeMarkdownContent(item?.content || '--')
        : String(item?.content || '--').replace(/\\n/g, '\n');
    const format = String(item?.content_format || 'text').trim().toLowerCase();
    
    // 如果格式声明为 markdown 或文本格式经正则校验极有可能是 markdown，则采用渲染器处理
    const shouldRenderMarkdown = Boolean(markdownUtil) && (format === 'markdown' || markdownUtil.isProbablyMarkdown(content));

    if (!shouldRenderMarkdown) {
        // 对于纯文本，保留多行换行样式直接渲染
        return (
            <Typography variant="body2" className="notification-feed-content-text notification-feed-content-text-plain notification-feed-content-text--multiline">
                {content}
            </Typography>
        );
    }

    // 渲染带有语法着色的高解析度 HTML 正文
    return (
        <Box
            className="notification-feed-content-text notification-md"
            dangerouslySetInnerHTML={{ __html: markdownUtil.renderMarkdownToHtml(content) }}
        />
    );
}

/**
 * 通知中心主视图组件
 * @param {object} props 接收父级透传的回调方法
 */
function NotificationsView({ onRefresh }) {
    // 订阅 Context 状态管理中心
    const { state, dispatch, refreshData } = useAppContext();
    const notificationApi = window.DisasterNotificationApi;
    
    // 安全提取通知的列表和全局元数据统计对象
    const notifications = Array.isArray(state.notifications) ? state.notifications : [];
    const notificationsMeta = state.notificationsMeta || { unread_count: 0, last_sync_at: '', total_count: 0 };
    
    // 获取系统的全局展示时区配置，格式化通知的本地显示时间
    const displayTimezone = state.config?.displayTimezone || 'UTC+8';
    const formatNotificationTime = (value) => formatTimeWithZone(value, displayTimezone, true);
    
    // 按钮提交的加载防抖锁状态，用于标识哪个按钮在执行操作，防止网络重复响应
    const [busyAction, setBusyAction] = React.useState('');

    // 向后端请求最新的云端同步数据
    const refreshFromServer = async () => {
        setBusyAction('refresh');
        try {
            const payload = await notificationApi.refreshNotifications();
            // 写入本地全局 Reducer 状态库
            dispatch({ type: 'SET_NOTIFICATIONS', payload: payload.items || [] });
            dispatch({ type: 'SET_NOTIFICATIONS_META', payload: payload.meta || null });
            
            // 协同调用传入或上下文的重载同步回调
            if (typeof onRefresh === 'function') {
                await onRefresh();
            } else if (typeof refreshData === 'function') {
                await refreshData();
            }
        } catch (e) {
            console.error(e);
        } finally {
            setBusyAction('');
        }
    };

    // 单条通知的设为已读处理
    const markOneAsRead = async (id) => {
        setBusyAction(`read-${id}`);
        try {
            const payload = await notificationApi.readNotification(id);
            // 更新全局未读总数元数据
            dispatch({ type: 'SET_NOTIFICATIONS_META', payload: payload.meta || null });
            // 乐观更新：将本地列表中匹配的 ID 记录标为已读，避免多余的再次全量 fetch
            dispatch({
                type: 'SET_NOTIFICATIONS',
                payload: notifications.map((item) => Number(item.id) === Number(id) ? { ...item, _read: true } : item),
            });
        } catch (e) {
            console.error(e);
        } finally {
            setBusyAction('');
        }
    };

    // 一键标记所有通知为已读
    const markAllAsRead = async () => {
        setBusyAction('read-all');
        try {
            const payload = await notificationApi.readAllNotifications();
            dispatch({ type: 'SET_NOTIFICATIONS_META', payload: payload.meta || null });
            // 本地全量标为已读
            dispatch({ type: 'SET_NOTIFICATIONS', payload: notifications.map((item) => ({ ...item, _read: true })) });
        } catch (e) {
            console.error(e);
        } finally {
            setBusyAction('');
        }
    };

    // 挂载时拉取初始化数据库已缓存的通知列表
    React.useEffect(() => {
        notificationApi.getNotifications()
            .then((payload) => {
                dispatch({ type: 'SET_NOTIFICATIONS', payload: payload.items || [] });
                dispatch({ type: 'SET_NOTIFICATIONS_META', payload: payload.meta || null });
            })
            .catch((e) => console.error('Failed to load notifications:', e));
    }, []);

    return (
        <Box className="notifications-view">
            {/* 顶层英雄式背景横幅卡片，提供明晰的数据看板 */}
            <div className="card notifications-hero-card">
                <Box className="notifications-header-row">
                    {/* 左侧文字与元数据指示区 */}
                    <div className="notifications-header-main">
                        <Box className="notifications-title-row">
                            <Box className="notifications-title-stack">
                                <Typography variant="h6" className="notifications-title-text">
                                    {`通知中心 (当前共 ${notificationsMeta.total_count || notifications.length} 条通知)`}
                                </Typography>
                                {/* 状态指示徽章，根据是否有未读消息自适应切换警告色/安全色 */}
                                <Chip
                                    label={Number(notificationsMeta.unread_count ?? 0) > 0 ? `未读 ${Number(notificationsMeta.unread_count ?? 0)} 条` : '全部已读'}
                                    size="small"
                                    color={Number(notificationsMeta.unread_count ?? 0) > 0 ? 'warning' : 'success'}
                                    variant="outlined"
                                />
                            </Box>
                            <div className="notifications-inline-meta">
                                <div className="notifications-inline-meta-item is-pill">
                                    <span className="notifications-inline-meta-label">未读通知</span>
                                    <strong>{Number(notificationsMeta.unread_count ?? 0)}</strong>
                                </div>
                                <div className="notifications-inline-meta-item is-pill">
                                    <span className="notifications-inline-meta-label">上次同步</span>
                                    <strong>{notificationsMeta.last_sync_at ? formatNotificationTime(notificationsMeta.last_sync_at) : '--'}</strong>
                                </div>
                            </div>
                        </Box>
                        <Typography variant="body2" color="text.secondary" className="notifications-hero-subtitle">
                            用于接收插件更新、修复说明、注意事项等官方通知。
                        </Typography>
                    </div>
                    {/* 右侧动作控制区 */}
                    <Box className="notifications-actions-row">
                        <Button variant="outlined" onClick={markAllAsRead} disabled={busyAction === 'read-all' || notifications.length === 0} className="notifications-action-btn">
                            全部已读
                        </Button>
                        <Button variant="contained" onClick={refreshFromServer} disabled={busyAction === 'refresh'} startIcon={<span>🔄</span>} className="notifications-action-btn notifications-action-btn--primary">
                            立即同步
                        </Button>
                    </Box>
                </Box>
            </div>

            {/* 当无通知记录时展示空白占位 */}
            {notifications.length === 0 ? (
                <div className="card notifications-empty-card">
                    <div className="notifications-empty-icon">🔔</div>
                    <Typography variant="h6" className="notifications-empty-title">暂无通知</Typography>
                    <Typography variant="body1" color="text.secondary" className="notifications-empty-subtitle">当前还没有可展示的系统通知。</Typography>
                </div>
            ) : (
                // 渲染通知提交流卡片列表
                <div className="notifications-feed-list">
                    {notifications.map((item) => {
                        const meta = resolveNotificationTypeMeta(item.type);
                        const isRead = Boolean(item._read) || false;
                        return (
                            // 根据是否已读，在卡片样式上分别打上 "已读阴影变淡" 或 "未读高亮左侧警告条" 标签
                            <div className={`card notification-feed-card ${isRead ? 'is-read' : 'is-urgent'}`} key={item.id}>
                                <div className="notification-feed-card-top">
                                    <div className="notification-feed-heading-group">
                                        <Typography variant="body1" className="notification-feed-title">{item.title || '--'}</Typography>
                                        <Chip className="notification-feed-type-chip" label={meta.label} size="small" color={meta.color} variant="outlined" />
                                    </div>
                                    <div className="notification-feed-side notification-feed-meta-inline">
                                        {/* 行内未读状态红点小药丸指示器 */}
                                        <span className={`notification-feed-status-pill ${isRead ? 'is-read' : 'is-unread'}`}>{isRead ? '已读' : '未读'}</span>
                                        <Typography variant="caption" className="mono notification-feed-time">
                                            {formatNotificationTime(item.created_at)}
                                        </Typography>
                                    </div>
                                </div>
                                <div className="notification-feed-content-panel">
                                    {/* 渲染转换后的内容体 */}
                                    {renderNotificationContent(item)}
                                    {/* 行内确认动作栏 */}
                                    <Box className="notification-feed-actions notification-feed-actions-inside">
                                        <Button variant="outlined" size="small" disabled={isRead || busyAction === `read-${item.id}`} onClick={() => markOneAsRead(item.id)} className="notifications-inline-btn">
                                            {isRead ? '已读' : '确认已读'}
                                        </Button>
                                    </Box>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </Box>
    );
}

window.NotificationsView = NotificationsView;
})();
