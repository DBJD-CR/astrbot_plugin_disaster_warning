const { Box, TextField, Switch, FormControlLabel, Typography, Button, Accordion, AccordionSummary, AccordionDetails, Divider, Paper, Chip, Slider, MenuItem, ToggleButton, ToggleButtonGroup } = MaterialUI;
const { useState, useEffect, useRef, useLayoutEffect } = React;

// 辅助函数：获取所有可展开的路径
const getAllExpandablePaths = (schema, prefix = '') => {
    let paths = [];
    Object.entries(schema).forEach(([key, value]) => {
        const currentPath = prefix ? `${prefix}.${key}` : key;
        if (value.type === 'object' && value.items) {
            paths.push(currentPath);
            paths = paths.concat(getAllExpandablePaths(value.items, currentPath));
        }
    });
    return paths;
};

// 为不同配置类型定义图标
const CONFIG_ICONS = {
    enabled: '🔌',
    admin_users: '👥',
    target_sessions: '📨',
    display_timezone: '🌍',
    data_sources: '📡',
    local_monitoring: '📍',
    earthquake_filters: '🔍',
    strategies: '🧠',
    push_frequency_control: '⏱️',
    message_format: '🎨',
    weather_config: '⛈️',
    websocket_config: '🔌',
    web_admin: '💻',
    debug_config: '🐛',
    telemetry_config: '📊',
};

const LEADING_EMOJI_REGEX = /^\s*(?:\p{Extended_Pictographic}(?:\uFE0F|\u200D\p{Extended_Pictographic})*)\s*/u;

const stripLeadingEmoji = (text) => {
    if (typeof text !== 'string') return text;
    return text.replace(LEADING_EMOJI_REGEX, '').trimStart();
};

/**
 * 配置字段渲染组件
 * 根据后端返回的 Schema 动态渲染不同类型的输入控件
 *
 * @param {Object} props
 * @param {string} props.fieldKey - 字段键名
 * @param {Object} props.schema - 字段 Schema 定义
 * @param {any} props.value - 当前值
 * @param {Function} props.onChange - 值变更回调
 * @param {number} props.depth - 嵌套深度 (用于缩进和样式)
 * @param {string} props.path - 当前字段路径
 * @param {Array} props.expandedKeys - 已展开的路径列表
 * @param {Function} props.onToggleExpand - 切换展开状态的回调
 */
