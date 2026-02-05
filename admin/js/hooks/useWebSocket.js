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
                    totalConnections: data.status.total_connections
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
            }
        } else if (msg.type === 'pong') {
            // 心跳响应
        }
    };

    const scheduleReconnect = () => {
        if (reconnectTimerRef.current) return;
        reconnectTimerRef.current = setTimeout(() => {
            reconnectTimerRef.current = null;
            console.log('[WS] 尝试重连...');
            connect();
        }, 3000);
    };

    const connect = () => {
        try {
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
                dispatch({ type: 'SET_WS_CONNECTED', payload: false });
                scheduleReconnect();
            };

            wsRef.current.onerror = (error) => {
                console.error('[WS] 连接错误', error);
                dispatch({ type: 'SET_WS_CONNECTED', payload: false });
            };
        } catch (e) {
            console.error('[WS] 创建连接失败', e);
            scheduleReconnect();
        }
    };

    useEffect(() => {
        connect();

        return () => {
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = null;
            }
        };
    }, []);

    const sendMessage = (msg) => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(msg));
        }
    };

    return { wsConnected: state.wsConnected, sendMessage };
}
