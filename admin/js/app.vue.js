/**
 * 灾害预警管理端 - Vue 3 版本
 */

const { createApp, ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } = Vue;

// API 基础路径
const API_BASE = '/api';

// 工具函数
const formatTime = (isoString) => {
    if (!isoString) return '--';
    const date = new Date(isoString);
    return date.toLocaleString('zh-CN');
};

const formatTimeFriendly = (isoString) => {
    if (!isoString) return '--';
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return '刚刚';
    if (diffMins < 60) return `${diffMins}分钟前`;

    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    const hours = date.getHours().toString().padStart(2, '0');
    const mins = date.getMinutes().toString().padStart(2, '0');
    return `${month}-${day} ${hours}:${mins}`;
};

const getMagColorClass = (mag) => {
    if (mag >= 7) return 'mag-high';
    if (mag >= 5) return 'mag-medium';
    return 'mag-low';
};

const getMagnitudeColor = (mag) => {
    if (mag >= 7) return '#ef4444';
    if (mag >= 5) return '#f97316';
    if (mag >= 3) return '#eab308';
    return '#3b82f6';
};

const getWeatherColorClass = (description) => {
    if (!description) return 'weather-blue';
    if (description.includes('红色')) return 'weather-red';
    if (description.includes('橙色')) return 'weather-orange';
    if (description.includes('黄色')) return 'weather-yellow';
    return 'weather-blue'; // Default to blue/info
};

