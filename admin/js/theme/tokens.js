(() => {
    /**
     * 全局视觉主题设计标记定义表。
     * 
     * 主要色彩机制说明：
     * - 分为亮色模式（light）与暗色模式（dark）两套色盘定义。
     * - 设计风格参照 Material Design 3 规范进行调色设定。
     */
    const APP_THEME_TOKENS = {
        // 亮色模式色彩标记
        light: {
            primary: '#6750A4',                  // 品牌主色：深紫
            primaryLight: '#7F67BE',             // 主色明亮变体
            primaryDark: '#4F378B',              // 主色暗化变体
            primaryContrast: '#FFFFFF',          // 主色上的高对比前景色
            secondary: '#625B71',                // 辅助色：暗灰紫
            secondaryLight: '#7D7589',           // 辅助色明亮变体
            secondaryDark: '#4A4458',            // 辅助色暗化变体
            secondaryContrast: '#FFFFFF',        // 辅助色前景色
            tertiary: '#7D5260',                 // 第三修饰色
            error: '#B3261E',                    // 危险错误红色
            errorLight: '#DC362E',               // 错误红色明亮变体
            errorDark: '#8C1D18',                // 错误红色暗化变体
            errorContrast: '#FFFFFF',            // 错误前景色
            success: '#386A20',                  // 成功运行安全绿色
            successLight: '#629749',             // 安全绿色明亮变体
            successContrast: '#FFFFFF',          // 安全前景色
            background: '#FEF7FF',               // 面板底层铺底背景色
            paper: '#FFFFFF',                    // 基础卡片纸张背景色
            surface: '#FFFFFF',                  // 基础表层色
            surfaceVariant: '#E7E0EC',           // 变体表层色
            surfaceTint: '#6750A4',              // 叠加色
            surfaceContainerLowest: '#FFFFFF',   // 最底层级表面色
            surfaceContainerLow: '#F7F2FA',      // 低层级表面色
            surfaceContainer: '#F3EDF7',         // 标准层级表面色
            surfaceContainerHigh: '#ECE6F0',     // 高层级表面色
            surfaceContainerHighest: '#E6E0E9',  // 最高层级表面色
            outline: '#79747E',                  // 描边线色
            outlineVariant: '#CAC4D0',           // 变体描边线色
            textPrimary: '#1D1B20',              // 主要文字深色
            textSecondary: '#49454F',            // 次要文字浅灰
            divider: 'rgba(121, 116, 126, 0.12)', // 分割线色
        },
        // 暗色模式色彩标记
        dark: {
            primary: '#D0BCFF',                  // 品牌主色：淡紫
            primaryLight: '#EADDFF',             // 主色明亮变体
            primaryDark: '#B69DF8',              // 主色暗化变体
            primaryContrast: '#371E73',          // 主色前景色
            secondary: '#CCC2DC',                // 辅助色：浅灰紫
            secondaryLight: '#E8DEF8',           // 辅助色明亮变体
            secondaryDark: '#B0A7C0',            // 辅助色暗化变体
            secondaryContrast: '#332D41',        // 辅助色前景色
            tertiary: '#EFB8C8',                 // 第三修饰色
            error: '#F2B8B5',                    // 危险错误淡红
            errorLight: '#F9DEDC',               // 错误红色明亮变体
            errorDark: '#EC928E',                // 错误红色暗化变体
            errorContrast: '#601410',            // 错误前景色
            success: '#A6D389',                  // 成功安全淡绿
            successLight: '#C4EBA0',             // 安全绿色明亮变体
            successContrast: '#0E2000',          // 安全前景色
            background: '#141218',               // 深色面板底层底色
            paper: '#1C1B1F',                    // 深色基础卡片纸张背景色
            surface: '#1C1B1F',                  // 深色基础表层色
            surfaceVariant: '#49454F',           // 深色变体表层色
            surfaceTint: '#D0BCFF',              // 深色叠加色
            surfaceContainerLowest: '#0F0D13',   // 最底层级表面色
            surfaceContainerLow: '#1D1B20',      // 低层级表面色
            surfaceContainer: '#211F26',         // 标准层级表面色
            surfaceContainerHigh: '#2B2930',     // 高层级表面色
            surfaceContainerHighest: '#36343B',  // 最高层级表面色
            outline: '#938F99',                  // 描边线色
            outlineVariant: '#49454F',           // 变体描边线色
            textPrimary: '#E6E1E5',              // 主要文字白色
            textSecondary: '#CAC4D0',            // 次要文字灰白
            divider: 'rgba(147, 143, 153, 0.12)', // 分割线色
        },
    };

    // 绑定至全局主题色彩字典中，以便主题创建函数调用
    window.AppThemeTokens = APP_THEME_TOKENS;
})();