function ConfigField({ fieldKey, schema, value, onChange, depth = 0, path = '', expandedKeys = [], onToggleExpand = () => {} }) {
    const [localValue, setLocalValue] = useState(value);

    useEffect(() => {
        setLocalValue(value);
    }, [value]);

    const handleChange = (newValue) => {
        setLocalValue(newValue);
        onChange(newValue);
    };

    const rawTitle = schema.description || fieldKey;
    const titleText = stripLeadingEmoji(rawTitle) || rawTitle;
    const icon = CONFIG_ICONS[fieldKey] || '⚙️';
    const currentPath = path ? `${path}.${fieldKey}` : fieldKey;

    // 对象类型 (后端使用 'object' + 'items')
    if (schema.type === 'object' && schema.items) {
        const isExpanded = expandedKeys.includes(currentPath);

        return (
            <Paper
                elevation={depth === 0 ? 2 : 0}
                sx={{
                    my: depth === 0 ? 1 : 0.75,
                    overflow: 'hidden',
                    border: depth === 0 ? 1.5 : 1,
                    borderColor: depth === 0 ? 'primary.main' : 'primary.light',
                    borderRadius: 2,
                    background: depth === 0
                        ? 'linear-gradient(135deg, rgba(0, 90, 193, 0.04) 0%, rgba(0, 90, 193, 0.01) 100%)'
                        : 'transparent'
                }}
            >
                <Accordion
                    expanded={isExpanded}
                    onChange={() => onToggleExpand(currentPath)}
                    elevation={0}
                    sx={{
                        '&:before': { display: 'none' },
                        bgcolor: 'transparent'
                    }}
                >
                    <AccordionSummary
                        expandIcon={
                            <Box sx={{
                                fontSize: '14px',
                                transform: 'rotate(0deg)',
                                transition: 'transform 0.2s',
                                '.Mui-expanded &': { transform: 'rotate(180deg)' }
                            }}>
                                ▼
                            </Box>
                        }
                        sx={{
                            px: 2,
                            py: 1,
                            minHeight: '48px !important',
                            bgcolor: depth === 0 ? 'rgba(0, 90, 193, 0.06)' : depth === 1 ? 'rgba(0, 90, 193, 0.02)' : 'transparent',
                            '&:hover': {
                                bgcolor: depth === 0 ? 'rgba(0, 90, 193, 0.1)' : 'rgba(0, 90, 193, 0.05)'
                            },
                            transition: 'all 0.2s ease'
                        }}
                    >
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flex: 1 }}>
                            <Box sx={{ fontSize: depth === 0 ? '20px' : '16px' }}>{icon}</Box>
                            <Box sx={{ flex: 1 }}>
                                <Typography
                                    variant="subtitle2"
                                    sx={{
                                        fontWeight: 700,
                                        color: depth === 0 ? 'primary.main' : depth > 0 ? 'primary.dark' : 'text.primary',
                                        fontSize: depth === 0 ? '0.95rem' : '0.875rem'
                                    }}
                                >
                                    {titleText}
                                </Typography>
                                {schema.hint && depth === 0 && (
                                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
                                        {schema.hint}
                                    </Typography>
                                )}
                            </Box>
                            {depth === 0 && (
                                <Chip
                                    label={`${Object.keys(schema.items).length}项`}
                                    size="small"
                                    color="primary"
                                    variant="outlined"
                                    sx={{ height: 22, fontSize: '0.7rem' }}
                                />
                            )}
                            {depth > 0 && (
                                <Typography variant="caption" sx={{ color: 'primary.main', fontWeight: 600, mr: 0.5 }}>
                                    {isExpanded ? '收起' : '展开'}
                                </Typography>
                            )}
                        </Box>
                    </AccordionSummary>
                    <AccordionDetails sx={{ px: 3, py: 0, bgcolor: 'background.default' }}>
                        <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                            {Object.entries(schema.items).map(([key, subSchema]) => (
                                <ConfigField
                                    key={key}
                                    fieldKey={key}
                                    schema={subSchema}
                                    value={localValue?.[key]}
                                    onChange={(newValue) => handleChange({ ...localValue, [key]: newValue })}
                                    depth={depth + 1}
                                    path={currentPath}
                                    expandedKeys={expandedKeys}
                                    onToggleExpand={onToggleExpand}
                                />
                            ))}
                        </Box>
                    </AccordionDetails>
                </Accordion>
            </Paper>
        );
    }

    // 公共描述区域组件
    const DescriptionSection = ({ flex = 8 }) => (
        <Box sx={{ flex: flex, pr: 2, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'text.primary', fontSize: '0.9rem', lineHeight: 1.3 }}>
                {schema.description || fieldKey}
            </Typography>
            {schema.hint && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, lineHeight: 1.3 }}>
                    {schema.hint}
                </Typography>
            )}
        </Box>
    );

    // 布尔类型 (后端使用 'bool')
    if (schema.type === 'bool' || schema.type === 'boolean') {
        return (
            <Box sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                py: 1.5,
                borderBottom: depth === 0 ? 'none' : '1px solid',
                borderColor: 'divider',
                '&:last-child': { borderBottom: 'none' }
            }}>
                <DescriptionSection flex={8} />
                <Box sx={{ flex: 2, display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
                    <Switch
                        checked={localValue !== undefined ? localValue : (schema.default || false)}
                        onChange={(e) => handleChange(e.target.checked)}
                        sx={{
                            width: 52,
                            height: 32,
                            padding: 0,
                            '& .MuiSwitch-switchBase': {
                                padding: 0,
                                margin: '4px',
                                transitionDuration: '300ms',
                                '&.Mui-checked': {
                                    transform: 'translateX(20px)',
                                    color: '#fff',
                                    '& + .MuiSwitch-track': {
                                        backgroundColor: 'primary.main',
                                        opacity: 1,
                                        border: 0,
                                    },
                                },
                            },
                            '& .MuiSwitch-thumb': {
                                boxSizing: 'border-box',
                                width: 24,
                                height: 24,
                                boxShadow: '0 2px 4px rgba(0, 0, 0, 0.2)',
                            },
                            '& .MuiSwitch-track': {
                                borderRadius: 16,
                                backgroundColor: 'rgba(0, 0, 0, 0.12)',
                                opacity: 1,
                                transition: 'background-color 300ms',
                            },
                        }}
                    />
                </Box>
            </Box>
        );
    }

    // 数值类型 (int/float)
    if (['integer', 'int', 'number', 'float', 'double'].includes(schema.type)) {
        const sliderConfig = schema.slider;
        const hasRange = sliderConfig !== undefined;
        // 如果有范围，展示 Slider，布局 5:3:2；否则回退到 8:2
        const descFlex = hasRange ? 5 : 8;
        
        const min = sliderConfig?.min ?? schema.minimum;
        const max = sliderConfig?.max ?? schema.maximum;
        const step = sliderConfig?.step ?? (schema.type === 'integer' || schema.type === 'int' ? 1 : 0.1);

        return (
            <Box sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                py: 1.5,
                borderBottom: depth === 0 ? 'none' : '1px solid',
                borderColor: 'divider',
                '&:last-child': { borderBottom: 'none' }
            }}>
                <DescriptionSection flex={descFlex} />
                
                {hasRange && (
                    <Box sx={{ flex: 3, px: 2, display: 'flex', alignItems: 'center' }}>
                        <Slider
                            value={Number(localValue) || 0}
                            onChange={(e, newValue) => setLocalValue(newValue)}
                            onChangeCommitted={(e, newValue) => handleChange(newValue)}
                            min={min}
                            max={max}
                            step={step}
                            size="small"
                            valueLabelDisplay="auto"
                            sx={{ color: 'primary.main' }}
                        />
                    </Box>
                )}

                <Box sx={{ flex: 2, display: 'flex', justifyContent: 'flex-end' }}>
                    <TextField
                        fullWidth
                        size="small"
                        type="number"
                        value={localValue !== undefined ? localValue : (schema.default || 0)}
                        onChange={(e) => {
                            const v = e.target.value;
                            // 允许输入空值或负号
                            if (v === '' || v === '-') {
                                setLocalValue(v);
                                return;
                            }
                            const num = schema.type === 'integer' || schema.type === 'int' ? parseInt(v) : parseFloat(v);
                            handleChange(isNaN(num) ? 0 : num);
                        }}
                        inputProps={{
                            min: min,
                            max: max,
                            step: step
                        }}
                        variant="outlined"
                        sx={{
                            '& .MuiOutlinedInput-root': {
                                borderRadius: 1.5,
                                bgcolor: 'background.paper',
                                '&.Mui-focused > fieldset': { borderColor: 'primary.main' }
                            }
                        }}
                    />
                </Box>
            </Box>
        );
    }

    // 列表类型 (后端使用 'list')
    if (schema.type === 'list' || schema.type === 'array') {
        return (
            <Box sx={{
                py: 1.5,
                borderBottom: depth === 0 ? 'none' : '1px solid',
                borderColor: 'divider',
                '&:last-child': { borderBottom: 'none' }
            }}>
                <Box sx={{ mb: 1 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'text.primary', fontSize: '0.9rem' }}>
                        {schema.description || fieldKey}
                    </Typography>
                    {schema.hint && (
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                            {schema.hint}
                        </Typography>
                    )}
                </Box>
                <TextField
                    fullWidth
                    multiline
                    rows={3}
                    size="small"
                    value={Array.isArray(localValue) ? localValue.join('\n') : ''}
                    onChange={(e) => handleChange(e.target.value.split('\n'))}
                    placeholder="每行一项"
                    variant="outlined"
                    sx={{
                        '& .MuiOutlinedInput-root': {
                            borderRadius: 1.5,
                            bgcolor: 'background.paper',
                            '&.Mui-focused > fieldset': { borderColor: 'primary.main' }
                        }
                    }}
                />
            </Box>
        );
    }

    // 带有选项的类型 (Select)
    if (schema.options && Array.isArray(schema.options)) {
        return (
            <Box sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                py: 1.5,
                borderBottom: depth === 0 ? 'none' : '1px solid',
                borderColor: 'divider',
                '&:last-child': { borderBottom: 'none' }
            }}>
                <DescriptionSection flex={8} />
                <Box sx={{ flex: 2, display: 'flex', justifyContent: 'flex-end' }}>
                    <TextField
                        select
                        fullWidth
                        size="small"
                        value={localValue !== undefined ? localValue : (schema.default || '')}
                        onChange={(e) => handleChange(e.target.value)}
                        variant="outlined"
                        SelectProps={{
                            MenuProps: {
                                PaperProps: {
                                    sx: {
                                        borderRadius: 1.5,
                                        mt: 0.5,
                                        boxShadow: '0 4px 16px rgba(0,0,0,0.1)'
                                    }
                                }
                            }
                        }}
                        sx={{
                            '& .MuiOutlinedInput-root': {
                                borderRadius: 1.5,
                                bgcolor: 'background.paper',
                                '&.Mui-focused > fieldset': { borderColor: 'primary.main' }
                            },
                            '& .MuiSelect-select': {
                                textAlign: 'center',
                                pr: '32px !important' // 给箭头图标留出空间，确保视觉居中
                            }
                        }}
                    >
                        {schema.options.map((option) => (
                            <MenuItem key={option} value={option} sx={{ justifyContent: 'center' }}>
                                {option}
                            </MenuItem>
                        ))}
                    </TextField>
                </Box>
            </Box>
        );
    }

    // 字符串类型(默认)
    // 判断是否应该使用多行输入
    const shouldBeMultiline =
        (schema.hint && schema.hint.length > 100) ||
        fieldKey.includes('format') ||
        fieldKey.includes('template') ||
        fieldKey.includes('pattern') ||
        fieldKey.includes('message') ||
        fieldKey.includes('body') ||
        fieldKey.includes('content');
    
    // 如果是长文本，保持上下布局；否则使用 8:2 布局
    if (shouldBeMultiline) {
        return (
            <Box sx={{
                py: 1.5,
                borderBottom: depth === 0 ? 'none' : '1px solid',
                borderColor: 'divider',
                '&:last-child': { borderBottom: 'none' }
            }}>
                <Box sx={{ mb: 1 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'text.primary', fontSize: '0.9rem' }}>
                        {schema.description || fieldKey}
                    </Typography>
                    {schema.hint && (
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                            {schema.hint}
                        </Typography>
                    )}
                </Box>
                <TextField
                    fullWidth
                    multiline
                    rows={3}
                    value={localValue !== undefined ? localValue : (schema.default || '')}
                    onChange={(e) => handleChange(e.target.value)}
                    variant="outlined"
                    sx={{
                        '& .MuiOutlinedInput-root': {
                            borderRadius: 1.5,
                            bgcolor: 'background.paper',
                            '&.Mui-focused > fieldset': { borderColor: 'primary.main' }
                        }
                    }}
                />
            </Box>
        );
    }

    return (
        <Box sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            py: 1.5,
            borderBottom: depth === 0 ? 'none' : '1px solid',
            borderColor: 'divider',
            '&:last-child': { borderBottom: 'none' }
        }}>
            <DescriptionSection flex={8} />
            <Box sx={{ flex: 2, display: 'flex', justifyContent: 'flex-end' }}>
                <TextField
                    fullWidth
                    size="small"
                    value={localValue !== undefined ? localValue : (schema.default || '')}
                    onChange={(e) => handleChange(e.target.value)}
                    variant="outlined"
                    sx={{
                        '& .MuiOutlinedInput-root': {
                            borderRadius: 1.5,
                            bgcolor: 'background.paper',
                            '&.Mui-focused > fieldset': { borderColor: 'primary.main' }
                        }
                    }}
                />
            </Box>
        </Box>
    );
}

