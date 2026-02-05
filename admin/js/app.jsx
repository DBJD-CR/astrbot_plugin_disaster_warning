const { ThemeProvider, createTheme, CssBaseline, Box, Container, Button, Card, CardContent } = MaterialUI;
const { useState, useMemo } = React;

function App() {
    const { state } = useAppContext();
    const [showSettings, setShowSettings] = useState(false);
    const [showSimulation, setShowSimulation] = useState(false);

    // 使用WebSocket Hook
    useWebSocket();

    // MUI主题配置
    const theme = useMemo(() => createTheme({
        palette: {
            mode: state.theme,
            primary: { main: '#005AC1' },
            secondary: { main: '#575E71' },
        },
        shape: {
            borderRadius: 12,
        },
        typography: {
            fontFamily: '"Outfit", sans-serif',
        },
    }), [state.theme]);

    const refreshAll = () => {
        window.location.reload();
    };

    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
                <Header onOpenSettings={() => setShowSettings(true)} />

                <Container maxWidth="xl" sx={{ flex: 1, py: 3 }}>
                    {/* 状态卡片网格 */}
                    <Box sx={{
                        display: 'grid',
                        gap: 2,
                        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                        mb: 2
                    }}>
                        <StatusCard />
                        <StatsCard />
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                                    <span style={{ fontSize: '24px' }}>⚡</span>
                                    <Typography variant="h6">快捷操作</Typography>
                                </Box>
                                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                                    <Button variant="contained" onClick={() => setShowSimulation(true)}>
                                        🧪 模拟预警
                                    </Button>
                                    <Button variant="outlined" onClick={refreshAll}>
                                        🔄 刷新
                                    </Button>
                                </Box>
                            </CardContent>
                        </Card>
                    </Box>

                    {/* 数据源连接 */}
                    <ConnectionsGrid />

                    {/* 震级分布图表 */}
                    <MagnitudeChart />

                    {/* 最近事件列表 */}
                    <EventsList />
                </Container>

                {/* 页脚 */}
                <Box component="footer" sx={{
                    textAlign: 'center',
                    py: 2,
                    borderTop: 1,
                    borderColor: 'divider',
                    color: 'text.secondary',
                    fontSize: '0.875rem'
                }}>
                    <Typography variant="caption">灾害预警插件 Web 管理端 - React版</Typography>
                </Box>

                {/* 配置模态框(简化) */}
                {showSettings && (
                    <Dialog open={showSettings} onClose={() => setShowSettings(false)} maxWidth="md" fullWidth>
                        <DialogTitle>⚙️ 插件配置</DialogTitle>
                        <DialogContent>
                            <ConfigRenderer />
                        </DialogContent>

                    </Dialog>
                )}

                {/* 模拟预警模态框 */}
                <SimulationModal open={showSimulation} onClose={() => setShowSimulation(false)} />
            </Box>
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
