/**
 * 格式化时间为友好显示字符串（如"刚刚"、"xx分钟前"）
 * @param {string} isoString - ISO 8601 格式的时间字符串
 * @param {string} timeZone - 目标时区 (例如: 'UTC+8', 'Asia/Shanghai')
 * @returns {string} 格式化后的时间字符串
 */
function formatTimeFriendly(isoString, timeZone = 'UTC+8') {
    if (!isoString) return '--';
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return '刚刚';
    if (diffMins < 60) return `${diffMins}分钟前`;

    return formatTimeWithZone(isoString, timeZone, false);
}

/**
 * 将时间字符串格式化为指定时区的时间
 * @param {string} isoString - ISO 8601 时间字符串
 * @param {string} timeZone - 目标时区 (例如: 'UTC+8', 'Asia/Shanghai')
 * @param {boolean} includeYear - 是否包含年份
 * @returns {string} 格式化后的时间字符串 (e.g., "02-13 14:30")
 */
function formatTimeWithZone(isoString, timeZone = 'UTC+8', includeYear = false) {
    if (!isoString) return '--';
    try {
        const date = new Date(isoString);
        
        // 处理 UTC+X / UTC-X 格式
        let timeZoneValue = timeZone;
        if (timeZone.toUpperCase().startsWith('UTC')) {
            const offsetStr = timeZone.substring(3);
            const offsetHours = parseFloat(offsetStr);
            if (!isNaN(offsetHours)) {
                // 手动计算偏移
                const utc = date.getTime() + (date.getTimezoneOffset() * 60000);
                const targetTime = new Date(utc + (3600000 * offsetHours));
                
                const month = (targetTime.getMonth() + 1).toString().padStart(2, '0');
                const day = targetTime.getDate().toString().padStart(2, '0');
                const hours = targetTime.getHours().toString().padStart(2, '0');
                const mins = targetTime.getMinutes().toString().padStart(2, '0');
                
                if (includeYear) {
                     return `${targetTime.getFullYear()}-${month}-${day} ${hours}:${mins}`;
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

        // 格式化结果类似 "02/13, 14:30" 或 "2024/02/13, 14:30" (取决于具体 locale)
        // 统一调整为 MM-DD HH:mm 格式
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
 * 将数据源代码转换为用户友好的显示名称
 * @param {string} source - 数据源代码 (e.g., 'fan_studio_cenc')
 * @returns {string} 友好的中文名称
 */
function formatSourceName(source) {
    if (!source) return '未知来源';
    const sourceMap = {
        // Fan Studio
        'fan_studio_cenc': '中国地震台网 (CENC) - Fan',
        'fan_studio_cea': '中国地震预警网 (CEA) - Fan',
        'fan_studio_cea_pr': '中国地震预警网 (省级)',
        'fan_studio_cwa': '台湾中央气象署: 强震即时警报 - Fan',
        'fan_studio_cwa_report': '台湾中央气象署地震报告',
        'fan_studio_usgs': '美国地质调查局 (USGS)',
        'fan_studio_jma': '日本气象厅: 紧急地震速报 - Fan',
        'fan_studio_weather': '中国气象局: 气象预警',
        'fan_studio_tsunami': '自然资源部海啸预警中心',
        
        // P2P
        'p2p_eew': '日本气象厅: 紧急地震速报 - P2P',
        'p2p_earthquake': '日本气象厅: 地震情报 - P2P',
        'p2p_tsunami': '日本气象厅: 海啸预报 - P2P',
        
        // Wolfx
        'wolfx_jma_eew': '日本气象厅: 紧急地震速报 - Wolfx',
        'wolfx_cenc_eew': '中国地震预警网 (CEA) - Wolfx',
        'wolfx_cwa_eew': '台湾中央气象署: 强震即时警报 - Wolfx',
        'wolfx_cenc_eq': '中国地震台网地震测定 - Wolfx',
        'wolfx_jma_eq': '日本气象厅地震情报 - Wolfx',
        
        // Global Quake
        'global_quake': 'Global Quake',

        // 其他/旧版兼容
        'sc_eew': '四川地震局',
        'fj_eew': '福建地震局',
        'kma_earthquake': '韩国气象厅 (KMA)',
        'emsc_earthquake': '欧洲地中海地震中心 (EMSC)',
        'gfz_earthquake': '德国地学研究中心 (GFZ)',
        'unknown': '未知来源',

        // 配置项 Key 映射 (用于连接状态显示)
        'china_earthquake_warning': '中国地震预警网 (CEA)',
        'china_earthquake_warning_provincial': '中国地震预警网 (省级)',
        'taiwan_cwa_earthquake': '台湾中央气象署: 强震即时警报',
        'taiwan_cwa_report': '台湾中央气象署: 地震报告',
        'china_cenc_earthquake': '中国地震台网 (CENC)',
        'usgs_earthquake': '美国地质调查局 (USGS)',
        'china_weather_alarm': '中国气象局: 气象预警',
        'china_tsunami': '自然资源部海啸预警中心',
        
        'japan_jma_eew': '日本气象厅: 紧急地震速报',
        'japan_jma_earthquake': '日本气象厅: 地震情报',
        'japan_jma_tsunami': '日本气象厅: 海啸预报',
        
        'china_cenc_eew': '中国地震预警网 (CEA)',
        'taiwan_cwa_eew': '台湾中央气象署: 强震即时警报',

        'enabled': '实时数据流'
    };
    return sourceMap[source] || source;
}
