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

        // Polling
        let pollingTimer = null;
        let statusTimer = null;
        let uptimeTimer = null;

        // Settings Modal
        const showSettings = ref(false);
        const schema = ref(null);
        const fullConfig = ref(null);
        const settingsSaving = ref(false);

        // Theme
        const isDarkTheme = ref(false);

        // ========== 计算属性 ==========
        const sortedConnections = computed(() => {
            return Object.entries(connections.value).sort((a, b) => a[0].localeCompare(b[0]));
        });

        const sortedRecentEvents = computed(() => {
            return [...recentEvents.value].reverse();
        });

        const magnitudeOrder = [
            "< M3.0", "M3.0 - M3.9", "M4.0 - M4.9", "M5.0 - M5.9", "M6.0 - M6.9", "M7.0 - M7.9", ">= M8.0"
        ];

        const maxMagnitudeValue = computed(() => {
            return Math.max(...Object.values(magnitudeDistribution.value), 1);
        });

        // ========== API 方法 ==========
        const fetchStatus = async () => {
            try {
                const res = await fetch(`${API_BASE}/status`);
                const data = await res.json();
                status.running = data.running;
                // status.uptime is now calculated client-side if startTime is available
                // but we keep the server value as fallback or initial
                if (data.start_time) {
                    status.startTime = new Date(data.start_time);
                    startUptimeTimer();
                } else {
                    status.uptime = data.uptime;
                }
                status.activeConnections = data.active_connections;
                status.totalConnections = data.total_connections;
            } catch (e) {
                console.error('Fetch status failed', e);
            }
        };

        const fetchStatistics = async () => {
            try {
                const res = await fetch(`${API_BASE}/statistics`);
                const data = await res.json();
                stats.totalEvents = data.total_events || 0;
                stats.earthquakeCount = (data.by_type && data.by_type.earthquake) || 0;
                stats.tsunamiCount = (data.by_type && data.by_type.tsunami) || 0;
                stats.weatherCount = (data.by_type && data.by_type.weather_alarm) || 0;
                recentEvents.value = data.recent_pushes || [];
                if (data.earthquake_stats && data.earthquake_stats.by_magnitude) {
                    magnitudeDistribution.value = data.earthquake_stats.by_magnitude;
                }
            } catch (e) {
                console.error('Fetch stats failed', e);
            }
        };

        const fetchConnections = async () => {
            try {
                const res = await fetch(`${API_BASE}/connections`);
                const data = await res.json();
                connections.value = data.connections || {};
            } catch (e) {
                console.error('Fetch connections failed', e);
            }
        };

        const fetchEarthquakes = async () => {
            try {
                const res = await fetch(`${API_BASE}/earthquakes`);
                const data = await res.json();

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
            } catch (e) {
                console.error('Fetch earthquakes failed', e);
            }
        };

        const refreshAll = async () => {
            await Promise.all([
                fetchStatus(),
                fetchStatistics(),
                fetchConnections()
            ]);
            lastUpdate.value = new Date().toLocaleString('zh-CN');
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

            // Initial load
            await refreshAll();
            await fetchEarthquakes();

            // Fast polling for status (every 2s)
            statusTimer = setInterval(fetchStatus, 2000);

            // Regular polling for data (every 30s)
            pollingTimer = setInterval(async () => {
                await refreshAll();
                await fetchEarthquakes();
            }, 30000);
        });

        onUnmounted(() => {
            if (pollingTimer) clearInterval(pollingTimer);
            if (statusTimer) clearInterval(statusTimer);
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

            // Methods
            refreshAll,
            toggleTheme,
            openSettings,
            closeSettings,
            saveSettings,
            testPush,

            // Helpers
            formatTime,
            formatTimeFriendly,
            getMagColorClass,
        };
    }
});

// Register component
app.component('config-renderer', window.ConfigRenderer);

// Make app globally accessible for debugging
window.vueApp = app;
app.mount('#app');
