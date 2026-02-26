const {Box, Typography, Collapse, CircularProgress} = MaterialUI;
const {useState, useMemo, useEffect, useCallback, useRef} = React;

/**
 * 事件列表组件
 * 展示地震、海啸、气象预警等各类事件列表
 * 提供了按事件类型筛选、按事件ID分组以及折叠历史更新记录的功能
 * 数据通过分页 API 从数据库直接拉取
 */
function EventsList() {
    const {state} = useAppContext();
    const {config} = state;
    const displayTimezone = config.displayTimezone || 'UTC+8';
    const [filterType, setFilterType] = useState('all');
    const [expandedEvents, setExpandedEvents] = useState(new Set());

    // 分页状态
    const [currentPage, setCurrentPage] = useState(1);
    const [totalPages, setTotalPages] = useState(0);
    const [total, setTotal] = useState(0);
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(false);
    const [pageSize, setPageSize] = useState(50);
    const [pageInput, setPageInput] = useState('');
    const [sourceFilterMode, setSourceFilterMode] = useState('single'); // single | multi
    const [selectedSources, setSelectedSources] = useState([]);
    const [sourceOptions, setSourceOptions] = useState([]);

    // 持有当前进行中请求的 AbortController，新请求发起时 abort 旧请求
    const abortControllerRef = useRef(null);

    const fetchEvents = useCallback((page, type, limit, sources = []) => {
        // 取消上一个尚未完成的请求
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        const controller = new AbortController();
        abortControllerRef.current = controller;

        const safeLimit = Number(limit) > 0 ? Number(limit) : 50;

        setLoading(true);
        const typeParam = type === 'all' ? '' : type;
        // 将前端 filter key 映射为后端的 type 值
        const typeMap = {
            'earthquake_warning': 'earthquake_warning',
            'earthquake': 'earthquake',
            'tsunami': 'tsunami',
            'weather': 'weather_alarm',
        };
        const apiType = typeMap[type] || typeParam;
        const normalizedSources = Array.isArray(sources)
            ? sources.map(s => (s || '').trim()).filter(Boolean)
            : [];
        const sourceParam = normalizedSources.length > 0
            ? `&source=${encodeURIComponent(normalizedSources.join(','))}`
            : '';
        fetch(`/api/events?page=${page}&limit=${safeLimit}${apiType ? `&type=${apiType}` : ''}${sourceParam}`, {signal: controller.signal})
            .then(res => res.json())
            .then(data => {
                setEvents(Array.isArray(data.events) ? data.events : []);
                setTotal(data.total || 0);
                setTotalPages(data.total_pages || 0);
                setSourceOptions(Array.isArray(data.sources) ? data.sources : []);
                setLoading(false);
            })
            .catch(err => {
                if (err.name === 'AbortError') return;
                console.error('Failed to fetch events:', err);
                setLoading(false);
            });
    }, []);

    // 切换筛选类型、每页数量或数据源筛选时重置到第1页
    useEffect(() => {
        setCurrentPage(1);
        setPageInput('');
        fetchEvents(1, filterType, pageSize, selectedSources);
    }, [filterType, pageSize, selectedSources, fetchEvents]);

    // 用 ref 追踪最新 filterType / pageSize，供新事件触发的刷新使用，
    // 避免引入它们为依赖导致双重请求
    const filterTypeRef = useRef(filterType);
    const pageSizeRef = useRef(pageSize);
    const selectedSourcesRef = useRef(selectedSources);
    useEffect(() => {
        filterTypeRef.current = filterType;
        pageSizeRef.current = pageSize;
        selectedSourcesRef.current = selectedSources;
    });

    // WebSocket 收到新事件时，回到第1页刷新（始终用当前筛选条件与每页大小）
    useEffect(() => {
        if (!state.wsConnected) return;
        setCurrentPage(1);
        setPageInput('');
        fetchEvents(1, filterTypeRef.current, pageSizeRef.current, selectedSourcesRef.current);
    }, [state.events, state.wsConnected, fetchEvents]);

    const availableSources = useMemo(() => {
        return (Array.isArray(sourceOptions) ? sourceOptions : [])
            .map(s => (s || '').trim())
            .filter(Boolean)
            .sort((a, b) => {
                const aName = formatSourceName(a);
                const bName = formatSourceName(b);
                return aName.localeCompare(bName, 'zh-CN');
            });
    }, [sourceOptions]);

    useEffect(() => {
        if (selectedSources.length === 0) return;
        const validSet = new Set(availableSources);
        const nextSelected = selectedSources.filter(source => validSet.has(source));
        if (nextSelected.length !== selectedSources.length) {
            setSelectedSources(nextSelected);
        }
    }, [availableSources, selectedSources]);

    const filteredEvents = useMemo(() => {
        return Array.isArray(events) ? events : [];
    }, [events]);

    const getEventTimeMs = (event) => {
        const parsed = parseEventTimeToDate(event?.time || event?.timestamp, event?.source || '');
        return parsed ? parsed.getTime() : 0;
    };

    // 将扁平的事件列表按照 event_id 进行分组
    // 这样可以将同一事件的多次更新（如：第1报、第2报...最终报）聚合在一起显示
    const groupedEvents = useMemo(() => {
        const groups = {};

        for (const evt of filteredEvents) {
            // 尝试获取唯一事件ID，如果不存在则使用 时间-描述 作为临时ID
            const eventId = evt.event_id || evt.id || `${evt.time}-${evt.description}`;
            if (!groups[eventId]) {
                groups[eventId] = {
                    id: eventId,
                    events: [],
                    latestEvent: null
                };
            }
            groups[eventId].events.push(evt);
        }

        // 处理每个分组：排序、计算更新数量、合并历史记录
        for (const id in groups) {
            // 按时间倒序排列，最新的在最前
            groups[id].events.sort((a, b) => getEventTimeMs(b) - getEventTimeMs(a));
            groups[id].latestEvent = groups[id].events[0];

            // 计算更新总数：
            // 优先使用后端返回的 update_count (注意：是下划线命名)
            // 如果后端未返回，则回退使用前端聚合的数组长度
            const backendCount = groups[id].latestEvent.update_count || 0;
            groups[id].updateCount = Math.max(groups[id].events.length, backendCount);

            // 合并后端返回的 'history' 字段 (如果有)
            // 这是一个补充机制，确保即使 WebSocket 只推了最新一条，前端展开时也能看到之前的记录
            if (groups[id].latestEvent.history && Array.isArray(groups[id].latestEvent.history)) {
                // 过滤掉已存在的事件 (避免重复显示)
                // 注意：不能只按 time 去重。地震多报常共享同一发震时间，
                // 若仅用 time，会把不同报次（第2报、第3报...）误判为重复。
                const buildDedupKey = (evt) => {
                    if (!evt || typeof evt !== 'object') return 'invalid';

                    // 1) 优先使用后端更新表主键（event_updates.id）
                    if (evt.id !== undefined && evt.id !== null && evt.id !== '') {
                        return `upd-id:${evt.id}`;
                    }

                    // 2) 其次使用源事件ID（通常在同一数据源内稳定）
                    if (evt.source_event_id) {
                        return `src-evt:${evt.source_event_id}`;
                    }

                    // 3) 再其次使用 report_num + time（报次语义）
                    if (evt.report_num !== undefined && evt.report_num !== null && evt.report_num !== '') {
                        return `report:${evt.report_num}|time:${evt.time || evt.timestamp || ''}`;
                    }

                    // 4) 最后使用多字段组合兜底，降低误判
                    return [
                        evt.time || evt.timestamp || '',
                        evt.magnitude ?? '',
                        evt.depth ?? '',
                        evt.description || ''
                    ].join('|');
                };

                const existingKeys = new Set(groups[id].events.map(e => buildDedupKey(e)));
                const historyEvents = groups[id].latestEvent.history.filter((h) => {
                    const key = buildDedupKey(h);
                    if (existingKeys.has(key)) return false;
                    existingKeys.add(key);
                    return true;
                });

                if (historyEvents.length > 0) {
                    groups[id].events.push(...historyEvents);
                    // 合并后再次重新排序
                    groups[id].events.sort((a, b) => getEventTimeMs(b) - getEventTimeMs(a));
                    // 更新计数
                    groups[id].updateCount = Math.max(groups[id].events.length, backendCount);
                }
            }
        }

        // 将分组转换为数组，并按最新事件的时间倒序排列（最近发生的事件排在列表顶部）
        return Object.values(groups).sort((a, b) =>
            getEventTimeMs(b.latestEvent) - getEventTimeMs(a.latestEvent)
        );
    }, [filteredEvents]);

    const toggleEventGroup = (groupId) => {
        setExpandedEvents(prev => {
            const newSet = new Set(prev);
            if (newSet.has(groupId)) {
                newSet.delete(groupId);
            } else {
                newSet.add(groupId);
            }
            return newSet;
        });
    };

    const goToPage = useCallback((targetPage) => {
        if (totalPages <= 0) return;
        const safePage = Math.max(1, Math.min(totalPages, targetPage));
        if (safePage === currentPage) return;

        setCurrentPage(safePage);
        setPageInput('');
        fetchEvents(safePage, filterType, pageSize, selectedSources);
    }, [currentPage, totalPages, fetchEvents, filterType, pageSize, selectedSources]);

    const paginationItems = useMemo(() => {
        if (totalPages <= 0) return [];

        if (totalPages <= 7) {
            return Array.from({length: totalPages}, (_, idx) => idx + 1);
        }

        const items = [1];
        const start = Math.max(2, currentPage - 1);
        const end = Math.min(totalPages - 1, currentPage + 1);

        if (start > 2) {
            items.push('ellipsis-left');
        }

        for (let p = start; p <= end; p += 1) {
            items.push(p);
        }

        if (end < totalPages - 1) {
            items.push('ellipsis-right');
        }

        items.push(totalPages);
        return items;
    }, [currentPage, totalPages]);

    const pageInputNumber = Number(pageInput);
    const canJump = Number.isInteger(pageInputNumber)
        && pageInputNumber >= 1
        && pageInputNumber <= Math.max(totalPages, 1)
        && pageInputNumber !== currentPage;

    const handlePageJump = () => {
        if (!canJump) return;
        goToPage(pageInputNumber);
    };

    const handleSourceFilterModeChange = (mode) => {
        setSourceFilterMode(mode);
        if (mode === 'single' && selectedSources.length > 1) {
            setSelectedSources([selectedSources[0]]);
        }
    };

    const handleSourceSelectChange = (e) => {
        const value = (e.target.value || '').trim();
        setSelectedSources(value ? [value] : []);
    };

    const handleSourceCheckboxToggle = (source) => {
        setSelectedSources((prev) => {
            if (prev.includes(source)) {
                return prev.filter(item => item !== source);
            }
            return [...prev, source];
        });
    };

    const selectedSourceSummary = useMemo(() => {
        if (selectedSources.length === 0) return '全部数据源';
        return `已选 ${selectedSources.length} 个数据源`;
    }, [selectedSources]);

    const isLikelyJmaSource = (source = '') => {
        const sourceKey = String(source || '').toLowerCase();
        if (!sourceKey) return false;
        return sourceKey.includes('jma') || sourceKey.includes('p2p') || sourceKey.includes('cwa');
    };

    const normalizeEarthquakeTitle = (evt) => {
        const rawTitle = String(evt?.description || '').trim();
        if (!rawTitle) return '未知位置';

        // 识别并剥离前缀震级，避免与左侧震级徽章重复显示
        // 例如："M5.0 日向滩" -> "日向滩"
        // 特殊值："MNone 未知地点" / "MNaN 未知地点" -> 进一步语义化处理
        const magPrefixMatch = rawTitle.match(/^M\s*([^\s]+)\s*(.*)$/i);
        if (magPrefixMatch) {
            const [, magTokenRaw, restRaw] = magPrefixMatch;
            const magToken = String(magTokenRaw || '').toLowerCase();
            const rest = String(restRaw || '').trim();

            const invalidMagToken = ['none', 'nan', '--', 'null', 'undefined'].includes(magToken);
            const unknownPlace = !rest || rest === '未知地点' || rest === '未知位置';
            if (invalidMagToken && unknownPlace) {
                return isLikelyJmaSource(evt?.source)
                    ? '震度速报（震源参数调查中）'
                    : '震源参数调查中';
            }

            if (rest) return rest;
        }

        return rawTitle;
    };

    const formatMagnitudeBadge = (mag) => {
        if (mag === null || mag === undefined || mag === '') return '--';
        const num = Number(mag);
        return Number.isFinite(num) ? num.toFixed(1) : '--';
    };

    const formatShindoBadge = (level) => {
        if (level === null || level === undefined || level === '') return null;

        const raw = String(level).trim();
        if (!raw) return null;

        const normalized = raw
            .replace(/弱/g, '-')
            .replace(/強/g, '+')
            .replace(/强/g, '+')
            .replace(/\s+/g, '');

        if (['1', '2', '3', '4', '5-', '5+', '6-', '6+', '7'].includes(normalized)) {
            return normalized;
        }

        const num = Number(level);
        if (!Number.isFinite(num)) return null;

        if (num < 1.5) return '1';
        if (num < 2.5) return '2';
        if (num < 3.5) return '3';
        if (num < 4.5) return '4';
        if (num < 5.0) return '5-';
        if (num < 5.5) return '5+';
        if (num < 6.0) return '6-';
        if (num < 6.5) return '6+';
        return '7';
    };

    const formatIntensityBadge = (level) => {
        if (level === null || level === undefined || level === '') return null;
        const num = Number(level);
        if (!Number.isFinite(num)) return null;

        // 烈度通常展示为 1-12
        const rounded = Math.round(num);
        if (rounded >= 1 && rounded <= 12) return String(rounded);
        return num.toFixed(1);
    };

    const INT_COLOR_MAP = {
        '1': '#6B7878',
        '2': '#1E6EE6',
        '3': '#32B464',
        '4': '#FFE05D',
        '5-': '#FFAA13',
        '5+': '#EF700F',
        '6-': '#E60000',
        '6+': '#A00000',
        '7': '#5D0090',
        'unknown': '#6B7878'
    };

    const getIntensityColor = (levelText, isJmaScale) => {
        if (!levelText) return INT_COLOR_MAP.unknown;
        if (isJmaScale) {
            return INT_COLOR_MAP[levelText] || INT_COLOR_MAP.unknown;
        }

        const n = Number(levelText);
        if (!Number.isFinite(n)) return INT_COLOR_MAP.unknown;
        if (n <= 2) return INT_COLOR_MAP['1'];
        if (n <= 4) return INT_COLOR_MAP['2'];
        if (n <= 5) return INT_COLOR_MAP['3'];
        if (n <= 6) return INT_COLOR_MAP['4'];
        if (n <= 8) return INT_COLOR_MAP['5-'];
        if (n <= 10) return INT_COLOR_MAP['6-'];
        return INT_COLOR_MAP['7'];
    };

    const getEarthquakeBadgeContent = (evt) => {
        const source = evt?.source || '';
        const level = evt?.level;
        const isJmaScale = isLikelyJmaSource(source);

        if (isJmaScale) {
            const shindo = formatShindoBadge(level);
            if (shindo) {
                return {
                    text: shindo,
                    label: '震度',
                    background: getIntensityColor(shindo, true),
                    color: shindo === '4' ? '#2b2b2b' : '#ffffff'
                };
            }
        } else {
            const intensity = formatIntensityBadge(level);
            if (intensity) {
                const color = Number(intensity) === 6 ? '#2b2b2b' : '#ffffff';
                return {
                    text: intensity,
                    label: '烈度',
                    background: getIntensityColor(intensity, false),
                    color
                };
            }
        }

        const mag = evt?.magnitude ?? evt?._groupMagnitude;
        const magText = formatMagnitudeBadge(mag);
        return {
            text: magText,
            label: '震级',
            background: '#6B7878',
            color: '#ffffff'
        };
    };

    const buildEarthquakeTitle = (evt) => {
        const normalizedTitle = normalizeEarthquakeTitle(evt);
        if (!normalizedTitle) return '未知位置';

        // 对“调查中”类标题不强行追加震级
        if (normalizedTitle.includes('调查中')) {
            return normalizedTitle;
        }

        const mag = evt?.magnitude ?? evt?._groupMagnitude;
        const magText = formatMagnitudeBadge(mag);
        if (magText === '--') {
            return normalizedTitle;
        }

        return `M ${magText} ${normalizedTitle}`;
    };

    const renderEventCard = (evt, isHistory = false, isExpandable = false, isExpanded = false, reportIndex = null) => {
        const eventType = evt.type || evt._groupType || '';
        const isEarthquake = eventType === 'earthquake' || eventType === 'earthquake_warning';
        const isTsunami = eventType === 'tsunami';
        const isWeather = eventType === 'weather_alarm';
        const displayTitle = isEarthquake
            ? buildEarthquakeTitle(evt)
            : (isWeather ? (evt.subtitle || evt.description || '未知位置') : (evt.description || '未知位置'));

        let badgeContent = '❓';
        let badgeClass = 'badge-unknown';
        let weatherIconUrl = null;
        let earthquakeBadgeMeta = null;

        if (isEarthquake) {
            earthquakeBadgeMeta = getEarthquakeBadgeContent(evt);
            badgeContent = earthquakeBadgeMeta?.text || '--';
            badgeClass = 'badge-earthquake';
        } else if (isTsunami) {
            badgeContent = '🌊';
            badgeClass = 'badge-tsunami';
        } else if (isWeather) {
            badgeContent = '☁️';
            badgeClass = 'badge-weather';
            // 尝试构建气象预警图标 URL
            // 优先从 weather_type_code (后端统计字段) 获取，其次尝试 raw_data
            const pCode = evt.weather_type_code || evt.raw_data?.type || evt.data?.type;
            if (pCode) {
                weatherIconUrl = `https://image.nmc.cn/assets/img/alarm/${pCode}.png`;
            }
        }

        // 计算报数显示
        let reportLabel = '';
        if (reportIndex !== null && reportIndex > 0) {
            // 历史记录：显示为 "第X报"
            reportLabel = `第 ${reportIndex} 报`;
        } else if (evt.report_num) {
            // 最新记录：如果后端提供了 report_num，使用它
            reportLabel = `第 ${evt.report_num} 报`;
        }

        return (
            <div className={`event-card ${isExpandable ? 'clickable' : ''}`} style={{
                marginBottom: isHistory ? '4px' : '0',
                padding: isHistory ? '12px 20px' : '',
                position: 'relative'
            }}>
                <div className={`mag-badge ${badgeClass}`} style={{
                    width: isHistory ? '40px' : '56px',
                    height: isHistory ? '40px' : '56px',
                    fontSize: isHistory ? '14px' : '18px',
                    overflow: earthquakeBadgeMeta ? 'hidden' : 'visible',
                    padding: weatherIconUrl ? 0 : undefined,
                    borderRadius: weatherIconUrl
                        ? '0'
                        : (earthquakeBadgeMeta ? (isHistory ? '10px' : '12px') : '50%'),
                    backgroundColor: weatherIconUrl
                        ? 'transparent'
                        : (earthquakeBadgeMeta?.background || '#6B7878'),
                    boxShadow: weatherIconUrl ? 'none' : (earthquakeBadgeMeta ? '0 2px 8px rgba(0,0,0,0.16)' : undefined),
                    color: earthquakeBadgeMeta?.color || undefined,
                    position: 'relative',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    lineHeight: 1
                }}>
                    {weatherIconUrl ? (
                        <img
                            src={weatherIconUrl}
                            alt={badgeContent}
                            style={{
                                width: '100%',
                                height: '100%',
                                objectFit: 'contain',
                                transform: 'scale(1.5)' // 放大显示，因为原图标可能有留白
                            }}
                            onError={(e) => {
                                e.target.style.display = 'none';
                                // 图片加载失败时恢复背景色和阴影 (通过修改父元素样式较为复杂，这里简单处理)
                                e.target.parentElement.style.backgroundColor = 'var(--md-sys-color-surface-variant)';
                            }}
                        />
                    ) : earthquakeBadgeMeta ? (
                        <>
                            <span style={{
                                position: 'absolute',
                                top: 0,
                                left: 0,
                                width: '100%',
                                height: isHistory ? '10px' : '12px',
                                lineHeight: isHistory ? '10px' : '12px',
                                textAlign: 'center',
                                fontSize: isHistory ? '8px' : '9px',
                                fontWeight: 600,
                                color: 'rgba(255,255,255,0.88)',
                                background: 'rgba(0,0,0,0.18)',
                                letterSpacing: '0.2px'
                            }}>
                                {earthquakeBadgeMeta.label}
                            </span>
                            <span style={{
                                paddingTop: isHistory ? '6px' : '8px',
                                fontWeight: 800,
                                fontSize: isHistory ? '18px' : '28px',
                                textShadow: '0 1px 2px rgba(0,0,0,0.25)'
                            }}>
                                {badgeContent}
                            </span>
                        </>
                    ) : (
                        badgeContent
                    )}
                </div>

                <div className="event-main">
                    <div style={{display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px'}}>
                        <Typography variant={isHistory ? "body2" : "h6"} sx={{fontWeight: 700, color: 'text.primary'}}>
                            {displayTitle}
                        </Typography>
                        {reportLabel && (
                            <span style={{
                                fontSize: isHistory ? '11px' : '12px',
                                fontWeight: 600,
                                padding: '2px 8px',
                                borderRadius: '4px',
                                background: reportIndex !== null && reportIndex > 0
                                    ? 'rgba(0,0,0,0.06)'
                                    : 'var(--md-sys-color-primary-container)',
                                color: reportIndex !== null && reportIndex > 0
                                    ? 'inherit'
                                    : 'var(--md-sys-color-on-primary-container)',
                                opacity: 0.9
                            }}>
                                {reportLabel}
                            </span>
                        )}
                    </div>
                    <div className="event-meta"
                         style={{opacity: 0.6, display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '8px'}}>
                        <span style={{display: 'inline-flex', alignItems: 'center', gap: '6px'}}>
                            🕒 {formatTimeFriendly(evt.time || evt.timestamp, displayTimezone, evt.source || '')}
                        </span>
                        <span style={{display: 'inline-flex', alignItems: 'center', gap: '6px'}}>
                            <span style={{opacity: 0.5}}>•</span>
                            📡 {formatSourceName(evt.source)}
                        </span>
                    </div>
                </div>

                {isExpandable && (
                    <div className="update-badge">
                        <span className="update-count">{isExpanded ? '收起' : `${evt.updateCount || ''} 条更新`}</span>
                        <span className="update-icon">{isExpanded ? '▲' : '▼'}</span>
                    </div>
                )}
            </div>
        );
    };

    return (
        <Box sx={{my: 2}}>
            <Box sx={{
                display: 'flex',
                justifyContent: 'flex-start',
                alignItems: 'center',
                mb: 4,
                flexWrap: 'wrap',
                gap: 2
            }}>
                <Box sx={{display: 'flex', alignItems: 'center', gap: 1.5}}>
                    <Typography variant="h5" sx={{fontWeight: 800, letterSpacing: '-0.5px', color: 'text.primary'}}>
                        最近事件记录
                    </Typography>
                    {total > 0 && (
                        <Typography variant="body2" sx={{opacity: 0.5, fontSize: '0.85rem'}}>
                            共 {total} 条
                        </Typography>
                    )}
                </Box>

                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    flexWrap: 'nowrap',
                    minWidth: 0
                }}>
                    <div className="filter-group" style={{flexWrap: 'nowrap'}}>
                        {[
                            {id: 'all', label: '全部'},
                            {id: 'earthquake_warning', label: '地震预警'},
                            {id: 'earthquake', label: '地震情报'},
                            {id: 'weather', label: '气象预警'},
                            {id: 'tsunami', label: '海啸预警'}
                        ].map(item => (
                            <button
                                key={item.id}
                                className={`btn-filter ${filterType === item.id ? 'active' : ''}`}
                                onClick={() => setFilterType(item.id)}
                            >
                                {filterType === item.id && <span style={{fontSize: '12px'}}>✓</span>}
                                {item.label}
                            </button>
                        ))}
                    </div>

                    {availableSources.length > 0 && (
                        <div className="filter-group" style={{
                            flexWrap: 'nowrap',
                            alignItems: 'center',
                            gap: '8px',
                            whiteSpace: 'nowrap',
                            minWidth: 0
                        }}>
                            <Typography variant="body2" sx={{opacity: 0.65, alignSelf: 'center', mr: 0.5}}>
                                数据源
                            </Typography>

                            <select
                                value={sourceFilterMode}
                                onChange={(e) => handleSourceFilterModeChange(e.target.value)}
                                style={{
                                    border: '1px solid var(--md-sys-color-outline-variant)',
                                    borderRadius: '8px',
                                    padding: '6px 10px',
                                    background: 'var(--md-sys-color-surface)',
                                    color: 'inherit',
                                    fontSize: '13px',
                                    fontWeight: 600,
                                    minWidth: '76px',
                                    width: '76px'
                                }}
                            >
                                <option value="single">单选</option>
                                <option value="multi">多选</option>
                            </select>

                            {sourceFilterMode === 'single' ? (
                                <select
                                    value={selectedSources[0] || ''}
                                    onChange={handleSourceSelectChange}
                                    style={{
                                        border: '1px solid var(--md-sys-color-outline-variant)',
                                        borderRadius: '8px',
                                        padding: '6px 10px',
                                        background: 'var(--md-sys-color-surface)',
                                        color: 'inherit',
                                        fontSize: '13px',
                                        width: '220px',
                                        minWidth: '220px',
                                        maxWidth: '220px',
                                        boxSizing: 'border-box'
                                    }}
                                >
                                    <option value="">全部数据源</option>
                                    {availableSources.map((source) => (
                                        <option key={source} value={source} title={source}>
                                            {formatSourceName(source)}
                                        </option>
                                    ))}
                                </select>
                            ) : (
                                <details style={{
                                    position: 'relative',
                                    width: '220px',
                                    minWidth: '220px',
                                    maxWidth: '220px',
                                    flex: '0 0 220px',
                                    overflow: 'visible',
                                    zIndex: 5
                                }}>
                                    <summary style={{
                                        listStyle: 'none',
                                        cursor: 'pointer',
                                        border: '1px solid var(--md-sys-color-outline-variant)',
                                        borderRadius: '8px',
                                        padding: '6px 10px',
                                        background: 'var(--md-sys-color-surface)',
                                        fontSize: '13px',
                                        userSelect: 'none',
                                        width: '100%',
                                        boxSizing: 'border-box',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        whiteSpace: 'nowrap'
                                    }}>
                                        {selectedSourceSummary}
                                    </summary>
                                    <div style={{
                                        position: 'absolute',
                                        top: 'calc(100% + 6px)',
                                        left: 0,
                                        width: '220px',
                                        minWidth: '220px',
                                        maxWidth: '220px',
                                        maxHeight: '260px',
                                        overflowY: 'auto',
                                        border: '1px solid var(--md-sys-color-outline-variant)',
                                        borderRadius: '10px',
                                        padding: '8px 10px',
                                        boxSizing: 'border-box',
                                        background: 'var(--md-sys-color-surface)',
                                        boxShadow: '0 8px 20px rgba(0,0,0,0.12)',
                                        zIndex: 30
                                    }}>
                                        <label style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '8px',
                                            marginBottom: '8px',
                                            fontSize: '12px',
                                            opacity: 0.8
                                        }}>
                                            <input
                                                type="checkbox"
                                                checked={selectedSources.length === 0}
                                                onChange={() => setSelectedSources([])}
                                            />
                                            全部数据源
                                        </label>
                                        {availableSources.map((source) => (
                                            <label key={source} style={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: '8px',
                                                marginBottom: '6px',
                                                fontSize: '13px'
                                            }}>
                                                <input
                                                    type="checkbox"
                                                    checked={selectedSources.includes(source)}
                                                    onChange={() => handleSourceCheckboxToggle(source)}
                                                />
                                                {formatSourceName(source)}
                                            </label>
                                        ))}
                                    </div>
                                </details>
                            )}
                        </div>
                    )}
                </div>
            </Box>

            {loading ? (
                <div className="card" style={{textAlign: 'center', padding: '60px'}}>
                    <CircularProgress size={32}/>
                </div>
            ) : groupedEvents.length === 0 ? (
                <div className="card" style={{textAlign: 'center', padding: '80px'}}>
                    <Typography variant="h2" sx={{opacity: 0.1, mb: 2}}>📭</Typography>
                    <Typography variant="body1" sx={{opacity: 0.5}}>暂无该类型的事件记录</Typography>
                    <Typography variant="body2" sx={{opacity: 0.3, mt: 1, fontSize: '0.8rem'}}>
                        系统正在持续监测中...
                    </Typography>
                </div>
            ) : (
                <>
                    <div className="events-scroll-window">
                        <div className="events-list">
                            {groupedEvents.map((group) => {
                                const isExpanded = expandedEvents.has(group.id);
                                const totalReports = group.events.length;

                                return (
                                    <div key={group.id} className="event-group">
                                        {/* 折叠状态：只显示最新一条 */}
                                        {!isExpanded && (
                                            <div onClick={() => group.updateCount > 1 && toggleEventGroup(group.id)}>
                                                {renderEventCard(
                                                    {
                                                        ...group.latestEvent,
                                                        updateCount: group.updateCount,
                                                        _groupType: group.latestEvent.type,
                                                        _groupMagnitude: group.latestEvent.magnitude
                                                    },
                                                    false,
                                                    group.updateCount > 1,
                                                    false,
                                                    null
                                                )}
                                            </div>
                                        )}

                                        {/* 展开状态：显示所有报的时间线 */}
                                        {isExpanded && (
                                            <div className="card" style={{
                                                padding: '24px',
                                                position: 'relative'
                                            }}>
                                                {/* 顶部标题栏 */}
                                                <div style={{
                                                    display: 'flex',
                                                    justifyContent: 'space-between',
                                                    alignItems: 'center',
                                                    marginBottom: '24px',
                                                    paddingBottom: '16px',
                                                    borderBottom: '1px solid var(--md-sys-color-outline-variant)'
                                                }}>
                                                    <div>
                                                        <Typography variant="h6" sx={{fontWeight: 700, mb: 0.5}}>
                                                            {buildEarthquakeTitle(group.latestEvent)}
                                                        </Typography>
                                                        <Typography variant="body2" sx={{opacity: 0.6}}>
                                                            📡 {formatSourceName(group.latestEvent.source)} ·
                                                            共 {totalReports} 次更新
                                                        </Typography>
                                                    </div>
                                                    <button
                                                        onClick={() => toggleEventGroup(group.id)}
                                                        style={{
                                                            background: 'var(--md-sys-color-surface-variant)',
                                                            border: 'none',
                                                            borderRadius: '8px',
                                                            padding: '8px 16px',
                                                            cursor: 'pointer',
                                                            fontSize: '13px',
                                                            fontWeight: 600,
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            gap: '4px'
                                                        }}
                                                    >
                                                        <span>收起</span>
                                                        <span>▲</span>
                                                    </button>
                                                </div>

                                                {/* 时间线展示所有报 */}
                                                <div style={{position: 'relative', paddingLeft: '40px'}}>
                                                    {/* 时间线竖线 */}
                                                    <div style={{
                                                        position: 'absolute',
                                                        left: '19px',
                                                        top: '12px',
                                                        bottom: '12px',
                                                        width: '2px',
                                                        background: 'var(--md-sys-color-outline-variant)'
                                                    }}></div>

                                                    {/* 所有报的列表（倒序：最新在上） */}
                                                    {group.events.map((evt, idx) => {
                                                        const reportIndex = totalReports - idx;
                                                        const isLatest = idx === 0;
                                                        const rowType = evt.type || group.latestEvent.type || '';
                                                        const isEarthquake = rowType === 'earthquake' || rowType === 'earthquake_warning';
                                                        const rowDepth = evt.depth ?? group.latestEvent.depth;
                                                        const rowMagnitude = evt.magnitude ?? group.latestEvent.magnitude;
                                                        const rowMagnitudeText = formatMagnitudeBadge(rowMagnitude);
                                                        const rowBadgeMeta = getEarthquakeBadgeContent({
                                                            ...group.latestEvent,
                                                            ...evt,
                                                            _groupMagnitude: group.latestEvent.magnitude
                                                        });

                                                        return (
                                                            <div key={idx} style={{
                                                                position: 'relative',
                                                                marginBottom: idx === group.events.length - 1 ? '0' : '20px',
                                                                paddingBottom: idx === group.events.length - 1 ? '0' : '20px',
                                                                borderBottom: idx === group.events.length - 1 ? 'none' : '1px solid var(--md-sys-color-outline-variant)'
                                                            }}>
                                                                {/* 时间线节点 */}
                                                                <div style={{
                                                                    position: 'absolute',
                                                                    left: '-29px',
                                                                    top: '8px',
                                                                    width: '20px',
                                                                    height: '20px',
                                                                    borderRadius: '50%',
                                                                    background: isLatest
                                                                        ? 'var(--md-sys-color-primary)'
                                                                        : 'var(--md-sys-color-surface-variant)',
                                                                    border: `3px solid ${isLatest ? 'var(--md-sys-color-primary-container)' : 'var(--md-sys-color-surface)'}`,
                                                                    boxShadow: isLatest ? '0 2px 8px rgba(103, 80, 164, 0.3)' : 'none'
                                                                }}></div>

                                                                {/* 报的内容 */}
                                                                <div style={{
                                                                    display: 'flex',
                                                                    gap: '12px',
                                                                    alignItems: 'flex-start'
                                                                }}>
                                                                    {/* 烈度/震度徽章（按数据源自动选择，缺失时回退震级） */}
                                                                    {isEarthquake && (
                                                                        <div style={{
                                                                            minWidth: '60px',
                                                                            height: '60px',
                                                                            borderRadius: '12px',
                                                                            backgroundColor: rowBadgeMeta.background || '#6B7878',
                                                                            display: 'flex',
                                                                            alignItems: 'center',
                                                                            justifyContent: 'center',
                                                                            flexShrink: 0,
                                                                            position: 'relative',
                                                                            overflow: 'hidden',
                                                                            boxShadow: '0 2px 8px rgba(0,0,0,0.16)'
                                                                        }}>
                                                                    <span style={{
                                                                        position: 'absolute',
                                                                        top: 0,
                                                                        left: 0,
                                                                        width: '100%',
                                                                        height: '14px',
                                                                        lineHeight: '14px',
                                                                        textAlign: 'center',
                                                                        fontSize: '9px',
                                                                        fontWeight: 600,
                                                                        color: 'rgba(255,255,255,0.88)',
                                                                        background: 'rgba(0,0,0,0.2)'
                                                                    }}>
                                                                        {rowBadgeMeta.label}
                                                                    </span>
                                                                            <span style={{
                                                                                paddingTop: '10px',
                                                                                fontWeight: 800,
                                                                                fontSize: '30px',
                                                                                color: rowBadgeMeta.color,
                                                                                textShadow: '0 1px 2px rgba(0,0,0,0.25)',
                                                                                lineHeight: 1
                                                                            }}>
                                                                        {rowBadgeMeta.text}
                                                                    </span>
                                                                        </div>
                                                                    )}

                                                                    {/* 信息列 */}
                                                                    <div style={{flex: 1, minWidth: 0}}>
                                                                        <div style={{
                                                                            display: 'flex',
                                                                            alignItems: 'center',
                                                                            gap: '8px',
                                                                            marginBottom: '6px',
                                                                            flexWrap: 'wrap'
                                                                        }}>
                                                                    <span style={{
                                                                        fontSize: '13px',
                                                                        fontWeight: 700,
                                                                        padding: '3px 10px',
                                                                        borderRadius: '6px',
                                                                        background: isLatest
                                                                            ? 'var(--md-sys-color-primary)'
                                                                            : 'var(--md-sys-color-surface-variant)',
                                                                        color: isLatest
                                                                            ? 'var(--md-sys-color-on-primary)'
                                                                            : 'inherit'
                                                                    }}>
                                                                        第 {reportIndex} 报
                                                                    </span>
                                                                            {isLatest && (
                                                                                <span style={{
                                                                                    fontSize: '13px',
                                                                                    fontWeight: 700,
                                                                                    padding: '3px 10px',
                                                                                    borderRadius: '6px',
                                                                                    background: 'var(--md-sys-color-tertiary-container)',
                                                                                    color: 'var(--md-sys-color-on-tertiary-container)'
                                                                                }}>
                                                                            最新
                                                                        </span>
                                                                            )}
                                                                            <Typography variant="body2" sx={{
                                                                                opacity: 0.6,
                                                                                fontSize: '13px'
                                                                            }}>
                                                                                🕒 {formatTimeFriendly(evt.time || evt.timestamp, displayTimezone, evt.source || group.latestEvent.source || '')}
                                                                            </Typography>
                                                                        </div>
                                                                        {isEarthquake && (
                                                                            <div style={{
                                                                                display: 'flex',
                                                                                alignItems: 'center',
                                                                                gap: '12px',
                                                                                flexWrap: 'wrap'
                                                                            }}>
                                                                                <Typography variant="body2" sx={{
                                                                                    opacity: 0.85,
                                                                                    fontSize: '13px',
                                                                                    fontWeight: 600
                                                                                }}>
                                                                                    震级: {rowMagnitudeText !== '--' ? `M ${rowMagnitudeText}` : '调查中'}
                                                                                </Typography>
                                                                                <Typography variant="body2" sx={{
                                                                                    opacity: 0.8,
                                                                                    fontSize: '13px'
                                                                                }}>
                                                                                    深度: {(rowDepth !== undefined && rowDepth !== null) ? `${rowDepth} km` : '未知'}
                                                                                </Typography>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* 分页控件 */}
                    {total > 0 && (
                        <Box sx={{mt: 4, display: 'flex', flexDirection: 'column', gap: 1.5}}>
                            <Box sx={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                flexWrap: 'wrap',
                                gap: 1.5
                            }}>
                                <Box sx={{display: 'flex', alignItems: 'center', gap: 1}}>
                                    <Typography variant="body2" sx={{opacity: 0.7}}>每页</Typography>
                                    <select
                                        value={pageSize}
                                        onChange={(e) => setPageSize(Number(e.target.value))}
                                        style={{
                                            border: '1px solid var(--md-sys-color-outline-variant)',
                                            borderRadius: '8px',
                                            padding: '6px 10px',
                                            background: 'var(--md-sys-color-surface)',
                                            color: 'inherit',
                                            fontSize: '13px',
                                            fontWeight: 600
                                        }}
                                    >
                                        {[20, 50, 100, 200].map(size => (
                                            <option key={size} value={size}>{size} 条</option>
                                        ))}
                                    </select>
                                    <Typography variant="body2" sx={{opacity: 0.6}}>
                                        第 {currentPage} / {Math.max(totalPages, 1)} 页
                                    </Typography>
                                </Box>

                                <Box sx={{display: 'flex', alignItems: 'center', gap: 1}}>
                                    <input
                                        type="number"
                                        min={1}
                                        max={Math.max(totalPages, 1)}
                                        value={pageInput}
                                        onChange={(e) => setPageInput(e.target.value)}
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter') {
                                                handlePageJump();
                                            }
                                        }}
                                        placeholder="跳转页码"
                                        style={{
                                            width: '92px',
                                            border: '1px solid var(--md-sys-color-outline-variant)',
                                            borderRadius: '8px',
                                            padding: '6px 10px',
                                            background: 'var(--md-sys-color-surface)',
                                            color: 'inherit',
                                            fontSize: '13px'
                                        }}
                                    />
                                    <button
                                        onClick={handlePageJump}
                                        disabled={!canJump}
                                        style={{
                                            padding: '6px 12px',
                                            borderRadius: '8px',
                                            border: '1px solid var(--md-sys-color-outline-variant)',
                                            background: 'var(--md-sys-color-surface-variant)',
                                            cursor: canJump ? 'pointer' : 'not-allowed',
                                            opacity: canJump ? 1 : 0.5,
                                            fontWeight: 600,
                                            fontSize: '13px'
                                        }}
                                    >
                                        跳转
                                    </button>
                                </Box>
                            </Box>

                            {totalPages > 1 && (
                                <Box sx={{
                                    display: 'flex',
                                    justifyContent: 'center',
                                    alignItems: 'center',
                                    flexWrap: 'wrap',
                                    gap: 1
                                }}>
                                    <button
                                        onClick={() => goToPage(currentPage - 1)}
                                        disabled={currentPage <= 1}
                                        style={{
                                            padding: '6px 12px',
                                            borderRadius: '8px',
                                            border: '1px solid var(--md-sys-color-outline-variant)',
                                            background: 'var(--md-sys-color-surface-variant)',
                                            cursor: currentPage <= 1 ? 'not-allowed' : 'pointer',
                                            opacity: currentPage <= 1 ? 0.4 : 1,
                                            fontWeight: 600,
                                            fontSize: '13px'
                                        }}
                                    >
                                        ‹
                                    </button>

                                    {paginationItems.map((item, idx) => (
                                        typeof item === 'number' ? (
                                            <button
                                                key={`page-${item}`}
                                                onClick={() => goToPage(item)}
                                                style={{
                                                    minWidth: '34px',
                                                    padding: '6px 10px',
                                                    borderRadius: '8px',
                                                    border: '1px solid var(--md-sys-color-outline-variant)',
                                                    background: item === currentPage
                                                        ? 'var(--md-sys-color-primary-container)'
                                                        : 'var(--md-sys-color-surface)',
                                                    color: item === currentPage
                                                        ? 'var(--md-sys-color-on-primary-container)'
                                                        : 'inherit',
                                                    cursor: 'pointer',
                                                    fontWeight: item === currentPage ? 700 : 600,
                                                    fontSize: '13px'
                                                }}
                                            >
                                                {item}
                                            </button>
                                        ) : (
                                            <span key={`ellipsis-${idx}`}
                                                  style={{opacity: 0.6, padding: '0 2px'}}>…</span>
                                        )
                                    ))}

                                    <button
                                        onClick={() => goToPage(currentPage + 1)}
                                        disabled={currentPage >= totalPages}
                                        style={{
                                            padding: '6px 12px',
                                            borderRadius: '8px',
                                            border: '1px solid var(--md-sys-color-outline-variant)',
                                            background: 'var(--md-sys-color-surface-variant)',
                                            cursor: currentPage >= totalPages ? 'not-allowed' : 'pointer',
                                            opacity: currentPage >= totalPages ? 0.4 : 1,
                                            fontWeight: 600,
                                            fontSize: '13px'
                                        }}
                                    >
                                        ›
                                    </button>
                                </Box>
                            )}
                        </Box>
                    )}
                </>
            )}
        </Box>
    );
}