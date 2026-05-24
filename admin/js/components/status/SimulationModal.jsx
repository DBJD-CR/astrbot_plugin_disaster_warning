const { Dialog, DialogTitle, DialogContent, DialogActions, Button, Box, Typography, TextField, Select, MenuItem, FormControl, InputLabel, Divider, IconButton, Tooltip } = MaterialUI;
const { useState, useEffect } = React;

/**
 * 模拟灾害预警测试配置模态框组件 (SimulationModal)
 * 允许具有管理员特权的运维开发人员在控制台中直接伪造并发送各种灾害类型预警数据。
 * 可用于实时校准群组卡片消息推送、防灾模版排版测试。
 * 
 * 核心流程与功能：
 * 1. 模拟参数拉取：启动后从服务端 `/api/simulation/params` 获取支持的模拟格式、预选数据源模版与默认经纬度值。
 * 2. 目标会话限制：允许定向群组测试或全网默认群组分流测试。
 * 3. 智能关联联动：切换测试格式（数据源模版）时，自动同步重设下方“数据源” key，并拉取该格式下的地理极值 defaults。
 * 4. 原生 IP 定位：提供 GPS 定位辅助功能，调取宿主 geoIP 服务，一键解析定位并填充经纬度与位置文本，无需手动输入。
 * 5. 各类型测试表单多态渲染：地震模式输入经纬震级深度，海啸模式输入灾害地点，气象预警模式输入通报全文。
 *
 * @param {Object} props
 * @param {boolean} props.open 模态框是否处于显露状态
 * @param {Function} props.onClose 模态框关闭指令回调
 */
