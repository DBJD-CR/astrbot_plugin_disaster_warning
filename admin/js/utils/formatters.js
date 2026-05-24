const JST_SOURCE_KEYWORDS = ['jma', 'p2p', 'wolfx_jma', 'japan'];

/**
 * 判断数据源是否属于 UTC+9 (JST) 体系
 * @param {string} source - 数据源标识
 * @returns {boolean}
 */
function isLikelyJstSource(source = '') {
    const sourceKey = String(source || '').toLowerCase();
    if (!sourceKey) return false;
    return JST_SOURCE_KEYWORDS.some(keyword => sourceKey.includes(keyword));
}

/**
 * 统一解析事件时间，返回标准 Date 对象
 * - 优先遵循字符串内自带时区信息 (Z / +09:00 等)
 * - 对无时区的时间字符串按数据源兜底：JST 源按 UTC+9，其他按 UTC+8
 * @param {string|number|Date} rawTime - 原始时间
 * @param {string} sourceHint - 数据源标识，用于无时区时推断
 * @returns {Date|null}
 */
function parseEventTimeToDate(rawTime, sourceHint = '') {
    if (rawTime === null || rawTime === undefined || rawTime === '') return null;

    if (rawTime instanceof Date) {
        return Number.isNaN(rawTime.getTime()) ? null : new Date(rawTime.getTime());
    }

    if (typeof rawTime === 'number') {
        const dateFromTs = new Date(rawTime);
        return Number.isNaN(dateFromTs.getTime()) ? null : dateFromTs;
    }

    const raw = String(rawTime).trim();
    if (!raw) return null;

    // 已携带时区：直接按标准时间解析
    if (/([zZ]|[+\-]\d{2}:?\d{2})$/.test(raw)) {
        const directDate = new Date(raw);
        return Number.isNaN(directDate.getTime()) ? null : directDate;
    }

    // 尝试解析不带时区的标准日期时间
    const normalized = raw.replace(' ', 'T');
    const match = normalized.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?$/);
    if (match) {
        const [, y, m, d, hh, mm, ss = '0', ms = '0'] = match;
        const offsetHours = isLikelyJstSource(sourceHint) ? 9 : 8;
        const utcMs = Date.UTC(
            Number(y),
            Number(m) - 1,
            Number(d),
            Number(hh) - offsetHours,
            Number(mm),
            Number(ss),
            Number(ms.padEnd(3, '0'))
        );
        const parsed = new Date(utcMs);
        return Number.isNaN(parsed.getTime()) ? null : parsed;
    }

    // 兜底走浏览器原生解析
    const fallbackDate = new Date(raw);
    return Number.isNaN(fallbackDate.getTime()) ? null : fallbackDate;
}

/**
 * 格式化时间为友好显示字符串（如"刚刚"、"xx分钟前"）
 * @param {string} isoString - ISO 8601 格式的时间字符串
 * @param {string} timeZone - 目标时区 (例如: 'UTC+8', 'Asia/Shanghai')
 * @param {string} sourceHint - 数据源标识，用于无时区时间解析
 * @returns {string} 格式化后的时间字符串
 */
function formatTimeFriendly(isoString, timeZone = 'UTC+8', sourceHint = '') {
    if (!isoString) return '--';
    const date = parseEventTimeToDate(isoString, sourceHint);
    if (!date) return '--';

    const diffMs = Date.now() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return '刚刚';
    if (diffMins < 60) return `${diffMins}分钟前`;

    return formatTimeWithZone(isoString, timeZone, false, sourceHint);
}

/**
 * 将时间字符串格式化为指定时区的时间
 * @param {string} isoString - ISO 8601 时间字符串
 * @param {string} timeZone - 目标时区 (例如: 'UTC+8', 'Asia/Shanghai')
 * @param {boolean} includeYear - 是否包含年份
 * @param {string} sourceHint - 数据源标识，用于无时区时间解析
 * @returns {string} 格式化后的时间字符串 (e.g., "02-13 14:30")
 */
