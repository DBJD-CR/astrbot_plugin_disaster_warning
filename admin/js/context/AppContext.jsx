const { createContext, useContext, useReducer, useEffect } = React;

// 初始状态
const initialState = {
    status: {
        running: false,
        uptime: '--',
        startTime: null,
        activeConnections: 0,
        totalConnections: 0
    },
    stats: {
        totalEvents: 0,
        earthquakeCount: 0,
        tsunamiCount: 0,
        weatherCount: 0
    },
    connections: {},
    events: [],
    magnitudeDistribution: {},
    wsConnected: false,
    theme: localStorage.getItem('theme') || 'light'
};

// Reducer
function appReducer(state, action) {
    switch (action.type) {
        case 'UPDATE_STATUS':
            return { ...state, status: { ...state.status, ...action.payload } };
        case 'UPDATE_STATS':
            const stats = action.payload;
            return {
                ...state,
                stats: {
                    totalEvents: stats.total_events || 0,
                    earthquakeCount: (stats.by_type && stats.by_type.earthquake) || 0,
                    tsunamiCount: (stats.by_type && stats.by_type.tsunami) || 0,
                    weatherCount: (stats.by_type && stats.by_type.weather_alarm) || 0
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
        document.body.className = state.theme === 'dark' ? 'dark-theme' : '';
        localStorage.setItem('theme', state.theme);
    }, [state.theme]);

    // 运行时长计时器
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
        <AppContext.Provider value={{ state, dispatch }}>
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
