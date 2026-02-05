const { AppBar, Toolbar, Typography, IconButton, Box } = MaterialUI;

function Header({ onOpenSettings }) {
    const { state, dispatch } = useAppContext();

    const toggleTheme = () => {
        dispatch({ type: 'TOGGLE_THEME' });
    };

    return (
        <AppBar position="static" color="default" elevation={1}>
            <Toolbar>
                <Typography variant="h6" sx={{ flexGrow: 1, ml: 1.5 }}>
                    灾害预警管理端
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box
                            sx={{
                                width: 8,
                                height: 8,
                                borderRadius: '50%',
                                bgcolor: state.wsConnected ? 'success.main' : 'error.main'
                            }}
                        />
                        <Typography variant="body2">
                            {state.wsConnected ? '实时监控中' : '连接断开'}
                        </Typography>
                    </Box>
                    <IconButton onClick={toggleTheme} title="切换主题">
                        🌓
                    </IconButton>
                    <IconButton onClick={onOpenSettings} title="设置">
                        ⚙️
                    </IconButton>
                </Box>
            </Toolbar>
        </AppBar>
    );
}
