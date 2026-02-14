const { ThemeProvider, createTheme, CssBaseline, Box, Container } = MaterialUI;
const { useState, useMemo, useEffect, useRef, useLayoutEffect } = React;

/**
 * 应用程序根组件
 * 负责主题配置、路由（视图切换）以及全局状态初始化
 */
function App() {
    const { state } = useAppContext();
    // 从 localStorage 初始化 currentView，默认为 'status'
    const [currentView, setCurrentView] = useState(() => {
        return localStorage.getItem('currentView') || 'status';
    });
    const [showSimulation, setShowSimulation] = useState(false);

    // 监听 currentView 变化并保存到 localStorage
    useEffect(() => {
        localStorage.setItem('currentView', currentView);
    }, [currentView]);

    // 滚动位置记忆处理
    const mainContentRef = useRef(null);
    const isRestoringRef = useRef(false);

    // 1. 切换视图时恢复滚动位置
    useLayoutEffect(() => {
        const el = mainContentRef.current;
        if (!el) return;

        const key = `astrbot_scroll_${currentView}`;
        const savedPos = parseInt(localStorage.getItem(key) || '0', 10);
        
        // 标记正在恢复中，避免保存逻辑覆盖
        isRestoringRef.current = true;

        if (savedPos > 0) {
            el.scrollTop = savedPos;
            
            // 针对异步内容加载的重试机制
            const retryScroll = () => {
                // 1. 如果用户已手动介入（通过事件监听捕获），停止恢复
                if (!isRestoringRef.current) return;

                const currentScroll = el.scrollTop;
                
                // 2. 智能检测：如果当前滚动位置既不是0，也与目标位置偏差较大（>100px）
                // 很有可能是用户通过拖动滚动条改变了位置（这种操作难以通过事件完全捕获）
                // 此时应放弃后续的强制修正，尊重用户当前的浏览位置
                if (currentScroll > 0 && Math.abs(currentScroll - savedPos) > 100) {
                    isRestoringRef.current = false;
                    return;
                }

                if (Math.abs(currentScroll - savedPos) > 5 && el.scrollHeight > el.clientHeight) {
                    el.scrollTop = savedPos;
                }
            };

            // 多次尝试以适应不同的加载速度
            // 增加尝试次数和持续时间，以应对网络延迟导致的列表渲染滞后
            const timeouts = [
                setTimeout(retryScroll, 50),
                setTimeout(retryScroll, 200),
                setTimeout(retryScroll, 500),
                setTimeout(retryScroll, 1000),
                setTimeout(retryScroll, 2000)
            ];

            // 2.5秒后结束恢复状态
            const tEnd = setTimeout(() => {
                isRestoringRef.current = false;
            }, 2500);

            return () => {
                timeouts.forEach(clearTimeout);
                clearTimeout(tEnd);
            };
        } else {
            el.scrollTop = 0;
            isRestoringRef.current = false;
        }
    }, [currentView]);

    // 补充：数据变化时尝试再次修正滚动位置（应对列表动态加载）
    useEffect(() => {
        if (isRestoringRef.current && mainContentRef.current) {
            const key = `astrbot_scroll_${currentView}`;
            const savedPos = parseInt(localStorage.getItem(key) || '0', 10);
            const el = mainContentRef.current;
            
            // 再次检查锁状态，防止在 Effect 执行前用户已经打断
            if (isRestoringRef.current && savedPos > 0 && Math.abs(el.scrollTop - savedPos) > 20 && el.scrollHeight >= savedPos) {
                // 同样增加智能检测：如果偏差过大，认为是用户操作
                if (el.scrollTop > 0 && Math.abs(el.scrollTop - savedPos) > 100) {
                    isRestoringRef.current = false;
                    return;
                }
                el.scrollTop = savedPos;
            }
        }
    }, [state.events, state.stats]);

    // 2. 监听滚动并保存
    useEffect(() => {
        const el = mainContentRef.current;
        if (!el) return;

        const handleScroll = () => {
            // 如果处于恢复状态
            if (isRestoringRef.current) {
                const key = `astrbot_scroll_${currentView}`;
                const savedPos = parseInt(localStorage.getItem(key) || '0', 10);
                
                // 额外检查：如果滚动位置发生了巨大变化（>100px），这通常意味着用户拖动了滚动条
                // 此时即使没有触发 mousedown/touchstart 等事件，也应该解除锁定
                if (Math.abs(el.scrollTop - savedPos) > 100) {
                    isRestoringRef.current = false;
                } else {
                    // 否则认为是自动恢复过程中的滚动，不保存
                    return;
                }
            }

            const key = `astrbot_scroll_${currentView}`;
            localStorage.setItem(key, el.scrollTop);
        };

        // 防抖处理
        let timeout;
        const debouncedScroll = () => {
            clearTimeout(timeout);
            timeout = setTimeout(handleScroll, 100);
        };

        el.addEventListener('scroll', debouncedScroll);
        // 监听用户交互以立即终止恢复状态
        const stopRestoring = () => { isRestoringRef.current = false; };
        el.addEventListener('touchstart', stopRestoring, { passive: true });
        el.addEventListener('wheel', stopRestoring, { passive: true });
        el.addEventListener('mousedown', stopRestoring); // 捕获滚动条拖动
        el.addEventListener('keydown', stopRestoring); // 捕获键盘滚动

        return () => {
            el.removeEventListener('scroll', debouncedScroll);
            el.removeEventListener('touchstart', stopRestoring);
            el.removeEventListener('wheel', stopRestoring);
            el.removeEventListener('mousedown', stopRestoring);
            el.removeEventListener('keydown', stopRestoring);
            clearTimeout(timeout);
        };
    }, [currentView]);

    // 使用WebSocket Hook
    // 注意：useWebSocket 应该在 AppProvider 内部使用，但这里 App 组件已经在 AppProvider 内部
    // 所以调用是安全的。保持全局单例连接。
    useWebSocket();

    // Material Design 3 主题配置 - 紫色种子色（正确的层次）
    const theme = useMemo(() => createTheme({
        palette: {
            mode: state.theme,
            primary: {
                main: state.theme === 'dark' ? '#D0BCFF' : '#6750A4',
                light: state.theme === 'dark' ? '#EADDFF' : '#7F67BE',
                dark: state.theme === 'dark' ? '#B69DF8' : '#4F378B',
                contrastText: state.theme === 'dark' ? '#371E73' : '#FFFFFF',
            },
            secondary: {
                main: state.theme === 'dark' ? '#CCC2DC' : '#625B71',
                light: state.theme === 'dark' ? '#E8DEF8' : '#7D7589',
                dark: state.theme === 'dark' ? '#B0A7C0' : '#4A4458',
                contrastText: state.theme === 'dark' ? '#332D41' : '#FFFFFF',
            },
            tertiary: {
                main: state.theme === 'dark' ? '#EFB8C8' : '#7D5260',
            },
            error: {
                main: state.theme === 'dark' ? '#F2B8B5' : '#B3261E',
                light: state.theme === 'dark' ? '#F9DEDC' : '#DC362E',
                dark: state.theme === 'dark' ? '#EC928E' : '#8C1D18',
                contrastText: state.theme === 'dark' ? '#601410' : '#FFFFFF',
            },
            success: {
                main: state.theme === 'dark' ? '#A6D389' : '#386A20',
                light: state.theme === 'dark' ? '#C4EBA0' : '#629749',
                contrastText: state.theme === 'dark' ? '#0E2000' : '#FFFFFF',
            },
            background: {
                default: state.theme === 'dark' ? '#141218' : '#FEF7FF',
                paper: state.theme === 'dark' ? '#1C1B1F' : '#FFFFFF',
            },
            surface: {
                main: state.theme === 'dark' ? '#1C1B1F' : '#FFFFFF',
                variant: state.theme === 'dark' ? '#49454F' : '#E7E0EC',
                tint: state.theme === 'dark' ? '#D0BCFF' : '#6750A4',
            },
            surfaceContainer: {
                lowest: state.theme === 'dark' ? '#0F0D13' : '#FFFFFF',
                low: state.theme === 'dark' ? '#1D1B20' : '#F7F2FA',
                main: state.theme === 'dark' ? '#211F26' : '#F3EDF7',
                high: state.theme === 'dark' ? '#2B2930' : '#ECE6F0',
                highest: state.theme === 'dark' ? '#36343B' : '#E6E0E9',
            },
            outline: {
                main: state.theme === 'dark' ? '#938F99' : '#79747E',
                variant: state.theme === 'dark' ? '#49454F' : '#CAC4D0',
            },
            text: {
                primary: state.theme === 'dark' ? '#E6E1E5' : '#1D1B20',
                secondary: state.theme === 'dark' ? '#CAC4D0' : '#49454F',
            },
            divider: state.theme === 'dark' ? 'rgba(147, 143, 153, 0.12)' : 'rgba(121, 116, 126, 0.12)',
        },
        shape: {
            borderRadius: 12,
        },
        typography: {
            fontFamily: '"Roboto", "Noto Sans SC", "Helvetica", "Arial", sans-serif',
            h3: {
                fontSize: '3rem',
                fontWeight: 400,
                lineHeight: 1.167,
                letterSpacing: '0em',
            },
            h5: {
                fontSize: '1.5rem',
                fontWeight: 400,
                lineHeight: 1.334,
                letterSpacing: '0em',
            },
            h6: {
                fontSize: '1.25rem',
                fontWeight: 500,
                lineHeight: 1.6,
                letterSpacing: '0.0075em',
            },
            subtitle1: {
                fontSize: '1rem',
                fontWeight: 500,
                lineHeight: 1.5,
                letterSpacing: '0.00938em',
            },
            subtitle2: {
                fontSize: '0.875rem',
                fontWeight: 500,
                lineHeight: 1.57,
                letterSpacing: '0.00714em',
            },
            body1: {
                fontSize: '1rem',
                fontWeight: 400,
                lineHeight: 1.5,
                letterSpacing: '0.00938em',
            },
            body2: {
                fontSize: '0.875rem',
                fontWeight: 400,
                lineHeight: 1.43,
                letterSpacing: '0.01071em',
            },
            button: {
                fontSize: '0.875rem',
                fontWeight: 500,
                lineHeight: 1.75,
                letterSpacing: '0.02857em',
                textTransform: 'none',
            },
            caption: {
                fontSize: '0.75rem',
                fontWeight: 400,
                lineHeight: 1.66,
                letterSpacing: '0.03333em',
            }
        },
        components: {
            MuiCssBaseline: {
                styleOverrides: {
                    body: {
                        backgroundColor: state.theme === 'dark' ? '#141218' : '#FEF7FF',
                    }
                }
            },
            MuiCard: {
                defaultProps: {
                    elevation: 0,
                },
                styleOverrides: {
                    root: {
                        backgroundColor: 'transparent',
                        borderRadius: 16,
                        border: 'none',
                    }
                }
            },
            MuiButton: {
                defaultProps: {
                    disableElevation: true,
                },
                styleOverrides: {
                    root: {
                        borderRadius: 100,
                        paddingLeft: 24,
                        paddingRight: 24,
                        paddingTop: 10,
                        paddingBottom: 10,
                        textTransform: 'none',
                        fontWeight: 600,
                        fontSize: '0.875rem',
                        letterSpacing: '0.02857em',
                    },
                    contained: {
                        backgroundColor: state.theme === 'dark' ? '#D0BCFF' : '#6750A4',
                        color: state.theme === 'dark' ? '#371E73' : '#FFFFFF',
                        '&:hover': {
                            backgroundColor: state.theme === 'dark' ? '#E8DDFF' : '#7F67BE',
                            boxShadow: '0 4px 12px rgba(103, 80, 164, 0.2)',
                        }
                    },
                    outlined: {
                        borderColor: state.theme === 'dark' ? '#938F99' : '#79747E',
                        color: state.theme === 'dark' ? '#D0BCFF' : '#6750A4',
                        '&:hover': {
                            backgroundColor: state.theme === 'dark' 
                                ? 'rgba(208, 188, 255, 0.08)' 
                                : 'rgba(103, 80, 164, 0.08)',
                            borderColor: state.theme === 'dark' ? '#D0BCFF' : '#6750A4',
                        }
                    },
                    text: {
                        color: state.theme === 'dark' ? '#D0BCFF' : '#6750A4',
                    }
                }
            },
            MuiListItemButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 100,
                        margin: '0 8px',
                        '&.Mui-selected': {
                            backgroundColor: state.theme === 'dark' 
                                ? 'rgba(208, 188, 255, 0.12)' 
                                : 'rgba(103, 80, 164, 0.12)',
                            color: state.theme === 'dark' ? '#D0BCFF' : '#21005D',
                            '&:hover': {
                                backgroundColor: state.theme === 'dark' 
                                    ? 'rgba(208, 188, 255, 0.16)' 
                                    : 'rgba(103, 80, 164, 0.16)',
                            }
                        },
                        '&:hover': {
                            backgroundColor: state.theme === 'dark' 
                                ? 'rgba(208, 188, 255, 0.08)' 
                                : 'rgba(103, 80, 164, 0.08)',
                        }
                    }
                }
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                        fontWeight: 600,
                        border: 'none',
                    },
                    colorSuccess: {
                        backgroundColor: state.theme === 'dark' ? 'rgba(166, 211, 137, 0.12)' : 'rgba(56, 106, 32, 0.12)',
                        color: state.theme === 'dark' ? '#A6D389' : '#386A20',
                    },
                    colorError: {
                        backgroundColor: state.theme === 'dark' ? 'rgba(242, 184, 181, 0.12)' : 'rgba(179, 38, 30, 0.12)',
                        color: state.theme === 'dark' ? '#F2B8B5' : '#B3261E',
                    }
                }
            },
            MuiPaper: {
                defaultProps: {
                    elevation: 0,
                },
                styleOverrides: {
                    root: {
                        backgroundColor: state.theme === 'dark' ? '#211F26' : '#F7F2FA',
                        backgroundImage: 'none',
                        border: 'none',
                    }
                }
            },
            MuiDivider: {
                styleOverrides: {
                    root: {
                        borderColor: state.theme === 'dark' ? 'rgba(147, 143, 153, 0.12)' : 'rgba(121, 116, 126, 0.12)',
                    }
                }
            }
        }
    }), [state.theme]);

    const renderView = () => {
        switch (currentView) {
            case 'status':
                return <StatusView onOpenSimulation={() => setShowSimulation(true)} />;
            case 'events':
                return <EventsView />;
            case 'stats':
                return <StatsView />;
            case 'config':
                return <ConfigView />;
            default:
                return <StatusView onOpenSimulation={() => setShowSimulation(true)} />;
        }
    };

    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            <div className="app">
                {/* 侧边栏 */}
                <Sidebar currentView={currentView} onViewChange={setCurrentView} />

                {/* 主内容区 */}
                <div className="main-wrapper">
                    <Header currentView={currentView} />

                    <div className="main-content" ref={mainContentRef}>
                        {renderView()}
                    </div>
                </div>

                {/* 模拟预警模态框 */}
                <SimulationModal open={showSimulation} onClose={() => setShowSimulation(false)} />
            </div>
        </ThemeProvider>
    );
}

// 渲染应用
const rootElement = document.getElementById('root');
const root = ReactDOM.createRoot(rootElement);
root.render(
    <AppProvider>
        <ToastProvider>
            <App />
        </ToastProvider>
    </AppProvider>
);
