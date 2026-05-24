/**
 * 配置对象组渲染组件 (ConfigObjectGroup)
 * 用于将嵌套的 schema 节点（如 `strategies`, `weather_config`）渲染为一个美观的
 * 折叠手风琴面板 (Accordion)。面板标题会智能剔除开头的 Emoji 并绑定统一的预设配置图标，
 * 并在展开后递归生成该对象名下嵌套的所有子配置项组件。
 *
 * @param {Object} props
 * @param {string} props.fieldKey 配置字段名 (即当前对象组的 Key，如 'weather_config')
 * @param {Object} props.schema 包含该嵌套对象所有 items 定义的 schema
 * @param {Object} props.value 存储在当前层级下的 JSON 属性值
 * @param {Function} props.onChange 子配置变动时触发的回调，回传完整的 object 结构
 * @param {number} props.depth 嵌套深度 (0 代表根节点风琴面板，大于 0 则为子风琴面板)
 * @param {string} props.path 当前对象在整个配置树中的节点路径，用于控制折叠展开
 * @param {string[]} props.expandedKeys 全局已展开的节点路径数组
 * @param {Function} props.onToggleExpand 切换该节点折叠展开状态的回调函数
 */
function ConfigObjectGroup({ 
    fieldKey, 
    schema, 
    value, 
    onChange, 
    depth, 
    path, 
    expandedKeys, 
    onToggleExpand 
}) {
    const { Box, Typography, Accordion, AccordionSummary, AccordionDetails, Paper, Chip } = MaterialUI;
    const { CONFIG_ICONS, stripLeadingEmoji } = window.ConfigFieldLayout;
    
    // 判断当前嵌套路径是否处于展开状态
    const isExpanded = expandedKeys.includes(path);
    
    // 清理描述文本中自带的 Emoji，以便我们渲染我们自己挑选的统一图标
    const rawTitle = schema.description || fieldKey;
    const titleText = stripLeadingEmoji(rawTitle) || rawTitle;
    
    // 获取配置图标，若未匹配则默认使用齿轮图标 ⚙️
    const icon = CONFIG_ICONS[fieldKey] || '⚙️';
    
    // 强制保障 localValue 为 object 类型，防范空数据报错
    const localValue = value && typeof value === 'object' ? value : {};
    
    // 根配置组与嵌套配置组采用不同的 CSS 类名以应用不同的内边距与底色
    const depthClass = depth === 0 ? 'config-object-group--root' : 'config-object-group--nested';

    return (
        <Paper elevation={0} square={false} className={`config-object-group ${depthClass}`}>
            <Accordion 
                expanded={isExpanded} 
                onChange={() => onToggleExpand(path)} 
                elevation={0} 
                square={false} 
                disableGutters 
                className="config-object-accordion"
            >
                {/* 折叠栏头部摘要区域 */}
                <AccordionSummary
                    expandIcon={<Box className="config-object-expand-icon">{isExpanded ? '▲' : '▼'}</Box>}
                    className={`config-object-summary config-object-summary--depth-${Math.min(depth, 2)}`}
                >
                    <Box className="config-object-summary-content">
                        {/* 左侧大图标（根节点会进行高亮背景修饰） */}
                        <Box className={`config-object-icon ${depth === 0 ? 'config-object-icon--root' : ''}`}>
                            {icon}
                        </Box>
                        
                        {/* 中间标题与提示文本说明 */}
                        <Box className="config-object-title-block">
                            <Typography variant="subtitle2" className={`config-object-title ${depth === 0 ? 'config-object-title--root' : ''}`}>
                                {titleText}
                            </Typography>
                            {schema.hint && depth === 0 && (
                                <Typography variant="caption" color="text.secondary" className="config-object-hint">
                                    {schema.hint}
                                </Typography>
                            )}
                        </Box>
                        
                        {/* 右侧角标与控制状态提示 */}
                        <Box className="config-object-meta">
                            {/* 仅在首层渲染该配置组内所拥有的子项目总数角标 */}
                            {depth === 0 && (
                                <Chip
                                    label={`${Object.keys(schema.items).length}项`}
                                    size="small"
                                    color="primary"
                                    variant="outlined"
                                    className="config-object-count-chip"
                                />
                            )}
                            {/* 嵌套深层仅渲染展开/收起文字提示 */}
                            {depth > 0 && (
                                <Typography variant="caption" className="config-object-toggle-caption">
                                    {isExpanded ? '收起' : '展开'}
                                </Typography>
                            )}
                        </Box>
                    </Box>
                </AccordionSummary>
                
                {/* 展开后的嵌套子项列表 */}
                <AccordionDetails className="config-object-details">
                    <Box className="config-object-children">
                        {Object.entries(schema.items).map(([key, subSchema]) => (
                            <ConfigField
                                key={key}
                                fieldKey={key}
                                schema={subSchema}
                                value={localValue?.[key]}
                                // 当某个嵌套子项数据变更时，浅拷贝父级对象并覆盖对应的 Key，然后向上传递
                                onChange={(newValue) => onChange({ ...localValue, [key]: newValue })}
                                depth={depth + 1}
                                path={path}
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

// 注册到全局以便被 ConfigField.jsx 引用
window.ConfigObjectGroup = ConfigObjectGroup;
