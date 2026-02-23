const { createContext, useContext, useReducer, useEffect } = React;

/**
 * 应用全局状态上下文
 * 管理应用的核心数据，包括运行状态、统计信息、连接状态和事件列表
 */

// 初始状态定义
const initialState = {
    // 系统核心状态
    config: {
        apiUrl: '',
        displayTimezone: 'UTC+8' // 默认时区
    },
    status: {
        running: false,
        uptime: '--',
        startTime: null,
        activeConnections: 0,
        totalConnections: 0,
        version: '未知版本'
    },
    stats: {
        totalEvents: 0,
        earthquakeCount: 0,
        warningCount: 0,
        tsunamiCount: 0,
        weatherCount: 0,
        maxMagnitude: null,
        earthquakeRegions: [],
        weatherRegions: [],
        weatherLevels: [],
        weatherTypes: [],
        dataSources: [],
        logStats: null
    },
    connections: {},
    events: [],
    magnitudeDistribution: {},
    wsConnected: false,
    theme: localStorage.getItem('theme') || 'light',
    // 新增：数据加载状态
    dataLoaded: false
};

// Reducer
function appReducer(state, action) {
    switch (action.type) {
        case 'UPDATE_STATUS':
            return { ...state, status: { ...state.status, ...action.payload }, dataLoaded: true };
        case 'UPDATE_CONFIG':
            return { ...state, config: { ...state.config, ...action.payload } };
        case 'UPDATE_STATS':
            const stats = action.payload;
            
            // 处理地震地区数据
            const eqRegions = [];
            if (stats.earthquake_stats && stats.earthquake_stats.by_region) {
                Object.entries(stats.earthquake_stats.by_region).forEach(([region, count]) => {
                    eqRegions.push({ region, count });
                });
                eqRegions.sort((a, b) => b.count - a.count);
            }

            // 处理气象数据
            const wRegions = [];
            const wTypes = [];
            const wLevels = [];
            
            if (stats.weather_stats) {
                if (stats.weather_stats.by_region) {
                    Object.entries(stats.weather_stats.by_region).forEach(([region, count]) => {
                        wRegions.push({ region, count });
                    });
                    wRegions.sort((a, b) => b.count - a.count);
                }
                if (stats.weather_stats.by_type) {
                    Object.entries(stats.weather_stats.by_type).forEach(([type, count]) => {
                        wTypes.push({ type, count });
                    });
                    wTypes.sort((a, b) => b.count - a.count);
                }
                if (stats.weather_stats.by_level) {
                    Object.entries(stats.weather_stats.by_level).forEach(([level, count]) => {
                        wLevels.push({ level, count });
                    });
                    // 按数量排序
                    wLevels.sort((a, b) => b.count - a.count);
                }
            }

            // 处理数据源统计
            const dSources = [];
            if (stats.by_source) {
                Object.entries(stats.by_source).forEach(([source, count]) => {
                    dSources.push({ source, count });
                });
                dSources.sort((a, b) => b.count - a.count);
            }

            return {
                ...state,
                stats: {
                    totalEvents: stats.total_events || 0,
                    earthquakeCount: (stats.by_type && stats.by_type.earthquake) || 0,
                    warningCount: (stats.by_type && typeof stats.by_type.earthquake_warning !== 'undefined') ? Number(stats.by_type.earthquake_warning) : 0,
                    tsunamiCount: (stats.by_type && stats.by_type.tsunami) || 0,
                    weatherCount: (stats.by_type && stats.by_type.weather_alarm) || 0,
                    maxMagnitude: (stats.earthquake_stats && stats.earthquake_stats.max_magnitude) || null,
                    earthquakeRegions: eqRegions,
                    weatherRegions: wRegions,
                    weatherTypes: wTypes,
                    weatherLevels: wLevels,
                    dataSources: dSources,
                    logStats: stats.log_stats || null
                },
                events: stats.recent_pushes || [],
                magnitudeDistribution: (stats.earthquake_stats && stats.earthquake_stats.by_magnitude) || {}
            };
        case 'UPDATE_CONNECTIONS':
            return { ...state, connections: action.payload };
        case 'SET_WS_CONNECTED':
            return { ...state, wsConnected: action.payload };
        case 'TOGGLE_THEME':
            return { ...state, theme: state.theme === 'light' ? 'dark' : 'light' };
        default:
            return state;
    }
}