function formatTimeWithZone(isoString, timeZone = 'UTC+8', includeYear = false, sourceHint = '') {
    if (!isoString) return '--';
    try {
        const date = parseEventTimeToDate(isoString, sourceHint);
        if (!date) return '--';

        // 处理 UTC+X / UTC-X 格式
        if (timeZone.toUpperCase().startsWith('UTC')) {
            const offsetStr = timeZone.substring(3);
            const offsetHours = parseFloat(offsetStr);
            if (!isNaN(offsetHours)) {
                const targetTime = new Date(date.getTime() + (3600000 * offsetHours));

                const month = (targetTime.getUTCMonth() + 1).toString().padStart(2, '0');
                const day = targetTime.getUTCDate().toString().padStart(2, '0');
                const hours = targetTime.getUTCHours().toString().padStart(2, '0');
                const mins = targetTime.getUTCMinutes().toString().padStart(2, '0');

                if (includeYear) {
                     return `${targetTime.getUTCFullYear()}-${month}-${day} ${hours}:${mins}`;
                }
                return `${month}-${day} ${hours}:${mins}`;
            }
        }

        // 使用 Intl.DateTimeFormat 处理 IANA 时区 (Asia/Shanghai 等)
        const options = {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
            timeZone: timeZone
        };

        if (includeYear) {
            options.year = 'numeric';
        }

        const formatter = new Intl.DateTimeFormat('zh-CN', options);
        const parts = formatter.formatToParts(date);

        let y, m, d, h, min;
        parts.forEach(({ type, value }) => {
            if (type === 'year') y = value;
            if (type === 'month') m = value;
            if (type === 'day') d = value;
            if (type === 'hour') h = value;
            if (type === 'minute') min = value;
        });

        if (includeYear) {
            return `${y}-${m}-${d} ${h}:${min}`;
        }
        return `${m}-${d} ${h}:${min}`;

    } catch (e) {
        console.error('Time formatting error:', e);
        return isoString; // Fallback
    }
}

/**
 * 根据震级获取对应的 CSS 类名
 * @param {number} mag - 地震震级
 * @returns {string} CSS 类名
 */
function getMagColorClass(mag) {
    if (mag >= 7) return 'mag-high';
    if (mag >= 5) return 'mag-medium';
    return 'mag-low';
}

/**
 * 根据震级获取对应的颜色值（Hex）
 * @param {number} mag - 地震震级
 * @returns {string} 颜色 Hex 值
 */
function getMagnitudeColor(mag) {
    if (mag >= 7) return '#ef4444';
    if (mag >= 5) return '#f97316';
    if (mag >= 3) return '#eab308';
    return '#3b82f6';
}

/**
 * 根据气象预警描述获取对应的颜色类名（解析红色、橙色、黄色、蓝色等关键字）
 * @param {string} description - 预警描述文本
 * @returns {string} CSS 类名
 */
function getWeatherColorClass(description) {
    if (!description) return 'weather-blue';
    if (description.includes('红色')) return 'weather-red';
    if (description.includes('橙色')) return 'weather-orange';
    if (description.includes('黄色')) return 'weather-yellow';
    return 'weather-blue';
}

/**
 * 统一规范化后端重构后的数据源标识
 * - 新命名(source/source_id) 作为主体系
 * - 旧命名仅作为输入别名折叠到同一规范名
 * @param {string} source
 * @returns {string}
 */