/**
 * 主配置渲染器组件
 * 负责加载、显示和保存插件的完整配置
 * 包含了配置的获取、状态管理和保存逻辑
 */
function ConfigRenderer() {
    const { showToast } = useToast();
    const [schema, setSchema] = useState(null);
    const [config, setConfig] = useState(null);
    const [expandedKeys, setExpandedKeys] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    // 多会话模式相关状态
    const [mode, setMode] = useState('global'); // global | session
    const [sessions, setSessions] = useState([]);
    const [selectedSession, setSelectedSession] = useState('');
    const [sessionLoading, setSessionLoading] = useState(false);

    const api = useApi();
    const scrollContainerRef = useRef(null);
    const loadConfigSeqRef = useRef(0);

    // 动态缓存 key，避免全局与会话配置草稿互相覆盖
    const getDraftKey = (currentMode = mode, currentSession = selectedSession) => {
        if (currentMode === 'session' && currentSession) {
            return `astrbot_plugin_dw_draft_config_session_${currentSession}`;
        }
        return 'astrbot_plugin_dw_draft_config_global';
    };

    const getExpandedKey = (currentMode = mode, currentSession = selectedSession) => {
        if (currentMode === 'session' && currentSession) {
            return `astrbot_plugin_dw_expanded_keys_session_${currentSession}`;
        }
        return 'astrbot_plugin_dw_expanded_keys_global';
    };

    const getScrollKey = (currentMode = mode, currentSession = selectedSession) => {
        if (currentMode === 'session' && currentSession) {
            return `astrbot_scroll_config_list_session_${currentSession}`;
        }
        return 'astrbot_scroll_config_list_global';
    };

    useEffect(() => {
        initializePage();
    }, []);

    useEffect(() => {
        if (!schema) return;
        loadConfig(mode, selectedSession);
    }, [mode, selectedSession]);

    // 滚动位置恢复
    useLayoutEffect(() => {
        if (!loading && scrollContainerRef.current) {
            const savedPos = localStorage.getItem(getScrollKey());
            if (savedPos) {
                // 尝试恢复
                const pos = parseInt(savedPos, 10);
                if (pos > 0) {
                    scrollContainerRef.current.scrollTop = pos;
                    // 双重保障
                    requestAnimationFrame(() => {
                        if (scrollContainerRef.current) {
                            scrollContainerRef.current.scrollTop = pos;
                        }
                    });
                }
            }
        }
    }, [loading, mode, selectedSession]);

    // 监听滚动保存
    useEffect(() => {
        const el = scrollContainerRef.current;
        if (!el || loading) return;

        const handleScroll = () => {
            localStorage.setItem(getScrollKey(), el.scrollTop);
        };

        let timeout;
        const debouncedScroll = () => {
            clearTimeout(timeout);
            timeout = setTimeout(handleScroll, 100);
        };

        el.addEventListener('scroll', debouncedScroll);
        return () => {
            el.removeEventListener('scroll', debouncedScroll);
            clearTimeout(timeout);
        };
    }, [loading, mode, selectedSession]);

    // 自动保存草稿
    useEffect(() => {
        if (config) {
            localStorage.setItem(getDraftKey(), JSON.stringify(config));
        }
    }, [config, mode, selectedSession]);

    // 自动保存展开状态
    useEffect(() => {
        if (schema) { // 确保 schema 加载后再保存，避免初始化时的空状态覆盖
            localStorage.setItem(getExpandedKey(), JSON.stringify(expandedKeys));
        }
    }, [expandedKeys, schema, mode, selectedSession]);

    const initializePage = async () => {
        setLoading(true);
        try {
            const schemaData = await api.getConfigSchema();
            setSchema(schemaData);

            await loadSessions();
        } catch (e) {
            console.error('初始化配置页失败', e);
            showToast('初始化配置页失败,请检查控制台', 'error');
        } finally {
            setLoading(false);
        }
    };

    const loadSessions = async () => {
        try {
            const result = await api.listSessionConfigs();
            const sessionList = result?.sessions || [];
            setSessions(sessionList);

            // 默认选中第一个会话
            if (!selectedSession && sessionList.length > 0) {
                setSelectedSession(sessionList[0].session);
            }
        } catch (e) {
            console.error('加载会话列表失败', e);
            showToast('加载会话列表失败,请检查控制台', 'error');
        }
    };

    const loadConfig = async (currentMode = mode, currentSession = selectedSession) => {
        if (!schema) return;

        const requestSeq = ++loadConfigSeqRef.current;
        setLoading(true);
        try {
            let configData = null;

            if (currentMode === 'session') {
                if (!currentSession) {
                    if (requestSeq === loadConfigSeqRef.current) {
                        setConfig(null);
                    }
                    return;
                }
                setSessionLoading(true);
                const sessionData = await api.getSessionConfig(currentSession);
                configData = sessionData?.effective || {};
            } else {
                configData = await api.getFullConfig();
            }

            // 如果不是最新请求，丢弃过期响应，避免会话串改
            if (requestSeq !== loadConfigSeqRef.current) {
                return;
            }

            // 1. 处理配置记忆 (草稿)
            // 会话模式以服务端 effective 为准，避免本地草稿造成会话间污染
            let finalConfig = configData;
            if (currentMode === 'global') {
                const draftConfigStr = localStorage.getItem(getDraftKey(currentMode, currentSession));
                if (draftConfigStr) {
                    try {
                        const draftConfig = JSON.parse(draftConfigStr);
                        // 简单校验：如果草稿是对象且不为空，则使用草稿
                        if (draftConfig && typeof draftConfig === 'object') {
                            finalConfig = draftConfig;
                            console.log('已恢复本地草稿配置');
                        }
                    } catch (e) {
                        console.error('解析草稿配置失败', e);
                    }
                }
            }

            // 2. 处理展开状态记忆
            const cachedExpandedStr = localStorage.getItem(getExpandedKey(currentMode, currentSession));
            let finalExpandedKeys = [];
            if (cachedExpandedStr) {
                try {
                    finalExpandedKeys = JSON.parse(cachedExpandedStr);
                } catch (e) {
                    console.error('解析展开状态失败', e);
                }
            } else {
                // 默认全展开
                finalExpandedKeys = getAllExpandablePaths(schema);
            }

            setConfig(finalConfig);
            setExpandedKeys(finalExpandedKeys);
        } catch (e) {
            if (requestSeq === loadConfigSeqRef.current) {
                console.error('加载配置失败', e);
                showToast('加载配置失败,请检查控制台', 'error');
                setConfig(null);
            }
        } finally {
            if (requestSeq === loadConfigSeqRef.current) {
                setSessionLoading(false);
                setLoading(false);
            }
        }
    };

    const handleToggleExpand = (path) => {
        setExpandedKeys(prev => {
            if (prev.includes(path)) {
                return prev.filter(p => p !== path);
            } else {
                return [...prev, path];
            }
        });
    };

    const handleToggleAll = () => {
        if (expandedKeys.length > 0) {
            setExpandedKeys([]); // 全部收起
        } else {
            setExpandedKeys(getAllExpandablePaths(schema)); // 全部展开
        }
    };

    const cleanConfig = (obj) => {
        if (Array.isArray(obj)) {
            return obj
                .map(item => typeof item === 'string' ? item.trim() : item)
                .filter(item => item !== '');
        }
        if (obj && typeof obj === 'object') {
            const newObj = {};
            for (const key in obj) {
                newObj[key] = cleanConfig(obj[key]);
            }
            return newObj;
        }
        return obj;
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            const cleanedConfig = cleanConfig(config);
            const currentMode = mode;
            const currentSession = selectedSession;

            if (currentMode === 'session') {
                if (!currentSession) {
                    showToast('请先选择会话', 'warning');
                    return;
                }
                await api.updateSessionConfig(currentSession, {
                    mode: 'effective',
                    effective: cleanedConfig
                });
                showToast('会话差异配置已保存', 'success');
                await loadSessions();
                // 会话模式保存后强制回读服务端 effective，确保会话隔离与覆写状态显示正确
                await loadConfig(currentMode, currentSession);
            } else {
                await api.updateConfig(cleanedConfig);
                showToast('全局配置已保存', 'success');
                setConfig(cleanedConfig); // 全局模式可直接更新界面
                localStorage.setItem(getDraftKey(currentMode, currentSession), JSON.stringify(cleanedConfig));
            }
        } catch (e) {
            console.error('保存配置失败', e);
            showToast('保存配置失败,请检查控制台', 'error');
        } finally {
            setSaving(false);
        }
    };

    const handleResetOverride = async () => {
        if (!selectedSession) {
            showToast('请先选择会话', 'warning');
            return;
        }

        const ok = confirm('确定要清空该会话的差异配置吗？\n\n清空后将完全继承全局默认配置。');
        if (!ok) return;

        setSaving(true);
        try {
            await api.resetSessionConfig(selectedSession);
            showToast('会话差异配置已清空', 'success');
            localStorage.removeItem(getDraftKey(mode, selectedSession));
            await loadSessions();
            await loadConfig(mode, selectedSession);
        } catch (e) {
            console.error('清空会话差异配置失败', e);
            showToast('清空会话差异配置失败', 'error');
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <Box sx={{ textAlign: 'center', py: 6 }}>
                <Box sx={{ fontSize: '36px', mb: 1.5 }}>⚙️</Box>
                <Typography variant="body1" color="text.secondary">加载配置中...</Typography>
            </Box>
        );
    }

    if (!schema || !config) {
        return (
            <Box sx={{ textAlign: 'center', py: 6 }}>
                <Box sx={{ fontSize: '36px', mb: 1.5 }}>❌</Box>
                <Typography variant="body1" color="error">无法加载配置</Typography>
            </Box>
        );
    }

    const selectedSessionMeta = sessions.find(s => s.session === selectedSession);

    return (
        <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
            {/* 顶部模式与会话选择栏 */}
            <Box sx={{ px: 3, pt: 2, pb: 1, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
                    <ToggleButtonGroup
                        exclusive
                        size="small"
                        value={mode}
                        onChange={(e, val) => {
                            if (!val) return;
                            setMode(val);
                        }}
                    >
                        <ToggleButton value="global">全局配置</ToggleButton>
                        <ToggleButton value="session">会话差异配置</ToggleButton>
                    </ToggleButtonGroup>

                    {mode === 'session' && (
                        <>
                            <TextField
                                select
                                size="small"
                                label="目标会话"
                                value={selectedSession}
                                onChange={(e) => setSelectedSession(e.target.value)}
                                sx={{ minWidth: 420, maxWidth: '100%' }}
                            >
                                {sessions.map((item) => (
                                    <MenuItem key={item.session} value={item.session}>
                                        {item.session}
                                    </MenuItem>
                                ))}
                            </TextField>
                            {selectedSessionMeta?.has_override && (
                                <Chip size="small" color="primary" label="已存在差异覆写" />
                            )}
                            {sessionLoading && (
                                <Typography variant="caption" color="text.secondary">会话配置加载中...</Typography>
                            )}
                        </>
                    )}
                </Box>

                {mode === 'session' && selectedSessionMeta && (
                    <Typography variant="caption" color="text.secondary">
                        当前会话：{selectedSessionMeta.session} ｜ push_enabled：{selectedSessionMeta.push_enabled ? '开启' : '关闭'} ｜ override字段：{(selectedSessionMeta.override_keys || []).join(', ') || '无'}
                    </Typography>
                )}
            </Box>

            {/* 配置项列表 */}
            <Box
                ref={scrollContainerRef}
                sx={{
                    flex: 1,
                    overflowY: 'auto',
                    px: 3,
                    py: 2,
                '&::-webkit-scrollbar': {
                    width: '6px',
                },
                '&::-webkit-scrollbar-track': {
                    bgcolor: 'background.default',
                    borderRadius: 3,
                },
                '&::-webkit-scrollbar-thumb': {
                    bgcolor: 'primary.main',
                    borderRadius: 3,
                    '&:hover': {
                        bgcolor: 'primary.dark',
                    }
                }
            }}>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    {Object.entries(schema).map(([key, subSchema]) => (
                        <Box key={key} sx={{ width: '100%' }}>
                            <ConfigField
                                fieldKey={key}
                                schema={subSchema}
                                value={config[key]}
                                onChange={(newValue) => setConfig({ ...config, [key]: newValue })}
                                path=""
                                expandedKeys={expandedKeys}
                                onToggleExpand={handleToggleExpand}
                            />
                        </Box>
                    ))}
                </Box>
            </Box>

            {/* 底部操作栏 */}
            <Box sx={{
                flexShrink: 0,
                bgcolor: 'var(--md-sys-color-surface)', // 使用主题表面色
                backdropFilter: 'blur(8px)',
                borderTop: '1px solid',
                borderColor: 'divider',
                px: 3,
                py: 2,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                boxShadow: '0 -4px 20px rgba(0, 0, 0, 0.05)',
                zIndex: 10
            }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
                        {Object.keys(schema).length} 个配置组
                    </Typography>
                    <Button
                        onClick={handleToggleAll}
                        size="small"
                        variant="text"
                        sx={{ minWidth: 'auto', px: 1 }}
                    >
                        {expandedKeys.length > 0 ? '全部收起' : '全部展开'}
                    </Button>
                </Box>
                <Box sx={{ display: 'flex', gap: 1.5 }}>
                    <Button
                        onClick={() => {
                            if (confirm('⚠️ 确定要恢复出厂设置吗？\n\n这将覆盖当前所有配置项为默认值（需要点击“保存配置”才能生效）。')) {
                                const generateDefaults = (s) => {
                                    const c = {};
                                    Object.entries(s).forEach(([k, v]) => {
                                        if (v.type === 'object' && v.items) {
                                            c[k] = generateDefaults(v.items);
                                        } else {
                                            c[k] = v.default !== undefined ? v.default : null;
                                        }
                                    });
                                    return c;
                                };
                                
                                const defaults = generateDefaults(schema);
                                setConfig(defaults);
                                localStorage.removeItem(getDraftKey());
                            }
                        }}
                        disabled={saving}
                        variant="outlined"
                        color="error"
                        size="medium"
                        startIcon={<span>🗑️</span>}
                        sx={{
                            minWidth: 100,
                            borderRadius: 2,
                            borderWidth: 1.5,
                            fontSize: '0.875rem',
                            '&:hover': { borderWidth: 1.5 }
                        }}
                    >
                        恢复默认
                    </Button>
                    <Button
                        onClick={() => {
                            if (confirm('确定要撤销所有未保存的更改吗？\n\n这将重新加载服务器上已保存的配置。')) {
                                localStorage.removeItem(getDraftKey());
                                loadConfig();
                            }
                        }}
                        disabled={saving}
                        variant="outlined"
                        size="medium"
                        startIcon={<span>↩️</span>}
                        sx={{
                            minWidth: 100,
                            borderRadius: 2,
                            borderWidth: 1.5,
                            fontSize: '0.875rem',
                            '&:hover': { borderWidth: 1.5 }
                        }}
                    >
                        撤销更改
                    </Button>
                    {mode === 'session' && (
                        <Button
                            onClick={handleResetOverride}
                            disabled={saving || !selectedSession}
                            variant="outlined"
                            color="warning"
                            size="medium"
                            startIcon={<span>♻️</span>}
                            sx={{
                                minWidth: 130,
                                borderRadius: 2,
                                borderWidth: 1.5,
                                fontSize: '0.875rem',
                                '&:hover': { borderWidth: 1.5 }
                            }}
                        >
                            清空会话覆写
                        </Button>
                    )}
                    <Button
                        variant="contained"
                        onClick={handleSave}
                        disabled={saving}
                        size="medium"
                        startIcon={<span>💾</span>}
                        sx={{
                            minWidth: 120,
                            borderRadius: 2,
                            fontSize: '0.875rem',
                            boxShadow: '0 2px 8px rgba(0, 90, 193, 0.3)',
                            '&:hover': {
                                boxShadow: '0 4px 12px rgba(0, 90, 193, 0.4)',
                            }
                        }}
                    >
                        {saving ? '保存中...' : (mode === 'session' ? '保存会话配置' : '保存配置')}
                    </Button>
                </Box>
            </Box>
        </Box>
    );
}