// Context
const AppContext = createContext();

// Provider组件
function AppProvider({ children }) {
    const [state, dispatch] = useReducer(appReducer, initialState);

    // 主题效果
    useEffect(() => {
        const isDark = state.theme === 'dark';

        document.body.className = isDark ? 'dark-theme' : '';
        document.documentElement.classList.toggle('theme-dark', isDark);

        localStorage.setItem('theme', state.theme);
    }, [state.theme]);

    // 封装刷新数据的函数
    const refreshData = React.useCallback(() => {
        return fetch('/api/status')
            .then(res => res.json())
            .then(data => {
                const statusUpdate = {
                    running: data.running,
                    activeConnections: data.active_connections,
                    totalConnections: data.total_connections,
                    uptime: data.uptime,
                    subSourceStatus: data.sub_source_status // 新增：子数据源状态
                };

                // version 可能不存在于旧版接口返回中，但在新版应该有
                // 如果没有，就保持初始值
                if (data.version) {
                    statusUpdate.version = data.version;
                }
                
                // 处理 start_time
                if (data.start_time) {
                    statusUpdate.startTime = new Date(data.start_time);
                }

                dispatch({ type: 'UPDATE_STATUS', payload: statusUpdate });
                return data;
            })
            .catch(err => {
                console.error('Failed to fetch status:', err);
                throw err;
            });
    }, []);

    // 获取连接状态（包括延迟）
    const fetchConnections = React.useCallback(() => {
        return fetch('/api/connections')
            .then(res => res.json())
            .then(data => {
                if (data.connections) {
                    dispatch({ type: 'UPDATE_CONNECTIONS', payload: data.connections });
                }
                return data;
            })
            .catch(err => {
                console.error('Failed to fetch connections:', err);
                throw err;
            });
    }, []);

    // 获取配置信息（包括时区）
    const fetchConfig = React.useCallback(() => {
        return fetch('/api/config')
            .then(res => res.json())
            .then(data => {
                if (data.display_timezone) {
                    dispatch({
                        type: 'UPDATE_CONFIG',
                        payload: { displayTimezone: data.display_timezone }
                    });
                }
                return data;
            })
            .catch(err => {
                console.error('Failed to fetch config:', err);
                throw err;
            });
    }, []);

    // 初始化时延迟加载数据，优先渲染UI框架
    useEffect(() => {
        // 使用 setTimeout 确保首屏 UI 先渲染
        const timer = setTimeout(() => {
            refreshData();
            fetchConfig();
            fetchConnections(); // 加载连接状态（包括延迟信息）
        }, 0);
        
        return () => clearTimeout(timer);
    }, [refreshData, fetchConfig, fetchConnections]);

    // 运行时长计时器
    // 每秒更新一次 uptime 显示，格式化为 天/小时/分/秒
    useEffect(() => {
        if (!state.status.startTime || !state.status.running) return;

        const timer = setInterval(() => {
            const now = new Date();
            const diff = Math.floor((now - state.status.startTime) / 1000);

            if (diff < 0) {
                dispatch({ type: 'UPDATE_STATUS', payload: { uptime: '刚刚' } });
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

            dispatch({ type: 'UPDATE_STATUS', payload: { uptime: str } });
        }, 1000);

        return () => clearInterval(timer);
    }, [state.status.startTime, state.status.running]);

    return (
        <AppContext.Provider value={{ state, dispatch, refreshData, fetchConnections, fetchConfig }}>
            {children}
        </AppContext.Provider>
    );
}

// Hook
function useAppContext() {
    const context = useContext(AppContext);
    if (!context) {
        throw new Error('useAppContext must be used within AppProvider');
    }
    return context;
}

// 暴露给全局
window.AppProvider = AppProvider;
window.useAppContext = useAppContext;
