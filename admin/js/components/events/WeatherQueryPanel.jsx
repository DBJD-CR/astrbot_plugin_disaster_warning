const { Box, Typography, CircularProgress } = MaterialUI;
const { useState, useMemo } = React;

/**
 * 气象预警快捷查询面板
 * 查询逻辑与后端 /气象预警查询 保持一致：
 * - keyword 为预警ID时进入详情模式
 * - 否则按地区 + 可选类型/颜色检索近72小时
 */
function WeatherQueryPanel() {
    const [keyword, setKeyword] = useState('');
    const [optionalA, setOptionalA] = useState('');
    const [optionalB, setOptionalB] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [result, setResult] = useState(null);

    const isIdQuery = useMemo(() => /^\d+_\d{12,14}$/.test((keyword || '').trim()), [keyword]);

    const handleSearch = async () => {
        const kw = (keyword || '').trim();
        if (!kw) {
            setError('请输入地区关键词或预警ID');
            setResult(null);
            return;
        }

        setLoading(true);
        setError('');
        try {
            const query = new URLSearchParams({
                keyword: kw,
                optional_a: (optionalA || '').trim(),
                optional_b: (optionalB || '').trim(),
            });

            const response = await fetch(`/api/weather/query?${query.toString()}`);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data?.error || '查询失败');
            }

            if (!data?.success) {
                const baseError = String(data?.error || '未查询到结果');
                if (data?.query_mode === 'search' && data?.filters) {
                    const segments = [`地区=${data.filters.location || ''}`].filter(Boolean);
                    if (data.filters.type) segments.push(`预警类型=${data.filters.type}`);
                    if (data.filters.color) segments.push(`预警颜色=${data.filters.color}`);
                    setError(`${baseError}${segments.length ? `\n检索条件：${segments.join('，')}` : ''}`);
                } else {
                    setError(baseError);
                }
                setResult(null);
                return;
            }

            setResult(data);
        } catch (e) {
            console.error('[WeatherQueryPanel] query failed:', e);
            setError(`查询失败：${e?.message || e}`);
            setResult(null);
        } finally {
            setLoading(false);
        }
    };

    const handleReset = () => {
        setKeyword('');
        setOptionalA('');
        setOptionalB('');
        setError('');
        setResult(null);
    };

    const renderIdResult = () => {
        const detail = result?.data || {};
        const titleText = detail.title_text || detail.headline_text || '气象预警详情';
        const bodyText = detail.body_text || '暂无详细描述';
        const guidelineText = detail.guideline_text || '';

        return (
            <div className="weather-query-result-card">
                <div className="weather-query-result-header">
                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                        {titleText}{detail.color_emoji || ''}
                    </Typography>
                    {detail.alarm_id && (
                        <Typography variant="caption" sx={{ opacity: 0.65 }}>
                            ID: {detail.alarm_id}
                        </Typography>
                    )}
                </div>

                <div className="weather-query-result-body">
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                        {bodyText}
                    </Typography>
                    {guidelineText && (
                        <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', mt: 1, opacity: 0.9 }}>
                            {guidelineText}
                        </Typography>
                    )}
                </div>

                {detail.icon_url && (
                    <div className="weather-query-icon-wrap">
                        <div className="weather-query-icon-card">
                            <img
                                src={detail.icon_url}
                                alt={detail.weather_type_code || 'weather-icon'}
                                className="weather-query-icon"
                                loading="lazy"
                                onError={(e) => {
                                    e.currentTarget.style.display = 'none';
                                }}
                            />
                        </div>
                    </div>
                )}
            </div>
        );
    };

    const renderSearchResult = () => {
        const items = Array.isArray(result?.items) ? result.items : [];
        return (
            <div className="weather-query-list">
                {items.map((item, index) => (
                    <div className="weather-query-list-item" key={`${item.alarm_id || 'unknown'}-${index}`}>
                        {item.icon_url && (
                            <img
                                src={item.icon_url}
                                alt={item.weather_type_code || 'weather-icon'}
                                className="weather-query-list-item-image"
                                loading="lazy"
                                onError={(e) => {
                                    e.currentTarget.style.display = 'none';
                                }}
                            />
                        )}
                        <div className="weather-query-list-item-main">
                            <Typography variant="body2">发布时间：{item.issue_time || '未知时间'}</Typography>
                            <Typography variant="body2">ID：{item.alarm_id || '未知ID'}</Typography>
                            <Typography variant="body2">发布机构：{item.publish_org || '未知发布机构'}</Typography>
                            <Typography variant="body2">预警类型：{item.weather_type_line || '未知类型预警'}</Typography>
                        </div>
                    </div>
                ))}
            </div>
        );
    };

    return (
        <div className="card weather-query-panel">
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 2.5, flexWrap: 'wrap' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <span style={{ fontSize: '20px' }}>🌦️</span>
                    <Typography variant="h6" sx={{ fontWeight: 800 }}>气象预警快捷查询</Typography>
                </Box>
                <Typography variant="caption" sx={{ opacity: 0.6 }}>
                    与 /气象预警查询 逻辑一致
                </Typography>
            </Box>

            <div className="weather-query-form">
                <input
                    value={keyword}
                    onChange={(e) => setKeyword(e.target.value)}
                    placeholder="输入地区关键词（如 山西）或预警ID（如 36042941600000_20260314235956）"
                    className="weather-query-input weather-query-keyword"
                />

                <input
                    value={optionalA}
                    onChange={(e) => setOptionalA(e.target.value)}
                    placeholder="可选：预警类型（如 大风）"
                    className="weather-query-input"
                    disabled={isIdQuery}
                />

                <select
                    value={optionalB}
                    onChange={(e) => setOptionalB(e.target.value)}
                    className="weather-query-input"
                    disabled={isIdQuery}
                >
                    <option value="">可选：预警颜色</option>
                    <option value="红色">红色</option>
                    <option value="橙色">橙色</option>
                    <option value="黄色">黄色</option>
                    <option value="蓝色">蓝色</option>
                    <option value="白色">白色</option>
                    <option value="红">红</option>
                    <option value="橙">橙</option>
                    <option value="黄">黄</option>
                    <option value="蓝">蓝</option>
                    <option value="白">白</option>
                </select>

                <button className="btn weather-query-btn" onClick={handleSearch} disabled={loading}>
                    {loading ? '查询中...' : '查询'}
                </button>
                <button className="btn weather-query-btn weather-query-btn-secondary" onClick={handleReset} disabled={loading}>
                    清空
                </button>
            </div>

            {loading && (
                <div className="weather-query-loading">
                    <CircularProgress size={24} />
                    <Typography variant="body2" sx={{ opacity: 0.75 }}>正在查询，请稍候...</Typography>
                </div>
            )}

            {!loading && error && (
                <div className="weather-query-error">
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{error}</Typography>
                </div>
            )}

            {!loading && !error && result && (
                <div className="weather-query-result">
                    {result.query_mode === 'id' ? renderIdResult() : renderSearchResult()}
                </div>
            )}
        </div>
    );
}
