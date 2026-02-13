const { useEffect, useRef } = React;

function useWebSocket() {
    const { state, dispatch } = useAppContext();
    const wsRef = useRef(null);
    const reconnectTimerRef = useRef(null);

    const getWsUrl = () => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws`;
    };

    const handleWsMessage = (msg) => {
        if (msg.type === 'full_update' || msg.type === 'update' || msg.type === 'event') {
            const data = msg.data;

            // 如果消息没有携带 data,提前返回(例如仅包含 new_event 的 event 消息)
            if (!data) {
                if (msg.type === 'event' && msg.new_event) {
                    console.log('[WS] 收到新事件:', msg.new_event);
                }
                return;
            }

            // 更新状态
            if (data.status) {
                const statusUpdate = {
                    running: data.status.running,
                    activeConnections: data.status.active_connections,
                    totalConnections: data.status.total_connections,
                    // 确保 version 被正确提取，如果为空则保留原值或使用默认值
                    version: data.status.version || state.status.version
                };

                if (data.status.start_time) {
                    statusUpdate.startTime = new Date(data.status.start_time);
                } else if (data.status.uptime) {
                    statusUpdate.uptime = data.status.uptime;
                }

                dispatch({ type: 'UPDATE_STATUS', payload: statusUpdate });
            }

            // 更新统计
            if (data.statistics) {
                dispatch({ type: 'UPDATE_STATS', payload: data.statistics });
            }

            // 更新连接状态
            if (data.connections) {
                dispatch({ type: 'UPDATE_CONNECTIONS', payload: data.connections });
            }

            // 如果是事件驱动的更新
            if (msg.type === 'event' && msg.new_event) {
                console.log('[WS] 收到新事件:', msg.new_event);
                dispatch({ type: 'ADD_EVENT', payload: msg.new_event });
            }
        } else if (msg.type === 'pong') {
            // 心跳响应
        }
    };

    const scheduleReconnect = () => {
        if (reconnectTimerRef.current) return;
        reconnectTimerRef.current = setTimeout(() => {
            reconnectTimerRef.current = null;
            // 检查组件是否已卸载
            if (!wsRef.current && state.wsConnected === undefined) return;
            console.log('[WS] 尝试重连...');
            connect();
        }, 3000);
    };

    const connect = () => {
        // 如果已经有连接且是开启状态，不重复连接
        if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
            return;
        }

        try {
            // 关闭旧连接
            if (wsRef.current) {
                // 移除旧的监听器防止干扰
                wsRef.current.onclose = null;
                wsRef.current.close();
            }

            wsRef.current = new WebSocket(getWsUrl());

            wsRef.current.onopen = () => {
                console.log('[WS] 已连接');
                dispatch({ type: 'SET_WS_CONNECTED', payload: true });
                if (reconnectTimerRef.current) {
                    clearTimeout(reconnectTimerRef.current);
                    reconnectTimerRef.current = null;
                }
            };

            wsRef.current.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    handleWsMessage(msg);
                } catch (e) {
                    console.error('[WS] 解析消息失败', e);
                }
            };

            wsRef.current.onclose = () => {
                console.log('[WS] 连接已关闭');
                // 只有当组件仍挂载时才更新状态
                if (wsRef.current) {
                    dispatch({ type: 'SET_WS_CONNECTED', payload: false });
                    scheduleReconnect();
                }
            };

            wsRef.current.onerror = (error) => {
                console.error('[WS] 连接错误', error);
                // 这里不需要重置状态，onclose 会被触发
            };
        } catch (e) {
            console.error('[WS] 创建连接失败', e);
            scheduleReconnect();
        }
    };

    // 使用 ref 跟踪是否是挂载状态，避免严格模式下的重复连接
    const isMounted = useRef(false);

    useEffect(() => {
        isMounted.current = true;
        
        // 只有当没有连接时才初始化连接
        if (!wsRef.current) {
            connect();
        }

        // 注意：这里我们不再在 cleanup 中直接关闭连接
        // 而是将 WebSocket 实例保持在 Context 或全局单例中会更好
        // 但为了最小化改动，我们采用引用计数或全局检测的方式
        
        return () => {
            isMounted.current = false;
            // 组件卸载时不关闭连接，让它在后台保持
            // 只有当页面完全刷新或关闭时连接才会断开
            // 这解决了 React 严格模式下重复挂载导致连接断开重连的问题
            
            // 如果确实需要清理，应该确保清理逻辑正确
            // if (wsRef.current) {
            //    wsRef.current.onclose = null; // 防止触发重连
            //    wsRef.current.close();
            //    wsRef.current = null;
            // }
        };
    }, []);

    const sendMessage = (msg) => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(msg));
        }
    };

    return {
        wsConnected: state.wsConnected,
        events: state.events, // 导出 events 状态供组件使用
        sendMessage
    };
}