function SimulationModal({ open, onClose }) {
    const statusApi = window.DisasterStatusApi;
    const { showToast } = useToast();
    
    // 表单状态控制
    const [disasterType, setDisasterType] = useState('earthquake');
    const [testType, setTestType] = useState('cea_fanstudio');
    const [targetGroup, setTargetGroup] = useState('');
    
    // 各项参数负载默认容器
    const [customParams, setCustomParams] = useState({
        latitude: 39.9,
        longitude: 116.4,
        magnitude: 5.5,
        depth: 10,
        location: '北京市',
        source: 'cea_fanstudio'
    });
    
    const [sending, setSending] = useState(false);
    const [params, setParams] = useState(null); // 后端支持的所有模拟参数详情

    // 每次 modal 打开时重载参数配置
    useEffect(() => {
        if (open) {
            loadParams();
        }
    }, [open]);

    // 联动副作用：测试模板格式改变时同步改写 customParams.source
    useEffect(() => {
        if (testType) {
            setCustomParams(prev => ({
                ...prev,
                source: testType
            }));
        }
    }, [testType]);

    /**
     * 规范化服务端下发的可选格式定义
     */
    const normalizeFormatOptions = (formats = []) => {
        if (!Array.isArray(formats)) return [];

        return formats
            .map((item) => {
                if (typeof item === 'string') {
                    return { value: item, label: item };
                }

                if (item && typeof item === 'object') {
                    const value = item.value || item.id || item.source || '';
                    const label = item.label || item.name || item.title || value;
                    if (value) {
                        return { value, label };
                    }
                }

                return null;
            })
            .filter(Boolean);
    };

    /**
     * 规范化模拟配置响应结构
     */
    const normalizeSimulationParams = (payload = {}) => {
        const disasterTypes = payload?.disaster_types || {};

        const normalizedDisasterTypes = Object.keys(disasterTypes).reduce((acc, typeKey) => {
            const typeData = disasterTypes[typeKey] || {};
            acc[typeKey] = {
                ...typeData,
                formats: normalizeFormatOptions(typeData.formats || typeData.test_formats || [])
            };
            return acc;
        }, {});

        return {
            ...payload,
            disaster_types: normalizedDisasterTypes
        };
    };

    /**
     * 加载后端模拟预警元数据选项，并自动回填初始默认值
     */
    const loadParams = async () => {
        try {
            const result = await statusApi.getSimulationParams();
            const normalizedResult = normalizeSimulationParams(result);
            setParams(normalizedResult);

            const typeKeys = Object.keys(normalizedResult?.disaster_types || {});
            if (typeKeys.length > 0) {
                const nextType = typeKeys[0];
                const typeData = normalizedResult.disaster_types[nextType] || {};
                const formats = normalizeFormatOptions(typeData.formats || []);
                const defaults = typeData.defaults || {};
                const nextTestType = formats[0]?.value || testType;

                setDisasterType(nextType);
                setTestType(nextTestType);
                setCustomParams(prev => ({
                    ...prev,
                    latitude: defaults.latitude ?? prev.latitude,
                    longitude: defaults.longitude ?? prev.longitude,
                    magnitude: defaults.magnitude ?? prev.magnitude,
                    depth: defaults.depth ?? prev.depth,
                    source: defaults.source || nextTestType || prev.source
                }));
            }
        } catch (e) {
            console.error('加载模拟参数失败', e);
        }
    };

    /**
     * 调用定位服务，解析本地 IP GPS 经纬度，一键回填参数行，简化调试输入
     */
    const handleGeolocate = async () => {
        try {
            const geoData = await statusApi.getGeoLocation();
            const { latitude, longitude, province, city } = geoData || {};
            if (latitude && longitude) {
                setCustomParams(prev => ({
                    ...prev,
                    latitude: latitude,
                    longitude: longitude,
                    location: `${province || ''} ${city || ''}`.trim() || prev.location
                }));
                return;
            }
            showToast('获取位置失败: 未返回有效坐标', 'error');
        } catch (e) {
            showToast(e.message || '获取位置失败', 'error');
            console.error(e);
        }
    };

    /**
     * 发送模拟测试指令请求
     */
    const handleSend = async () => {
        setSending(true);
        try {
            const result = await statusApi.sendSimulation({
                target_session: targetGroup,
                disaster_type: disasterType,
                test_type: testType,
                custom_params: customParams
            });

            showToast(result?.message || '预警消息已发送', 'success');
            onClose();
        } catch (e) {
            showToast(e.message || '请求失败,请检查控制台', 'error');
            console.error(e);
        } finally {
            setSending(false);
        }
    };

    // 表单选项生成器辅助
    const getDisasterTypeOptions = () => {
        if (!params) return [];
        return Object.keys(params.disaster_types || {});
    };

    const getTestTypeOptions = () => {
        if (!params || !disasterType) return [];
        const typeData = params.disaster_types[disasterType];
        return normalizeFormatOptions(typeData?.formats || typeData?.test_formats || []);
    };

    const getTargetSessionOptions = () => {
        if (!params || !params.target_sessions) return [];
        return params.target_sessions;
    };

    return (
        <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
            <DialogTitle>🧪 模拟预警测试</DialogTitle>
            <DialogContent>
                <Box className="simulation-modal-body">
                    {/* 1. 目标会话单选框 */}
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

                    {/* 2. 灾害大类单选 */}
                    <FormControl fullWidth size="small">
                        <InputLabel>灾害类型</InputLabel>
                        <Select
                            value={disasterType}
                            label="灾害类型"
                            onChange={(e) => {
                                const nextType = e.target.value;
                                const typeData = params?.disaster_types?.[nextType] || {};
                                const formats = normalizeFormatOptions(typeData.formats || typeData.test_formats || []);
                                const defaults = typeData.defaults || {};
                                const nextTestType = formats[0]?.value || '';

                                setDisasterType(nextType);
                                setTestType(nextTestType);
                                setCustomParams(prev => ({
                                    ...prev,
                                    latitude: defaults.latitude ?? prev.latitude,
                                    longitude: defaults.longitude ?? prev.longitude,
                                    magnitude: defaults.magnitude ?? prev.magnitude,
                                    depth: defaults.depth ?? prev.depth,
                                    source: defaults.source || nextTestType || prev.source
                                }));
                            }}
                            disabled // 目前后端仅完备地震模拟逻辑，因此强锁地震选项防止误操作
                        >
                            {getDisasterTypeOptions().map(type => (
                                <MenuItem key={type} value={type}>
                                    {params?.disaster_types?.[type]?.icon || ''} {params?.disaster_types?.[type]?.label || type}
                                </MenuItem>
                            ))}
                        </Select>
                        <Typography variant="caption" color="text.secondary" className="simulation-modal-hint">
                            目前仅支持地震模拟，其他灾害类型正在开发中
                        </Typography>
                    </FormControl>

                    {/* 3. 数据源模板格式选择 */}
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

                    {/* 4. 精细自定义参数区（多态呈现） */}
                    <Typography variant="subtitle2" className="simulation-modal-section-title">
                        自定义参数
                    </Typography>

                    {/* A. 地震模式专属表单 */}
                    {disasterType === 'earthquake' && (
                        <Box className="simulation-modal-form-stack">
                            {/* 经纬度、震级、深度合并定位行 */}
                            <Box className="simulation-modal-quake-row">
                                <TextField
                                    label="纬度"
                                    type="number"
                                    size="small"
                                    value={customParams.latitude}
                                    onChange={(e) => setCustomParams({ ...customParams, latitude: parseFloat(e.target.value) })}
                                    className="simulation-modal-field simulation-modal-field--geo"
                                />
                                <TextField
                                    label="经度"
                                    type="number"
                                    size="small"
                                    value={customParams.longitude}
                                    onChange={(e) => setCustomParams({ ...customParams, longitude: parseFloat(e.target.value) })}
                                    className="simulation-modal-field simulation-modal-field--geo"
                                />
                                {/* 一键 IP GPS 定位按钮 */}
                                <Tooltip title="使用当前 IP 自动定位填充经纬度">
                                    <IconButton onClick={handleGeolocate} color="primary" className="simulation-modal-geo-button">
                                        <span className="simulation-modal-geo-icon">📍</span>
                                    </IconButton>
                                </Tooltip>
                                <TextField
                                    label="震级 (M)"
                                    type="number"
                                    size="small"
                                    value={customParams.magnitude}
                                    onChange={(e) => setCustomParams({ ...customParams, magnitude: parseFloat(e.target.value) })}
                                    inputProps={{ min: 0, max: 10, step: 0.1 }}
                                    className="simulation-modal-field simulation-modal-field--metric"
                                />
                                <TextField
                                    label="深度 (km)"
                                    type="number"
                                    size="small"
                                    value={customParams.depth}
                                    onChange={(e) => setCustomParams({ ...customParams, depth: parseFloat(e.target.value) })}
                                    inputProps={{ min: 0, step: 1 }}
                                    className="simulation-modal-field simulation-modal-field--metric"
                                />
                            </Box>

                            {/* 震中地名输入 */}
                            <TextField
                                fullWidth
                                label="位置描述"
                                size="small"
                                value={customParams.location}
                                onChange={(e) => setCustomParams({ ...customParams, location: e.target.value })}
                            />

                            {/* 数据源名称绑定 */}
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

                    {/* B. 海啸模式备用表单 */}
                    {disasterType === 'tsunami' && (
                        <Box className="simulation-modal-form-stack">
                            <TextField
                                fullWidth
                                label="位置描述"
                                size="small"
                                value={customParams.location || ''}
                                onChange={(e) => setCustomParams({ ...customParams, location: e.target.value })}
                            />
                        </Box>
                    )}

                    {/* C. 气象警报备用表单 */}
                    {disasterType === 'weather' && (
                        <Box className="simulation-modal-form-stack">
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
            {/* 动作区 */}
            <DialogActions>
                <Button onClick={onClose}>取消</Button>
                <Button variant="contained" onClick={handleSend} disabled={sending || !testType}>
                    {sending ? '发送中...' : '📤 发送测试'}
                </Button>
            </DialogActions>
        </Dialog>
    );
}
