const { Dialog, DialogTitle, DialogContent, DialogActions, Button, Box, Typography, TextField, Select, MenuItem, FormControl, InputLabel, Divider, IconButton } = MaterialUI;
const { useState, useEffect } = React;

function SimulationModal({ open, onClose }) {
    const api = useApi();
    const [disasterType, setDisasterType] = useState('earthquake');
    const [testType, setTestType] = useState('china');
    const [targetGroup, setTargetGroup] = useState('');
    const [customParams, setCustomParams] = useState({
        latitude: 39.9,
        longitude: 116.4,
        magnitude: 5.5,
        depth: 10,
        location: '北京市',
        source: 'cea_fanstudio'
    });
    const [sending, setSending] = useState(false);
    const [params, setParams] = useState(null);

    useEffect(() => {
        if (open) {
            loadParams();
        }
    }, [open]);

    const loadParams = async () => {
        try {
            const result = await api.getSimulationParams();
            setParams(result);
        } catch (e) {
            console.error('加载模拟参数失败', e);
        }
    };

    const handleGeolocate = async () => {
        try {
            const result = await api.getGeoLocation();
            if (result.latitude && result.longitude) {
                setCustomParams({
                    ...customParams,
                    latitude: result.latitude,
                    longitude: result.longitude,
                    location: `${result.province || ''} ${result.city || ''}`
                });
            }
        } catch (e) {
            alert('获取位置失败');
            console.error(e);
        }
    };

    const handleSend = async () => {
        setSending(true);
        try {
            const result = await api.sendSimulation({
                target_group: targetGroup,
                disaster_type: disasterType,
                test_type: testType,
                custom_params: customParams
            });

            if (result.success) {
                alert(`✅ 测试成功!\n${result.message || '预警消息已发送'}`);
                onClose();
            } else {
                alert(`❌ 测试失败: ${result.message || result.error}`);
            }
        } catch (e) {
            alert('请求失败,请检查控制台');
            console.error(e);
        } finally {
            setSending(false);
        }
    };

    const getDisasterTypeOptions = () => {
        if (!params) return [];
        return Object.keys(params.disaster_types || {});
    };

    const getTestTypeOptions = () => {
        if (!params || !disasterType) return [];
        const typeData = params.disaster_types[disasterType];
        return Object.keys(typeData?.test_formats || {});
    };

    return (
        <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
            <DialogTitle>🧪 模拟预警测试</DialogTitle>
            <DialogContent>
                <Box sx={{ py: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {/* 目标群组 */}
                    <TextField
                        fullWidth
                        label="目标群组"
                        placeholder="留空发送到第一个配置的群组"
                        value={targetGroup}
                        onChange={(e) => setTargetGroup(e.target.value)}
                        size="small"
                        helperText="可选,指定要发送到的群组ID"
                    />

                    <Divider />

                    {/* 灾害类型 */}
                    <FormControl fullWidth size="small">
                        <InputLabel>灾害类型</InputLabel>
                        <Select
                            value={disasterType}
                            label="灾害类型"
                            onChange={(e) => {
                                setDisasterType(e.target.value);
                                setTestType('');
                            }}
                        >
                            {getDisasterTypeOptions().map(type => (
                                <MenuItem key={type} value={type}>
                                    {type === 'earthquake' ? '🌍 地震' :
                                        type === 'tsunami' ? '🌊 海啸' :
                                            type === 'weather' ? '☁️ 气象预警' : type}
                                </MenuItem>
                            ))}
                        </Select>
                    </FormControl>

                    {/* 测试格式 */}
                    {disasterType && (
                        <FormControl fullWidth size="small">
                            <InputLabel>测试格式</InputLabel>
                            <Select
                                value={testType}
                                label="测试格式"
                                onChange={(e) => setTestType(e.target.value)}
                            >
                                {getTestTypeOptions().map(type => (
                                    <MenuItem key={type} value={type}>{type}</MenuItem>
                                ))}
                            </Select>
                        </FormControl>
                    )}

                    <Divider />

                    {/* 自定义参数 */}
                    <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                        自定义参数
                    </Typography>

                    {disasterType === 'earthquake' && (
                        <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
                            <Box sx={{ display: 'flex', gap: 1, gridColumn: '1 / -1' }}>
                                <TextField
                                    fullWidth
                                    label="纬度"
                                    type="number"
                                    size="small"
                                    value={customParams.latitude}
                                    onChange={(e) => setCustomParams({ ...customParams, latitude: parseFloat(e.target.value) })}
                                />
                                <TextField
                                    fullWidth
                                    label="经度"
                                    type="number"
                                    size="small"
                                    value={customParams.longitude}
                                    onChange={(e) => setCustomParams({ ...customParams, longitude: parseFloat(e.target.value) })}
                                />
                                <IconButton onClick={handleGeolocate} title="使用当前位置">
                                    🌍
                                </IconButton>
                            </Box>

                            <TextField
                                label="震级"
                                type="number"
                                size="small"
                                value={customParams.magnitude}
                                onChange={(e) => setCustomParams({ ...customParams, magnitude: parseFloat(e.target.value) })}
                                inputProps={{ min: 0, max: 10, step: 0.1 }}
                            />

                            <TextField
                                label="深度 (km)"
                                type="number"
                                size="small"
                                value={customParams.depth}
                                onChange={(e) => setCustomParams({ ...customParams, depth: parseFloat(e.target.value) })}
                                inputProps={{ min: 0, step: 1 }}
                            />

                            <TextField
                                fullWidth
                                label="位置描述"
                                size="small"
                                value={customParams.location}
                                onChange={(e) => setCustomParams({ ...customParams, location: e.target.value })}
                                sx={{ gridColumn: '1 / -1' }}
                            />

                            <TextField
                                fullWidth
                                label="数据源"
                                size="small"
                                value={customParams.source}
                                onChange={(e) => setCustomParams({ ...customParams, source: e.target.value })}
                                sx={{ gridColumn: '1 / -1' }}
                            />
                        </Box>
                    )}

                    {disasterType === 'tsunami' && (
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <TextField
                                fullWidth
                                label="位置描述"
                                size="small"
                                value={customParams.location || ''}
                                onChange={(e) => setCustomParams({ ...customParams, location: e.target.value })}
                            />
                        </Box>
                    )}

                    {disasterType === 'weather' && (
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <TextField
                                fullWidth
                                label="预警描述"
                                size="small"
                                multiline
                                rows={2}
                                value={customParams.description || ''}
                                onChange={(e) => setCustomParams({ ...customParams, description: e.target.value })}
                            />
                        </Box>
                    )}
                </Box>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>取消</Button>
                <Button variant="contained" onClick={handleSend} disabled={sending || !testType}>
                    {sending ? '发送中...' : '📤 发送测试'}
                </Button>
            </DialogActions>
        </Dialog>
    );
}
