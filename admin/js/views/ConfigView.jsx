const { Box, Typography } = MaterialUI;

function ConfigView() {
    return (
        <Box>
            <div className="card">
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                    <div style={{ width: '4px', height: '24px', background: 'var(--md-sys-color-primary)', borderRadius: '2px' }}></div>
                    <Typography variant="h6" sx={{ fontWeight: 800, letterSpacing: '-0.5px' }}>配置管理</Typography>
                </div>
                <ConfigRenderer />
            </div>
        </Box>
    );
}
