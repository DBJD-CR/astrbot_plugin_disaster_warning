const { useEffect, useRef, useCallback } = React;

// ========== 全局单例 WebSocket 实例 ==========
// 确保整个应用只有一个 WebSocket 连接
let globalWsInstance = null;
let globalReconnectTimer = null;
let connectionListeners = new Set(); // 存储所有订阅者

function useWebSocket() {
    const { state, dispatch } = useAppContext();
    const listenerIdRef = useRef(null);
    const handleWsMessageRef = useRef(null);

    // 使用 useRef 存储最新的消息处理函数，避免重复注册监听器
    handleWsMessageRef.current = (msg) => {
        if (msg.type === 'full_update' || msg.type === 'update' || msg.type === 'event') {
            const data = msg.data;

            // 优先处理 new_event（即使没有 data 也需要 dispatch）
            if (msg.type === 'event' && msg.new_event) {
                console.log('[WS] 收到新事件:', msg.new_event);
                dispatch({ type: 'ADD_EVENT', payload: msg.new_event });
            }

            // 如果消息没有携带 data，不再继续处理状态更新
            if (!data) {
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

        } else if (msg.type === 'pong') {
            // 心跳响应
        }
    };

    const getWsUrl = () => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const token = window.AuthUtil && window.AuthUtil.getToken();
        const tokenParam = (token && token !== 'no-auth') ? `?token=${encodeURIComponent(token)}` : '';
        return `${protocol}//${window.location.host}/ws${tokenParam}`;
    };

    const scheduleReconnect = () => {
        if (globalReconnectTimer) return;
        globalReconnectTimer = setTimeout(() => {
            globalReconnectTimer = null;
            // 检查是否还有活跃的监听器
            if (connectionListeners.size === 0) return;
            console.log('[WS] 尝试重连...');
            connect();
        }, 3000);
    };

    const connect = () => {
        // 如果已经有连接且是开启状态，不重复连接
        if (globalWsInstance && (globalWsInstance.readyState === WebSocket.OPEN || globalWsInstance.readyState === WebSocket.CONNECTING)) {
            console.log('[WS] 全局连接已存在，复用现有连接');
            return;
        }

        try {
            // 关闭旧连接
            if (globalWsInstance) {
                // 移除旧的监听器防止干扰
                globalWsInstance.onclose = null;
                globalWsInstance.close();
            }

            globalWsInstance = new WebSocket(getWsUrl());

            globalWsInstance.onopen = () => {
                console.log('[WS] 全局单例连接已建立');
                // 通知所有订阅者连接已建立
                connectionListeners.forEach(listener => {
                    if (listener.onConnected) listener.onConnected();
                });
                if (globalReconnectTimer) {
                    clearTimeout(globalReconnectTimer);
                    globalReconnectTimer = null;
                }
            };

            globalWsInstance.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    // 广播给所有订阅者
                    connectionListeners.forEach(listener => {
                        if (listener.onMessage) listener.onMessage(msg);
                    });
                } catch (e) {
                    console.error('[WS] 解析消息失败', e);
                }
            };

            globalWsInstance.onclose = () => {
                console.log('[WS] 全局连接已关闭');
                // 通知所有订阅者连接已关闭
                connectionListeners.forEach(listener => {
                    if (listener.onDisconnected) listener.onDisconnected();
                });
                // 只有当还有订阅者时才重连
                if (connectionListeners.size > 0) {
                    scheduleReconnect();
                }
            };

            globalWsInstance.onerror = (error) => {
                console.error('[WS] 连接错误', error);
                // 这里不需要重置状态，onclose 会被触发
            };
        } catch (e) {
            console.error('[WS] 创建连接失败', e);
            scheduleReconnect();
        }
    };

    useEffect(() => {
        // 生成唯一的监听器 ID
        const listenerId = Math.random().toString(36).substr(2, 9);
        listenerIdRef.current = listenerId;
        
        // 创建监听器对象
        const listener = {
            onConnected: () => {
                dispatch({ type: 'SET_WS_CONNECTED', payload: true });
            },
            onDisconnected: () => {
                dispatch({ type: 'SET_WS_CONNECTED', payload: false });
            },
            onMessage: (msg) => {
                handleWsMessageRef.current(msg);
            }
        };
        
        // 注册监听器
        connectionListeners.add(listener);
        console.log(`[WS] 注册监听器 ${listenerId}，当前监听器数: ${connectionListeners.size}`);
        
        // 首次调用或连接不存在时，初始化连接
        if (!globalWsInstance || globalWsInstance.readyState === WebSocket.CLOSED) {
            connect();
        } else if (globalWsInstance.readyState === WebSocket.OPEN) {
            // 如果已经连接，立即通知新监听器
            dispatch({ type: 'SET_WS_CONNECTED', payload: true });
        }
        
        return () => {
            // 移除监听器
            connectionListeners.delete(listener);
            console.log(`[WS] 移除监听器 ${listenerId}，剩余监听器数: ${connectionListeners.size}`);
            
            // 如果没有监听器了，清理重连定时器并关闭连接
            if (connectionListeners.size === 0) {
                if (globalReconnectTimer) {
                    clearTimeout(globalReconnectTimer);
                    globalReconnectTimer = null;
                }
                if (globalWsInstance) {
                    console.log('[WS] 所有监听器已移除，关闭全局连接');
                    globalWsInstance.onclose = null; // 移除 onclose 处理器防止触发重连
                    globalWsInstance.close();
                    globalWsInstance = null;
                }
            }
        };
    }, [dispatch]); // 只依赖 dispatch，不依赖 handleWsMessage

    const sendMessage = (msg) => {
        if (globalWsInstance && globalWsInstance.readyState === WebSocket.OPEN) {
            globalWsInstance.send(JSON.stringify(msg));
            return true; // 发送成功
        }
        return false; // 发送失败
    };

    return {
        wsConnected: state.wsConnected,
        events: state.events, // 导出 events 状态供组件使用
        sendMessage
    };
}
