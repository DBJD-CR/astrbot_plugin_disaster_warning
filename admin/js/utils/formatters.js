/**
 * 格式化时间为友好显示字符串（如"刚刚"、"xx分钟前"）
 * @param {string} isoString - ISO 8601 格式的时间字符串
 * @returns {string} 格式化后的时间字符串
 */
function formatTimeFriendly(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return '刚刚';
    if (diffMins < 60) return `${diffMins}分钟前`;

    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    const hours = date.getHours().toString().padStart(2, '0');
    const mins = date.getMinutes().toString().padStart(2, '0');
    return `${month}-${day} ${hours}:${mins}`;
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