function normalizeSourceName(source) {
    if (!source) return 'unknown';

    const rawSource = String(source).trim();
    if (!rawSource) return 'unknown';

    const lowerSource = rawSource.toLowerCase();
    const aliasMap = {
        // 旧前端 key -> 新规范 key
        'fan_studio_cenc': 'cenc_fanstudio',
        'fan_studio_cea': 'cea_fanstudio',
        'fan_studio_cea_pr': 'cea_pr_fanstudio',
        'fan_studio_cwa': 'cwa_fanstudio',
        'fan_studio_cwa_report': 'cwa_fanstudio_report',
        'fan_studio_usgs': 'usgs_fanstudio',
        'fan_studio_jma': 'jma_fanstudio',
        'fan_studio_weather': 'china_weather_fanstudio',
        'fan_studio_tsunami': 'china_tsunami_fanstudio',
        'p2p_eew': 'jma_p2p',
        'p2p_earthquake': 'jma_p2p_info',
        'p2p_tsunami': 'jma_tsunami_p2p',
        'wolfx_jma_eew': 'jma_wolfx',
        'wolfx_cenc_eew': 'cea_wolfx',
        'wolfx_cwa_eew': 'cwa_wolfx',
        'wolfx_cenc_eq': 'cenc_wolfx',
        'wolfx_jma_eq': 'jma_wolfx_info',

        // 配置项 / 子数据源 key -> 新规范展示 key
        'china_earthquake_warning': 'cea_fanstudio',
        'china_earthquake_warning_provincial': 'cea_pr_fanstudio',
        'taiwan_cwa_earthquake': 'cwa_fanstudio',
        'taiwan_cwa_report': 'cwa_fanstudio_report',
        'china_cenc_earthquake': 'cenc_fanstudio',
        'usgs_earthquake': 'usgs_fanstudio',
        'china_weather_alarm': 'china_weather_fanstudio',
        'china_tsunami': 'china_tsunami_fanstudio',
        'japan_jma_eew': 'jma_p2p',
        'japan_jma_earthquake': 'jma_p2p_info',
        'japan_jma_tsunami': 'jma_tsunami_p2p',
        'china_cenc_eew': 'cea_wolfx',
        'taiwan_cwa_eew': 'cwa_wolfx',

        // 中文标签 -> 新规范 key
        '中国气象局：气象预警': 'china_weather_fanstudio',
        '中国气象局: 气象预警': 'china_weather_fanstudio',
        '台湾中央气象署：强震即时警报': 'cwa_fanstudio',
        '台湾中央气象署: 强震即时警报': 'cwa_fanstudio',
        '台湾中央气象署：地震报告': 'cwa_fanstudio_report',
        '台湾中央气象署: 地震报告': 'cwa_fanstudio_report',
        '中国地震台网（cenc）': 'cenc_fanstudio',
        '中国地震台网(cenc)': 'cenc_fanstudio',
        '中国地震台网（cenc）：地震测定': 'cenc_fanstudio',
        '中国地震台网(cenc)：地震测定': 'cenc_fanstudio',
        '中国地震预警网（cea）': 'cea_fanstudio',
        '中国地震预警网(cea)': 'cea_fanstudio',
        '中国地震预警网（省级）': 'cea_pr_fanstudio',
        '中国地震预警网(省级)': 'cea_pr_fanstudio',
        '日本气象厅：紧急地震速报': 'jma_fanstudio',
        '日本气象厅: 紧急地震速报': 'jma_fanstudio',
        '日本气象厅：地震情报': 'jma_p2p_info',
        '日本气象厅: 地震情报': 'jma_p2p_info',
        '日本气象厅：海啸预报': 'jma_tsunami_p2p',
        '日本气象厅: 海啸预报': 'jma_tsunami_p2p'
    };

    return aliasMap[rawSource] || aliasMap[lowerSource] || lowerSource;
}

/**
 * 将数据源代码转换为用户友好的显示名称
 * @param {string} source - 数据源代码
 * @returns {string} 友好的中文名称
 */
function formatSourceName(source) {
    const normalizedSource = normalizeSourceName(source);
    const sourceMap = {
        // Fan Studio (新规范)
        'cenc_fanstudio': '中国地震台网 (CENC) - Fan',
        'cea_fanstudio': '中国地震预警网 (CEA)',
        'cea_pr_fanstudio': '中国地震预警网 (省级)',
        'cwa_fanstudio': '台湾中央气象署: 强震即时警报 - Fan',
        'cwa_fanstudio_report': '台湾中央气象署: 地震报告',
        'usgs_fanstudio': '美国地质调查局 (USGS)',
        'jma_fanstudio': '日本气象厅: 紧急地震速报 - Fan',
        'china_weather_fanstudio': '中国气象局: 气象预警',
        'china_tsunami_fanstudio': '自然资源部海啸预警中心',

        // P2P (新规范)
        'jma_p2p': '日本气象厅: 紧急地震速报 - P2P',
        'jma_p2p_info': '日本气象厅: 地震情报 - P2P',
        'jma_tsunami_p2p': '日本气象厅: 海啸予报',

        // Wolfx (新规范)
        'jma_wolfx': '日本气象厅: 紧急地震速报 - Wolfx',
        'cea_wolfx': '中国地震预警网 (CEA) - Wolfx',
        'cwa_wolfx': '台湾中央气象署: 强震即时警报 - Wolfx',
        'cenc_wolfx': '中国地震台网地震测定 - Wolfx',
        'jma_wolfx_info': '日本气象厅地震情报 - Wolfx',

        // 其他
        'global_quake': 'Global Quake',
        'sc_eew': '四川地震局',
        'fj_eew': '福建地震局',
        'kma_earthquake': '韩国气象厅 (KMA)',
        'emsc_earthquake': '欧洲地中海地震中心 (EMSC)',
        'gfz_earthquake': '德国地学研究中心 (GFZ)',
        'enabled': '实时数据流',
        'unknown': '未知来源'
    };
    return sourceMap[normalizedSource] || String(source || '').trim() || '未知来源';
}
