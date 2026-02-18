const { Dialog, DialogTitle, DialogContent, DialogActions, Button, Box, Typography, TextField, Select, MenuItem, FormControl, InputLabel, Divider, IconButton } = MaterialUI;
const { useState, useEffect } = React;

/**
 * 模拟预警测试模态框
 * 允许管理员发送模拟的灾害预警消息，用于测试推送配置和格式
 * 支持自定义灾害类型、测试格式以及具体的经纬度、震级等参数
 *
 * @param {Object} props
 * @param {boolean} props.open - 是否显示模态框
 * @param {Function} props.onClose - 关闭回调
 */
function SimulationModal({ open, onClose }) {
    const api = useApi();
    const { showToast } = useToast(); // 使用 Toast 提示
    const [disasterType, setDisasterType] = useState('earthquake');
    const [testType, setTestType] = useState('cea_fanstudio');
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

    // 当测试格式改变时，自动更新数据源字段
    useEffect(() => {
        if (testType) {
            setCustomParams(prev => ({
                ...prev,
                source: testType
            }));
        }
    }, [testType]);

    // 加载后端支持的模拟参数配置（灾害类型、测试格式等）
    const loadParams = async () => {
        try {
            const result = await api.getSimulationParams();
            setParams(result);
        } catch (e) {
            console.error('加载模拟参数失败', e);
        }
    };

    // 获取当前浏览器位置（用于快速填充经纬度）
    const handleGeolocate = async () => {
        try {
            const result = await api.getGeoLocation();
            if (result.success && result.data) {
                const { latitude, longitude, province, city } = result.data;
                if (latitude && longitude) {
                    setCustomParams(prev => ({
                        ...prev,
                        latitude: latitude,
                        longitude: longitude,
                        location: `${province || ''} ${city || ''}`.trim() || prev.location
                    }));
                }
            } else {
                showToast('获取位置失败: ' + (result.error || '未知错误'), 'error');
            }
        } catch (e) {
            showToast('获取位置失败', 'error');
            console.error(e);
        }
    };

    // 发送模拟请求
    const handleSend = async () => {
        setSending(true);
        try {
            const result = await api.sendSimulation({
                target_session: targetGroup,
                disaster_type: disasterType,
                test_type: testType,
                custom_params: customParams
            });

            if (result.success) {
                showToast(result.message || '预警消息已发送', 'success');
                onClose();
            } else {
                showToast(`测试失败: ${result.message || result.error}`, 'error');
            }
        } catch (e) {
            showToast('请求失败,请检查控制台', 'error');
            console.error(e);
        } finally {
            setSending(false);
        }
    };

    const getDisasterTypeOptions = () => {
        if (!params) return [];
        // 只返回 earthquake，因为后端只支持地震模拟
        const allTypes = Object.keys(params.disaster_types || {});
        return allTypes.filter(type => type === 'earthquake');
    };

    const getTestTypeOptions = () => {
        if (!params || !disasterType) return [];
        const typeData = params.disaster_types[disasterType];
        // 修复：后端返回的是 formats 数组，不是 test_formats 对象
        return typeData?.formats || [];
    };

    const getTargetSessionOptions = () => {
        if (!params || !params.target_sessions) return [];
        return params.target_sessions;
    };

    return (
        <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
            <DialogTitle>🧪 模拟预警测试</DialogTitle>
            <DialogContent>
                <Box sx={{ py: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {/* 目标会话 */}
                    <FormControl fullWidth size="small">
                        <InputLabel shrink>目标会话</InputLabel>
                        <Select
                            value={targetGroup}
                            label="目标会话"
                            onChange={(e) => setTargetGroup(e.target.value)}
                            displayEmpty
                            notched
                        >
                            <MenuItem value="">
                                <em>默认 (第一个配置的会话)</em>
                            </MenuItem>
                            {getTargetSessionOptions().map((session, index) => (
                                <MenuItem key={index} value={session}>
                                    {session}
                                </MenuItem>
                            ))}
                        </Select>
                    </FormControl>

                    <Divider />

                    {/* 灾害类型 */}
                    <FormControl fullWidth size="small">
                        <InputLabel>灾害类型</InputLabel>
                        <Select
                            value={disasterType}
                            label="灾害类型"
                            onChange={(e) => {
                                setDisasterType(e.target.value);
                                setTestType('cea_fanstudio');
                            }}
                            disabled
                        >
                            {getDisasterTypeOptions().map(type => (
                                <MenuItem key={type} value={type}>
                                    {type === 'earthquake' ? '🌍 地震（仅支持）' : type}
                                </MenuItem>
                            ))}
                        </Select>
                        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, ml: 1.5 }}>
                            目前仅支持地震模拟，其他灾害类型正在开发中
                        </Typography>
                    </FormControl>

                    {/* 测试格式 */}
                    {disasterType && (
                        <FormControl fullWidth size="small">
                            <InputLabel>测试格式 (数据源模板)</InputLabel>
                            <Select
                                value={testType}
                                label="测试格式 (数据源模板)"
                                onChange={(e) => setTestType(e.target.value)}
                            >
                                {getTestTypeOptions().map(format => (
                                    <MenuItem key={format.value} value={format.value}>
                                        {format.label}
                                    </MenuItem>
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
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            {/* 经纬度、震级、深度合并行 */}
                            <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                                <TextField
                                    label="纬度"
                                    type="number"
                                    size="small"
                                    value={customParams.latitude}
                                    onChange={(e) => setCustomParams({ ...customParams, latitude: parseFloat(e.target.value) })}
                                    sx={{ flex: 1.2 }}
                                />
                                <TextField
                                    label="经度"
                                    type="number"
                                    size="small"
                                    value={customParams.longitude}
                                    onChange={(e) => setCustomParams({ ...customParams, longitude: parseFloat(e.target.value) })}
                                    sx={{ flex: 1.2 }}
                                />
                                <Tooltip title="使用当前 IP 自动定位填充经纬度">
                                    <IconButton onClick={handleGeolocate} color="primary" sx={{ border: '1px solid var(--md-sys-color-outline-variant)', borderRadius: '8px', padding: '8px' }}>
                                        <span style={{ fontSize: '1.1rem' }}>📍</span>
                                    </IconButton>
                                </Tooltip>
                                <TextField
                                    label="震级 (M)"
                                    type="number"
                                    size="small"
                                    value={customParams.magnitude}
                                    onChange={(e) => setCustomParams({ ...customParams, magnitude: parseFloat(e.target.value) })}
                                    inputProps={{ min: 0, max: 10, step: 0.1 }}
                                    sx={{ flex: 0.8 }}
                                />
                                <TextField
                                    label="深度 (km)"
                                    type="number"
                                    size="small"
                                    value={customParams.depth}
                                    onChange={(e) => setCustomParams({ ...customParams, depth: parseFloat(e.target.value) })}
                                    inputProps={{ min: 0, step: 1 }}
                                    sx={{ flex: 0.8 }}
                                />
                            </Box>

                            {/* 位置描述 */}
                            <TextField
                                fullWidth
                                label="位置描述"
                                size="small"
                                value={customParams.location}
                                onChange={(e) => setCustomParams({ ...customParams, location: e.target.value })}
                            />

                            {/* 数据源选择 */}
                            <FormControl fullWidth size="small">
                                <InputLabel>数据源</InputLabel>
                                <Select
                                    value={customParams.source}
                                    label="数据源"
                                    onChange={(e) => setCustomParams({ ...customParams, source: e.target.value })}
                                >
                                    {getTestTypeOptions().map(format => (
                                        <MenuItem key={format.value} value={format.value}>
                                            {format.label}
                                        </MenuItem>
                                    ))}
                                </Select>
                            </FormControl>
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
