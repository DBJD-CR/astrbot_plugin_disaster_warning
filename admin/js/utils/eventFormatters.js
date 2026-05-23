(() => {
    // 震度数值与对应的界面圆角徽标背景色映射表
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
        unknown: '#6B7878',
    };

    /**
     * 健壮地将数据库内扁平的时间戳字符串转化为前端兼容的 ISO 8601 标准 UTC 时间戳格式
     */
    function normalizeDbUtcTime(rawTime) {
        if (!rawTime) return '';
        const text = String(rawTime).trim();
        if (!text) return '';
        // 如果格式如 2026-05-22 18:00:00，则自动将空格替换为 T 字符并追加 Z 零时区标识
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text)) {
            return `${text.replace(' ', 'T')}Z`;
        }
        return text;
    }

    /**
     * 获取事件展示所需的核心时间戳
     * 
     * 判定逻辑：
     * - 可选择优先使用事件记录更新时间（recorded_at）还是发震发灾的最初物理时间（time）。
     */
    function getDisplayTimeValue(event, preferUpdateTime = false) {
        if (!event || typeof event !== 'object') return '';
        const updateTime = normalizeDbUtcTime(event.recorded_at || event.updated_at || event.timestamp);
        const eventTime = event.time || event.timestamp || '';
        return preferUpdateTime ? (updateTime || eventTime || '') : (eventTime || updateTime || '');
    }

    /**
     * 判断数据源是否为日本气象厅或相关高时效的特定数据节点
     */
    function isLikelyJmaSource(source = '') {
        const sourceKey = String(source || '').toLowerCase();
        if (!sourceKey) return false;
        return sourceKey.includes('jma') || sourceKey.includes('p2p') || sourceKey.includes('cwa');
    }

    /**
     * 净化及归一化地震卡片的标题和地名
     * 
     * 净化策略：
     * - 剥离标题首部冗余的“M 级”震级标识。
     * - 拦截调查中的地震事件，对日本源事件标记为震度速报，对其他源标记为参数调查中。
     */
    function normalizeEarthquakeTitle(evt) {
        const rawTitle = String(evt?.description || '').trim();
        if (!rawTitle) return '未知位置';

        const magPrefixMatch = rawTitle.match(/^M\s*([^\s]+)\s*(.*)$/i);
        if (magPrefixMatch) {
            const [, magTokenRaw, restRaw] = magPrefixMatch;
            const magToken = String(magTokenRaw || '').toLowerCase();
            const rest = String(restRaw || '').trim();
            const invalidMagToken = ['none', 'nan', '--', 'null', 'undefined'].includes(magToken);
            const unknownPlace = !rest || rest === '未知地点' || rest === '未知位置';
            
            // 匹配到无地点无震级的调查中异常状态事件
            if (invalidMagToken && unknownPlace) {
                return isLikelyJmaSource(evt?.source) ? '震度速报（震源参数调查中）' : '震源参数调查中';
            }
            if (rest) return rest;
        }
        return rawTitle;
    }

    /**
     * 格式化震级为保留一位小数的标准格式
     */
    function formatMagnitudeBadge(mag) {
        if (mag === null || mag === undefined || mag === '') return '--';
        const num = Number(mag);
        return Number.isFinite(num) ? num.toFixed(1) : '--';
    }

    /**
     * 格式化气象厅 Shindo 震度级别
     * 
     * 转换策略：
     * - 自动将日文的 弱 强 关键字替换为标准的减号与加号。
     * - 对传入的连续浮点数进行范围划档，对齐到 [1, 2, 3, 4, 5-, 5+, 6-, 6+, 7] 的等级上。
     */
    function formatShindoBadge(level) {
        if (level === null || level === undefined || level === '') return null;
        const raw = String(level).trim();
        if (!raw) return null;
        // 规整字符
        const normalized = raw.replace(/弱/g, '-').replace(/強/g, '+').replace(/强/g, '+').replace(/\s+/g, '');
        if (['1', '2', '3', '4', '5-', '5+', '6-', '6+', '7'].includes(normalized)) return normalized;
        
        // 浮点数分档算法
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
    }

    /**
     * 格式化中国标准的地震烈度级别
     */
    function formatIntensityBadge(level) {
        if (level === null || level === undefined || level === '') return null;
        const num = Number(level);
        if (!Number.isFinite(num)) return null;
        const rounded = Math.round(num);
        // 如果是标准的 1 至 12 度，则输出整型字符，否则输出保留一位的小数
        if (rounded >= 1 && rounded <= 12) return String(rounded);
        return num.toFixed(1);
    }

    /**
     * 根据震级或烈度值及所处度量体系获取对应的色盘颜色代码
     */
    function getIntensityColor(levelText, isJmaScale) {
        if (!levelText) return INT_COLOR_MAP.unknown;
        // 日本气象厅震度
        if (isJmaScale) return INT_COLOR_MAP[levelText] || INT_COLOR_MAP.unknown;
        
        // 中国标准烈度级别划分判色
        const n = Number(levelText);
        if (!Number.isFinite(n)) return INT_COLOR_MAP.unknown;
        if (n <= 2) return INT_COLOR_MAP['1'];
        if (n <= 4) return INT_COLOR_MAP['2'];
        if (n <= 5) return INT_COLOR_MAP['3'];
        if (n <= 6) return INT_COLOR_MAP['4'];
        if (n <= 8) return INT_COLOR_MAP['5-'];
        if (n <= 10) return INT_COLOR_MAP['6-'];
        return INT_COLOR_MAP['7'];
    }

    /**
     * 拼装样式类名后缀，用于在前台激活对应的阴影发光或底色 CSS
     */
    function normalizeBadgeToneToken(levelText, isJmaScale) {
        if (!levelText) return 'unknown';
        if (isJmaScale) {
            const normalized = String(levelText).trim().replace(/\s+/g, '');
            const jmaToneMap = {
                '1': 'shindo-1',
                '2': 'shindo-2',
                '3': 'shindo-3',
                '4': 'shindo-4',
                '5-': 'shindo-5-minus',
                '5+': 'shindo-5-plus',
                '6-': 'shindo-6-minus',
                '6+': 'shindo-6-plus',
                '7': 'shindo-7',
            };
            return jmaToneMap[normalized] || 'unknown';
        }
        
        const n = Number(levelText);
        if (!Number.isFinite(n)) return 'unknown';
        if (n <= 2) return 'intensity-1';
        if (n <= 4) return 'intensity-2';
        if (n <= 5) return 'intensity-3';
        if (n <= 6) return 'intensity-4';
        if (n <= 8) return 'intensity-5-minus';
        if (n <= 10) return 'intensity-6-minus';
        return 'intensity-7';
    }

    /**
     * 综合获取地震类事件卡片侧边圆圈高亮徽标的文本、状态类名及字样
     */
    function getEarthquakeBadgeContent(evt) {
        const source = evt?.source || '';
        const level = evt?.level;
        const isJmaScale = isLikelyJmaSource(source);
        if (isJmaScale) {
            const shindo = formatShindoBadge(level);
            if (shindo) {
                return { text: shindo, label: '震度', toneClass: normalizeBadgeToneToken(shindo, true) };
            }
        } else {
            const intensity = formatIntensityBadge(level);
            if (intensity) {
                return { text: intensity, label: '烈度', toneClass: normalizeBadgeToneToken(intensity, false) };
            }
        }
        // 退化分支：若无震度或烈度，则展示常规 M 级震级
        return { text: formatMagnitudeBadge(evt?.magnitude ?? evt?._groupMagnitude), label: '震级', toneClass: 'unknown' };
    }

    /**
     * 快速构建出符合规范的地震大标题，形如：M 6.0 四川雅安
     */
    function buildEarthquakeTitle(evt) {
        const normalizedTitle = normalizeEarthquakeTitle(evt);
        if (!normalizedTitle) return '未知位置';
        if (normalizedTitle.includes('调查中')) return normalizedTitle;
        const magText = formatMagnitudeBadge(evt?.magnitude ?? evt?._groupMagnitude);
        if (magText === '--') return normalizedTitle;
        return `M ${magText} ${normalizedTitle}`;
    }

    /**
     * 格式化并友好汉化下拉框中的数据源选项
     */
    function normalizeSourceOption(item) {
        if (!item) return null;
        const sourceValue = String(item.source_value || '').trim();
        const sourceLabel = String(item.source_label || '').trim();
        const rawValue = sourceValue || sourceLabel;
        if (!rawValue) return null;
        return {
            value: rawValue,
            label: formatSourceName(sourceLabel || sourceValue || rawValue), // 友好汉化地名名称
            normalizedKey: normalizeSourceName(rawValue),
        };
    }

    /**
     * 批量清洗汉化数据源过滤项，并按拼音降序排列
     */
    function normalizeSourceOptions(sourceOptions) {
        return (Array.isArray(sourceOptions) ? sourceOptions : [])
            .map(normalizeSourceOption)
            .filter(Boolean)
            .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
    }

    window.EventFormatters = {
        INT_COLOR_MAP,
        normalizeDbUtcTime,
        getDisplayTimeValue,
        isLikelyJmaSource,
        normalizeEarthquakeTitle,
        formatMagnitudeBadge,
        formatShindoBadge,
        formatIntensityBadge,
        getIntensityColor,
        normalizeBadgeToneToken,
        getEarthquakeBadgeContent,
        buildEarthquakeTitle,
        normalizeSourceOption,
        normalizeSourceOptions,
    };
})();
