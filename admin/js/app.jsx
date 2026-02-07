const { ThemeProvider, createTheme, CssBaseline, Box, Container } = MaterialUI;
const { useState, useMemo } = React;

function App() {
    const { state } = useAppContext();
    const [currentView, setCurrentView] = useState('status');
    const [showSimulation, setShowSimulation] = useState(false);

    // 使用WebSocket Hook
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

                    <div className="main-content">
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
        <App />
    </AppProvider>
);