// Vue App
const app = createApp({
    setup() {
        // ========== 响应式状态 ==========
        const status = reactive({
            running: false,
            uptime: '--',
            startTime: null,
            activeConnections: '--',
            totalConnections: '--'
        });

        const stats = reactive({
            totalEvents: 0,
            earthquakeCount: 0,
            tsunamiCount: 0,
            weatherCount: 0
        });

        const connections = ref({});
        const recentEvents = ref([]);
        const earthquakes = ref([]);
        const magnitudeDistribution = ref({});
        const lastUpdate = ref('--');

        // WebSocket
        let ws = null;
        let wsReconnectTimer = null;
        let uptimeTimer = null;
        const wsConnected = ref(false);

        // Settings Modal
        const showSettings = ref(false);
        const schema = ref(null);
        const fullConfig = ref(null);
        const settingsSaving = ref(false);

        // Simulation Modal
        const showSimulation = ref(false);
        const simulationOptions = ref(null);
        const simulationForm = reactive({
            targetGroup: '',
            disasterType: 'earthquake',
            testType: 'china',
            customParams: {
                magnitude: '',
                depth: '',
                latitude: '',
                longitude: '',
                place_name: '',
                intensity: '',
                scale: ''
            }
        });
        const simulationSending = ref(false);

        // Theme
        const isDarkTheme = ref(false);

        // Filter state
        const filterType = ref('all'); // 'all', 'earthquake', 'tsunami', 'weather'

        // Event grouping - track which event groups are expanded
        const expandedEvents = ref(new Set());

        // ========== 计算属性 ==========
        const sortedConnections = computed(() => {
            return Object.entries(connections.value).sort((a, b) => a[0].localeCompare(b[0]));
        });

        const sortedRecentEvents = computed(() => {
            return [...recentEvents.value].reverse();
        });

        // Filtered events based on selected type
        const filteredRecentEvents = computed(() => {
            if (filterType.value === 'all') {
                return recentEvents.value;
            }
            return recentEvents.value.filter(evt => {
                const type = evt.type || '';
                if (filterType.value === 'earthquake') {
                    return type === 'earthquake' || type === 'earthquake_warning';
                }
                if (filterType.value === 'tsunami') {
                    return type === 'tsunami';
                }
                if (filterType.value === 'weather') {
                    return type === 'weather_alarm';
                }
                return true;
            });
        });

        // Grouped events by ID - latest event as representative, with history
        const groupedEvents = computed(() => {
            const groups = {};
            const eventsToGroup = filteredRecentEvents.value;

            // Group events by ID
            for (const evt of eventsToGroup) {
                // Fix: 使用 event_id 作为主要分组依据 (后端字段名为 event_id)
                const eventId = evt.event_id || evt.id || `${evt.time}-${evt.description}`;
                if (!groups[eventId]) {
                    groups[eventId] = {
                        id: eventId,
                        events: [],
                        latestEvent: null
                    };
                }
                groups[eventId].events.push(evt);
            }

            // For each group, sort by time (newest first) and set latest
            for (const id in groups) {
                groups[id].events.sort((a, b) => new Date(b.time) - new Date(a.time));
                groups[id].latestEvent = groups[id].events[0];
                groups[id].updateCount = groups[id].events.length;
            }

            // Convert to array and sort by latest event time (newest first)
            return Object.values(groups).sort((a, b) =>
                new Date(b.latestEvent.time) - new Date(a.latestEvent.time)
            );
        });

        const magnitudeOrder = [
            "< M3.0", "M3.0 - M3.9", "M4.0 - M4.9", "M5.0 - M5.9", "M6.0 - M6.9", "M7.0 - M7.9", ">= M8.0"
        ];

        const maxMagnitudeValue = computed(() => {
            return Math.max(...Object.values(magnitudeDistribution.value), 1);
        });

        // Computed: current disaster type's formats
        const currentDisasterFormats = computed(() => {
            if (!simulationOptions.value || !simulationOptions.value.disaster_types) return [];
            const typeInfo = simulationOptions.value.disaster_types[simulationForm.disasterType];
            return typeInfo ? typeInfo.formats : [];
        });

        // ========== WebSocket 连接 ==========
        const getWsUrl = () => {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            return `${protocol}//${window.location.host}/ws`;
        };

        const connectWebSocket = () => {
            if (ws && ws.readyState === WebSocket.OPEN) return;

            try {
                ws = new WebSocket(getWsUrl());

                ws.onopen = () => {
                    console.log('[WS] 已连接');
                    wsConnected.value = true;
                    if (wsReconnectTimer) {
                        clearTimeout(wsReconnectTimer);
                        wsReconnectTimer = null;
                    }
                };

                ws.onmessage = (event) => {
                    try {
                        const msg = JSON.parse(event.data);
                        handleWsMessage(msg);
                    } catch (e) {
                        console.error('[WS] 解析消息失败', e);
                    }
                };

                ws.onclose = () => {
                    console.log('[WS] 连接已关闭');
                    wsConnected.value = false;
                    scheduleReconnect();
                };

                ws.onerror = (error) => {
                    console.error('[WS] 连接错误', error);
                    wsConnected.value = false;
                };
            } catch (e) {
                console.error('[WS] 创建连接失败', e);
                scheduleReconnect();
            }
        };

        const scheduleReconnect = () => {
            if (wsReconnectTimer) return;
            wsReconnectTimer = setTimeout(() => {
                wsReconnectTimer = null;
                console.log('[WS] 尝试重连...');
                connectWebSocket();
            }, 3000);
        };

        const handleWsMessage = (msg) => {
            if (msg.type === 'full_update' || msg.type === 'update' || msg.type === 'event') {
                const data = msg.data;

                // 更新状态
                if (data.status) {
                    status.running = data.status.running;
                    status.activeConnections = data.status.active_connections;
                    status.totalConnections = data.status.total_connections;
                    if (data.status.start_time) {
                        status.startTime = new Date(data.status.start_time);
                        startUptimeTimer();
                    } else {
                        status.uptime = data.status.uptime;
                    }
                }

                // 更新统计
                if (data.statistics) {
                    stats.totalEvents = data.statistics.total_events || 0;
                    stats.earthquakeCount = (data.statistics.by_type && data.statistics.by_type.earthquake) || 0;
                    stats.tsunamiCount = (data.statistics.by_type && data.statistics.by_type.tsunami) || 0;
                    stats.weatherCount = (data.statistics.by_type && data.statistics.by_type.weather_alarm) || 0;
                    recentEvents.value = data.statistics.recent_pushes || [];
                    if (data.statistics.earthquake_stats && data.statistics.earthquake_stats.by_magnitude) {
                        magnitudeDistribution.value = data.statistics.earthquake_stats.by_magnitude;
                    }
                }

                // 更新连接状态
                if (data.connections) {
                    connections.value = data.connections;
                }

                // 更新地震数据
                if (data.earthquakes && data.earthquakes.length > 0) {
                    earthquakes.value = data.earthquakes.map(eq => ({
                        id: eq.id,
                        lat: eq.latitude,
                        lng: eq.longitude,
                        magnitude: eq.magnitude || 0,
                        place: eq.place || '未知位置',
                        time: eq.time,
                        source: eq.source || ''
                    })).filter(eq => eq.lat != null && eq.lng != null);
                }

                // 更新时间戳
                lastUpdate.value = new Date().toLocaleString('zh-CN');

                // 如果是事件驱动的更新，在控制台记录
                if (msg.type === 'event' && msg.new_event) {
                    console.log('[WS] 收到新事件:', msg.new_event);
                }
            } else if (msg.type === 'pong') {
                // 心跳响应
            }
        };

        const sendWsMessage = (msg) => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify(msg));
            }
        };

        const refreshAll = async () => {
            // 优先使用 WebSocket 请求刷新
            if (ws && ws.readyState === WebSocket.OPEN) {
                sendWsMessage({ type: 'refresh' });
                return;
            }

            // WebSocket 未连接时，回退到 HTTP API 刷新
            console.log('[RefreshAll] WebSocket 未连接，使用 HTTP API 刷新');
            try {
                const [statusRes, statsRes, connsRes, earthquakesRes] = await Promise.all([
                    fetch(`${API_BASE}/status`),
                    fetch(`${API_BASE}/statistics`),
                    fetch(`${API_BASE}/connections`),
                    fetch(`${API_BASE}/earthquakes`)
                ]);

                const [statusData, statsData, connsData, earthquakesData] = await Promise.all([
                    statusRes.json(),
                    statsRes.json(),
                    connsRes.json(),
                    earthquakesRes.json()
                ]);

                // 更新状态
                if (statusData) {
                    status.running = statusData.running;
                    status.activeConnections = statusData.active_connections;
                    status.totalConnections = statusData.total_connections;
                    if (statusData.start_time) {
                        status.startTime = new Date(statusData.start_time);
                        startUptimeTimer();
                    } else {
                        status.uptime = statusData.uptime;
                    }
                }

                // 更新统计
                if (statsData) {
                    stats.totalEvents = statsData.total_events || 0;
                    stats.earthquakeCount = (statsData.by_type && statsData.by_type.earthquake) || 0;
                    stats.tsunamiCount = (statsData.by_type && statsData.by_type.tsunami) || 0;
                    stats.weatherCount = (statsData.by_type && statsData.by_type.weather_alarm) || 0;
                    recentEvents.value = statsData.recent_pushes || [];
                    if (statsData.earthquake_stats && statsData.earthquake_stats.by_magnitude) {
                        magnitudeDistribution.value = statsData.earthquake_stats.by_magnitude;
                    }
                }

                // 更新连接状态
                if (connsData && connsData.connections) {
                    connections.value = connsData.connections;
                }

                // 更新地震数据
                if (earthquakesData && earthquakesData.length > 0) {
                    earthquakes.value = earthquakesData.map(eq => ({
                        id: eq.id,
                        lat: eq.latitude,
                        lng: eq.longitude,
                        magnitude: eq.magnitude || 0,
                        place: eq.place || '未知位置',
                        time: eq.time,
                        source: eq.source || ''
                    })).filter(eq => eq.lat != null && eq.lng != null);
                }

                // 更新时间戳
                lastUpdate.value = new Date().toLocaleString('zh-CN');
                console.log('[RefreshAll] HTTP 刷新完成');
            } catch (e) {
                console.error('[RefreshAll] HTTP 刷新失败:', e);
                alert('刷新失败: ' + e.message);
            }
        };


        // ========== Theme ==========
        const initTheme = () => {
            const savedTheme = localStorage.getItem('theme');
            if (savedTheme === 'dark') {
                setTheme(true);
            } else if (savedTheme === 'light') {
                setTheme(false);
            } else {
                const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                setTheme(prefersDark);
            }
        };

        const toggleTheme = () => {
            setTheme(!isDarkTheme.value);
        };

        const setTheme = (isDark) => {
            isDarkTheme.value = isDark;
            if (isDark) {
                document.body.classList.add('dark-theme');
                localStorage.setItem('theme', 'dark');
            } else {
                document.body.classList.remove('dark-theme');
                localStorage.setItem('theme', 'light');
            }
        };

        // ========== Settings Modal ==========
        const openSettings = async () => {
            showSettings.value = true;
            if (!schema.value) {
                await loadSchemaAndConfig();
            }
        };

        const closeSettings = () => {
            showSettings.value = false;
        };

        const loadSchemaAndConfig = async () => {
            try {
                const [schemaRes, configRes] = await Promise.all([
                    fetch(`${API_BASE}/config-schema`),
                    fetch(`${API_BASE}/full-config`)
                ]);
                schema.value = await schemaRes.json();
                fullConfig.value = await configRes.json();
            } catch (e) {
                console.error('Failed to load settings:', e);
            }
        };


        const saveSettings = async () => {
            settingsSaving.value = true;
            try {
                // ConfigRenderer uses v-model binding directly to fullConfig.value
                // So we just need to send fullConfig.value back to the server.
                // We use JSON.parse(JSON.stringify()) to ensure we send a clean object without Vue proxies if needed,
                // mostly to matching the previous behavior of deep copying, though standard fetch handles proxies fine usually.
                // But for safety and consistency:
                const newConfig = JSON.parse(JSON.stringify(fullConfig.value));

                const res = await fetch(`${API_BASE}/full-config`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(newConfig)
                });
                const result = await res.json();

                if (result.success) {
                    alert('配置已保存，部分设置可能重启后生效');
                    closeSettings();
                    refreshAll();
                } else {
                    alert(`保存失败: ${result.error || result.message}`);
                }
            } catch (e) {
                console.error('Save failed', e);
                alert(`保存出错: ${e.message}`);
            } finally {
                settingsSaving.value = false;
            }
        };

        // ========== Test Push ==========
        const testPush = async (type) => {
            if (!confirm(`确定要测试发送一条${type}及测试消息到默认群吗？这将触发真实的群消息推送。`)) return;
            try {
                const res = await fetch(`${API_BASE}/test-push?disaster_type=${type}`, { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    alert(`测试成功：${data.message}`);
                } else {
                    alert(`测试失败：${data.message || data.error}`);
                }
            } catch (e) {
                alert('请求失败');
                console.error(e);
            }
        };

        // ========== Simulation Modal ==========
        const openSimulation = async () => {
            showSimulation.value = true;
            if (!simulationOptions.value) {
                await fetchSimulationOptions();
            }
        };

        const closeSimulation = () => {
            showSimulation.value = false;
        };

        const fetchSimulationOptions = async () => {
            try {
                const res = await fetch(`${API_BASE}/simulation-params`);
                const data = await res.json();
                simulationOptions.value = data;
                // Set default test type based on disaster type
                if (data.disaster_types && data.disaster_types[simulationForm.disasterType]) {
                    const formats = data.disaster_types[simulationForm.disasterType].formats;
                    if (formats && formats.length > 0) {
                        simulationForm.testType = formats[0].value;
                    }
                }
            } catch (e) {
                console.error('Failed to fetch simulation options:', e);
            }
        };

        const selectDisasterType = (type, info) => {
            simulationForm.disasterType = type;
            simulationForm.testType = info.formats[0]?.value || null;
            // Reset custom params when switching disaster types
            Object.keys(simulationForm.customParams).forEach(key => {
                simulationForm.customParams[key] = '';
            });
        };

        const sendSimulation = async () => {
            simulationSending.value = true;
            try {
                // Build request body
                const requestBody = {
                    target_group: simulationForm.targetGroup || '',
                    disaster_type: simulationForm.disasterType,
                    test_type: simulationForm.testType,
                    custom_params: {}
                };

                // Add non-empty custom params
                Object.entries(simulationForm.customParams).forEach(([key, value]) => {
                    if (value !== '' && value !== null && value !== undefined) {
                        requestBody.custom_params[key] = value;
                    }
                });

                const res = await fetch(`${API_BASE}/simulate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });
                const data = await res.json();

                if (data.success) {
                    alert(`✅ 测试成功：\n${data.message}`);
                    closeSimulation();
                } else {
                    alert(`❌ 测试失败：${data.message || data.error}`);
                }
            } catch (e) {
                alert('请求失败，请检查控制台');
                console.error(e);
            } finally {
                simulationSending.value = false;
            }
        };

        // Event group animation origins
        const eventOrigins = ref({});

        // ========== Event Group Toggle ==========
        const toggleEventGroup = (groupId, event) => {
            if (expandedEvents.value.has(groupId)) {
                expandedEvents.value.delete(groupId);
            } else {
                expandedEvents.value.add(groupId);
                if (event) {
                    const rect = event.currentTarget.getBoundingClientRect();
                    const x = event.clientX - rect.left;
                    const width = rect.width;
                    const percentage = (x / width) * 100;
                    eventOrigins.value[groupId] = `${percentage.toFixed(2)}%`;
                }
            }
            // Force reactivity
            expandedEvents.value = new Set(expandedEvents.value);
        };

        const isEventGroupExpanded = (groupId) => {
            return expandedEvents.value.has(groupId);
        };

        const getEventOrigin = (groupId) => {
            return eventOrigins.value[groupId] || '50%';
        };

        const setFilter = (type) => {
            filterType.value = type;
        };

        const startUptimeTimer = () => {
            if (uptimeTimer) return;
            uptimeTimer = setInterval(() => {
                if (!status.startTime || !status.running) return;
                const now = new Date();
                const diff = Math.floor((now - status.startTime) / 1000);

                if (diff < 0) {
                    status.uptime = '刚刚';
                    return;
                }

                const days = Math.floor(diff / 86400);
                const hours = Math.floor((diff % 86400) / 3600);
                const minutes = Math.floor((diff % 3600) / 60);
                const seconds = diff % 60;

                let str = '';
                if (days > 0) str += `${days}天`;
                if (hours > 0) str += `${hours}小时`;
                if (minutes > 0) str += `${minutes}分`;
                str += `${seconds}秒`;
                status.uptime = str;
            }, 1000);
        };

        // ========== Lifecycle ==========
        onMounted(async () => {
            initTheme();
            await loadSchemaAndConfig();

            // 连接 WebSocket
            connectWebSocket();
        });

        onUnmounted(() => {
            // 关闭 WebSocket 连接
            if (ws) {
                ws.close();
                ws = null;
            }
            if (wsReconnectTimer) {
                clearTimeout(wsReconnectTimer);
                wsReconnectTimer = null;
            }
            if (uptimeTimer) clearInterval(uptimeTimer);
        });

        // ========== Expose to template ==========
        return {
            // State
            status,
            stats,
            connections,
            sortedConnections,
            recentEvents,
            sortedRecentEvents,
            groupedEvents,
            expandedEvents,
            earthquakes,
            magnitudeDistribution,
            magnitudeOrder,
            maxMagnitudeValue,
            lastUpdate,
            showSettings,
            schema,
            fullConfig,
            settingsSaving,
            isDarkTheme,
            wsConnected,

            // Simulation Modal State
            showSimulation,
            simulationOptions,
            simulationForm,
            simulationSending,
            currentDisasterFormats,

            // Methods
            refreshAll,
            toggleTheme,
            openSettings,
            closeSettings,
            saveSettings,
            testPush,
            toggleEventGroup,
            isEventGroupExpanded,
            getEventOrigin,

            // Simulation Methods
            openSimulation,
            closeSimulation,
            sendSimulation,
            selectDisasterType,

            // Helpers
            formatTimeFriendly,
            getMagColorClass,
            getWeatherColorClass,
            setFilter,
            filterType,
        };
    }
});

// Register component
app.component('config-renderer', window.ConfigRenderer);

// Make app globally accessible for debugging
window.vueApp = app;
app.mount('#app');
