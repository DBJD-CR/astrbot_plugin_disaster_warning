const { Typography } = MaterialUI;

/**
 * 气象与海啸预警特定层级判色选项配置
 */
const EVENT_LEVEL_FILTER_CONFIG = {
    weather: {
        label: '预警颜色',
        allLabel: '全部颜色',
        options: [
            { value: 'weather_white', label: '白色' },
            { value: 'weather_blue', label: '蓝色' },
            { value: 'weather_yellow', label: '黄色' },
            { value: 'weather_orange', label: '橙色' },
            { value: 'weather_red', label: '红色' },
        ],
    },
    tsunami: {
        label: '海啸级别',
        allLabel: '全部级别',
        options: [
            { value: 'tsunami_info', label: '信息' },
            { value: 'tsunami_warning', label: '预警' },
        ],
    },
};

/**
 * 事件多维过滤器头部组件 (EventFilters)
 * 渲染于事件记录视图的顶部。提供以下高级过滤功能：
 * 1. 事件大类切换胶囊栏（全部、地震预警、地震速报、气象、海啸）。
 * 2. 震级限制过滤与震级排序（支持升降序）/ 预警危险颜色筛选。
 * 3. 动态加载可用数据源（支持单选下拉、多选 checkbox 下拉详情菜单）。
 * 4. 全局地点与文本关键字搜索框。
 *
 * @param {Object} props
 * @param {number} props.total 当前符合过滤条件的事件记录总数
 * @param {string} props.filterType 选中的大分类 ID
 * @param {Function} props.setFilterType 修改大分类的回调
 * @param {string} props.magnitudeFilter 选中的震级/颜色级别过滤值
 * @param {Function} props.setMagnitudeFilter 修改级别过滤的回调
 * @param {string} props.magnitudeOrder 震级排序模式 ('default' | 'desc' | 'asc')
 * @param {Function} props.setMagnitudeOrder 变更震级排序的回调
 * @param {string} props.keyword 关键词搜索文本值
 * @param {Function} props.setKeyword 变更关键词的回调
 * @param {Array} props.availableSources 可供筛选的规范化数据源列表
 * @param {string} props.sourceFilterMode 数据源筛选模式 ('single' 单选 | 'multi' 多选)
 * @param {Function} props.onSourceFilterModeChange 修改数据源筛选模式的回调
 * @param {string[]} props.selectedSources 已选中的数据源标识数组
 * @param {Function} props.onSourceSelectChange 单选模式下切换数据源的回调
 * @param {Function} props.onSourceCheckboxToggle 多选模式下勾选/取消勾选单个数据源的回调
 * @param {Function} props.setSelectedSources 强制覆盖已选数据源数组的回调
 * @param {string} props.selectedSourceSummary 数据源已选择项数目的摘要提示文案
 */
