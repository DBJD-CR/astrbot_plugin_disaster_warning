(() => {
    /**
     * 管理控制台与后端的双向长连接通信客户端类。
     * 
     * 核心技术细节与架构：
     * 1. 订阅者中心 (Set Listeners)：采用发布订阅模式，维护一个监听器集合。多个前台组件
     *    可同时订阅同一个长连接实例，在连接就绪、断开或有新消息广播时同步触发回调。
     * 2. 退避式自动重连 (Exponential Backoff Reconnect)：当检测到因网络闪断、宿主热重载
     *    或物理断网引起的关闭时，自动启动重连定时器。
     *    重连延迟时间采用指数级增长递增算法：重连间隔 = 基础重连延迟 * (2 ^ 尝试次数)，上限封顶为 30 秒，
     *    以防止网络故障时高频请求挤满服务器连接通道。
     * 3. 双向握手状态维护：在最后一个前台组件卸载或注销订阅时，主动向后端发送断开指令，
     *    并彻底清除内存中的重连定时器，节约浏览器 CPU 与物理内存占用。
     */
    let wsInstance = null;         // 长连接 WebSocket 单例实例
    let reconnectTimer = null;     // 重连定时器句柄
    let reconnectAttempt = 0;      // 连续尝试重连次数计数器
    const listeners = new Set();   // 注册的活跃组件订阅者集合
    const BASE_RECONNECT_DELAY = 3000;  // 基础延迟：3秒
    const MAX_RECONNECT_DELAY = 30000;  // 重连间隔上限：30秒

    /**
     * 拼装带有鉴权参数的 WebSocket 物理连接地址
     */
    function getWsUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const token = window.AuthUtil && window.AuthUtil.getToken();
        const tokenParam = (token && token !== 'no-auth') ? `?token=${encodeURIComponent(token)}` : '';
        return `${protocol}//${window.location.host}/ws${tokenParam}`;
    }

    function notifyConnected() {
        listeners.forEach((listener) => listener.onConnected && listener.onConnected());
    }

    function notifyDisconnected() {
        listeners.forEach((listener) => listener.onDisconnected && listener.onDisconnected());
    }

    function notifyMessage(message) {
        listeners.forEach((listener) => listener.onMessage && listener.onMessage(message));
    }

    /**
     * 自动指数退避重连算法实现
     */
    function scheduleReconnect() {
        if (reconnectTimer) return;
        
        // 计算当前重连间隔，防止重连频次过高产生雪崩效应
        const delay = Math.min(MAX_RECONNECT_DELAY, BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempt));
        reconnectAttempt += 1;
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            if (listeners.size === 0) return;
            console.log(`[WS] 尝试重连，delay=${delay}ms attempt=${reconnectAttempt}`);
            connect();
        }, delay);
    }

    function clearReconnectTimer() {
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
    }

    /**
     * 建立长连接的物理通道
     */
    function connect() {
        // 若当前连接已就绪或处于连接建立中，不进行重复连接
        if (wsInstance && (wsInstance.readyState === WebSocket.OPEN || wsInstance.readyState === WebSocket.CONNECTING)) {
            console.log('[WS] 全局连接已存在，复用现有连接');
            return;
        }

        try {
            if (wsInstance) {
                wsInstance.onclose = null;
                wsInstance.close();
            }

            wsInstance = new WebSocket(getWsUrl());
            wsInstance.onopen = () => {
                console.log('[WS] 全局单例连接已建立');
                reconnectAttempt = 0;
                clearReconnectTimer();
                notifyConnected();
            };
            wsInstance.onmessage = (event) => {
                try {
                    notifyMessage(JSON.parse(event.data));
                } catch (e) {
                    console.error('[WS] 解析消息失败', e);
                }
            };
            wsInstance.onclose = () => {
                console.log('[WS] 全局连接已关闭');
                notifyDisconnected();
                // 只有在仍有组件处于订阅状态时，才触发自动重连机制
                if (listeners.size > 0) scheduleReconnect();
            };
            wsInstance.onerror = (error) => {
                console.error('[WS] 连接错误', error);
            };
        } catch (e) {
            console.error('[WS] 创建连接失败', e);
            scheduleReconnect();
        }
    }

    /**
     * 前台组件注册订阅监听的入口方法
     */
    function subscribe(listener) {
        listeners.add(listener);
        console.log(`[WS] 注册监听器，当前监听器数: ${listeners.size}`);
        
        if (!wsInstance || wsInstance.readyState === WebSocket.CLOSED) {
            connect();
        } else if (wsInstance.readyState === WebSocket.OPEN && listener.onConnected) {
            listener.onConnected();
        }
        
        // 返回取消订阅的回调闭包，用于在组件销毁时实现自动注销
        return () => {
            listeners.delete(listener);
            console.log(`[WS] 移除监听器，剩余监听器数: ${listeners.size}`);
            
            // 如果所有组件全部注销，则主动切断 WebSocket 物理连接，释放网络端口
            if (listeners.size === 0) {
                clearReconnectTimer();
                reconnectAttempt = 0;
                if (wsInstance) {
                    console.log('[WS] 所有监听器已移除，关闭全局连接');
                    wsInstance.onclose = null;
                    wsInstance.close();
                    wsInstance = null;
                }
            }
        };
    }

    /**
     * 发送自定义长连接消息的方法
     */
    function send(message) {
        if (wsInstance && wsInstance.readyState === WebSocket.OPEN) {
            wsInstance.send(JSON.stringify(message));
            return true;
        }
        return false;
    }

    window.WebSocketClient = { subscribe, send, connect };
})();