function EventFilters({
    total,
    filterType,
    setFilterType,
    magnitudeFilter,
    setMagnitudeFilter,
    magnitudeOrder,
    setMagnitudeOrder,
    keyword,
    setKeyword,
    availableSources,
    sourceFilterMode,
    onSourceFilterModeChange,
    selectedSources,
    onSourceSelectChange,
    onSourceCheckboxToggle,
    setSelectedSources,
    selectedSourceSummary,
}) {
    // 指向多选 dropdown details 元素的 ref，以便点击页面外部时自动折叠下拉框
    const detailsRef = React.useRef(null);

    React.useEffect(() => {
        const handleClickOutside = (event) => {
            if (detailsRef.current && !detailsRef.current.contains(event.target)) {
                // 点击组件外区域，移去 open 属性关闭 HTML5 details 面板
                detailsRef.current.removeAttribute('open');
            }
        };

        document.addEventListener('click', handleClickOutside);
        return () => {
            document.removeEventListener('click', handleClickOutside);
        };
    }, []);

    // 顶层事件胶囊大类定义
    const eventTypes = [
        { id: 'all', label: '全部' },
        { id: 'earthquake_warning', label: '地震预警' },
        { id: 'earthquake', label: '地震情报' },
        { id: 'weather', label: '气象预警' },
        { id: 'tsunami', label: '海啸预警' },
    ];

    // 根据所选模式，动态映射右侧多维过滤选项
    const levelFilterConfig = EVENT_LEVEL_FILTER_CONFIG[filterType] || null;
    const magnitudeFilterLabel = levelFilterConfig ? levelFilterConfig.label : '震级';
    const magnitudeFilterOptions = levelFilterConfig
        ? [{ value: 'all', label: levelFilterConfig.allLabel }, ...levelFilterConfig.options]
        : [
            { value: 'all', label: '全部震级' },
            { value: '3', label: 'M ≥ 3.0' },
            { value: '4', label: 'M ≥ 4.0' },
            { value: '5', label: 'M ≥ 5.0' },
            { value: '6', label: 'M ≥ 6.0' },
            { value: '7', label: 'M ≥ 7.0' },
            { value: '8', label: 'M ≥ 8.0' },
        ];

    return (
        <div className="events-filters-header">
            {/* 顶排：标题与匹配总条数统计 */}
            <div className="events-filters-title-row">
                <div className="events-filters-title-group">
                    <Typography variant="h5" className="events-filters-title">最近事件记录</Typography>
                    {total > 0 && <Typography variant="body2" className="events-filters-total">共 {total} 条</Typography>}
                </div>
            </div>

            {/* 下排：过滤器交互控制台 */}
            <div className="event-filters-toolbar">
                {/* 1. 过滤流：事件大类胶囊过滤排 */}
                <div className="event-filters-primary-row">
                    <div className="event-filters-primary-label">事件类型</div>
                    <div className="filter-group event-filter-group-nowrap event-filter-type-group">
                        {eventTypes.map((item) => (
                            <button
                                key={item.id}
                                className={`btn-filter event-filter-pill ${filterType === item.id ? 'active' : ''}`}
                                onClick={() => {
                                    // 切换大类，同时重置震级过滤与震级排序，以防交叉污染
                                    setFilterType(item.id);
                                    setMagnitudeFilter('all');
                                    setMagnitudeOrder('default');
                                }}
                            >
                                {filterType === item.id && <span className="event-filter-checkmark">✓</span>}
                                {item.label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* 2. 细粒度过滤与搜索排 */}
                <div className="event-filters-secondary-row">
                    {/* A. 震级限制与排序 / 颜色预警过滤选择器 */}
                    <div className="filter-group event-filter-group-nowrap event-filter-field-group event-filter-field-card event-filter-field-card-magnitude">
                        <Typography variant="body2" className="event-filter-label">{magnitudeFilterLabel}</Typography>
                        <div className="event-filter-inline-controls">
                            <select value={magnitudeFilter} onChange={(e) => setMagnitudeFilter(e.target.value)} className="event-filter-select event-filter-select-md">
                                {magnitudeFilterOptions.map((option) => (
                                    <option key={option.value} value={option.value}>{option.label}</option>
                                ))}
                            </select>
                            {/* 仅在非气象/非海啸等地震速报模式下才显示“震级排序”选择器 */}
                            {!levelFilterConfig && (
                                <select value={magnitudeOrder} onChange={(e) => setMagnitudeOrder(e.target.value)} className="event-filter-select event-filter-select-md">
                                    <option value="default">默认排序</option>
                                    <option value="desc">震级降序</option>
                                    <option value="asc">震级升序</option>
                                </select>
                            )}
                        </div>
                    </div>

                    {/* B. 数据源过滤 (支持单选与多选模式) */}
                    {availableSources.length > 0 && (
                        <div className="filter-group event-filter-group-nowrap event-filter-field-group event-filter-field-card event-filter-field-card-source">
                            <Typography variant="body2" className="event-filter-label">数据源</Typography>
                            <div className="event-filter-inline-controls event-filter-inline-controls-source">
                                {/* 选择单/多选模式开关 */}
                                <select value={sourceFilterMode} onChange={(e) => onSourceFilterModeChange(e.target.value)} className="event-filter-select event-filter-select-sm">
                                    <option value="single">单选</option>
                                    <option value="multi">多选</option>
                                </select>
                                
                                {sourceFilterMode === 'single' ? (
                                    // 单选模式：标准的 HTML Select 下拉菜单
                                    <select value={selectedSources[0] || ''} onChange={onSourceSelectChange} className="event-filter-select event-filter-source-select">
                                        <option value="">全部数据源</option>
                                        {availableSources.map((source) => (
                                            <option key={source.normalizedKey} value={source.value} title={source.label}>
                                                {source.label}
                                            </option>
                                        ))}
                                    </select>
                                ) : (
                                    // 多选模式：细节折叠面板，实现 Checkbox 复选菜单
                                    <details ref={detailsRef} className="event-filter-source-details">
                                        <summary className="event-filter-source-summary">
                                            {selectedSourceSummary}
                                        </summary>
                                        <div className="event-filter-source-menu">
                                            {/* 重置清除所有勾选 */}
                                            <label className="event-filter-checkbox-label">
                                                <input type="checkbox" checked={selectedSources.length === 0} onChange={() => setSelectedSources([])} />
                                                全部数据源
                                            </label>
                                            {/* 各数据源选项复选框 */}
                                            {availableSources.map((source) => (
                                                <label key={source.normalizedKey} className="event-filter-checkbox-label event-filter-checkbox-label-lg">
                                                    <input 
                                                        type="checkbox" 
                                                        checked={selectedSources.includes(source.value)} 
                                                        onChange={() => onSourceCheckboxToggle(source.value)} 
                                                    />
                                                    {source.label}
                                                </label>
                                            ))}
                                        </div>
                                    </details>
                                )}
                            </div>
                        </div>
                    )}

                    {/* C. 文本/地点关键字模糊检索输入框 */}
                    <div className="filter-group event-filter-group-nowrap event-filter-field-group event-filter-field-card event-filter-field-card-keyword">
                        <Typography variant="body2" className="event-filter-label">关键词</Typography>
                        <div className="event-filter-inline-controls event-filter-inline-controls-keyword">
                            <input
                                value={keyword}
                                onChange={(e) => setKeyword(e.target.value)}
                                placeholder="搜索地点、标题、来源..."
                                className="event-filter-select event-filter-keyword-input"
                            />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
