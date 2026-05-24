(() => {
    /**
     * 根据明暗模式创建 Material-UI 全局主题对象。
     * 
     * 核心设计要点：
     * 1. 动态调色板映射：接收 dark 或 light 参数，自动从全局主题标记中提取相对应的色彩方案。
     * 2. 排版规范定制：指定默认字体族为 Roboto 配合 Noto Sans SC（思源黑体），并微调了从标题级到正文级、按钮级、说明级别的字号及字重。
     * 3. 组件级样式重载：为了对齐防灾大屏的现代感，深度定制了卡片、按钮、列表按钮、标签等组件的外观。
     */
    function createAppTheme(mode) {
        // 判断当前是暗黑还是亮色模式
        const themeMode = mode === 'dark' ? 'dark' : 'light';
        // 读取对应的配色标记值
        const tokens = window.AppThemeTokens[themeMode];

        return MaterialUI.createTheme({
            // 调色板配置
            palette: {
                mode: themeMode,
                // 主色调：采用经典紫色系
                primary: {
                    main: tokens.primary,
                    light: tokens.primaryLight,
                    dark: tokens.primaryDark,
                    contrastText: tokens.primaryContrast,
                },
                // 辅助色调：采用沉稳灰色系
                secondary: {
                    main: tokens.secondary,
                    light: tokens.secondaryLight,
                    dark: tokens.secondaryDark,
                    contrastText: tokens.secondaryContrast,
                },
                // 第三色调：用于次级重点高亮
                tertiary: {
                    main: tokens.tertiary,
                },
                // 错误色调：用于地震等危险警报高亮
                error: {
                    main: tokens.error,
                    light: tokens.errorLight,
                    dark: tokens.errorDark,
                    contrastText: tokens.errorContrast,
                },
                // 成功色调：用于在线心跳和安全运行指示
                success: {
                    main: tokens.success,
                    light: tokens.successLight,
                    contrastText: tokens.successContrast,
                },
                // 背景色彩定义
                background: {
                    default: tokens.background,
                    paper: tokens.paper,
                },
                // 表层色彩定义
                surface: {
                    main: tokens.surface,
                    variant: tokens.surfaceVariant,
                    tint: tokens.surfaceTint,
                },
                // 容器级表层色彩细化
                surfaceContainer: {
                    lowest: tokens.surfaceContainerLowest,
                    low: tokens.surfaceContainerLow,
                    main: tokens.surfaceContainer,
                    high: tokens.surfaceContainerHigh,
                    highest: tokens.surfaceContainerHighest,
                },
                // 轮廓边框线配色
                outline: {
                    main: tokens.outline,
                    variant: tokens.outlineVariant,
                },
                // 文本前景配色
                text: {
                    primary: tokens.textPrimary,
                    secondary: tokens.textSecondary,
                },
                // 分割线配色
                divider: tokens.divider,
            },
            // 通用形状圆角定义
            shape: {
                borderRadius: 12,
            },
            // 全局排版规格设定
            typography: {
                // 字体优先顺序：Roboto 字体，Noto Sans SC 中文思源黑体，Arial 兜底
                fontFamily: '"Roboto", "Noto Sans SC", "Helvetica", "Arial", sans-serif',
                h3: { fontSize: '3rem', fontWeight: 400, lineHeight: 1.167, letterSpacing: '0em' },
                h5: { fontSize: '1.5rem', fontWeight: 400, lineHeight: 1.334, letterSpacing: '0em' },
                h6: { fontSize: '1.25rem', fontWeight: 500, lineHeight: 1.6, letterSpacing: '0.0075em' },
                subtitle1: { fontSize: '1rem', fontWeight: 500, lineHeight: 1.5, letterSpacing: '0.00938em' },
                subtitle2: { fontSize: '0.875rem', fontWeight: 500, lineHeight: 1.57, letterSpacing: '0.00714em' },
                body1: { fontSize: '1rem', fontWeight: 400, lineHeight: 1.5, letterSpacing: '0.00938em' },
                body2: { fontSize: '0.875rem', fontWeight: 400, lineHeight: 1.43, letterSpacing: '0.01071em' },
                button: { fontSize: '0.875rem', fontWeight: 500, lineHeight: 1.75, letterSpacing: '0.02857em', textTransform: 'none' },
                caption: { fontSize: '0.75rem', fontWeight: 400, lineHeight: 1.66, letterSpacing: '0.03333em' },
            },
            // 细分组件样式重定义
            components: {
                // 全局基础样式表重写
                MuiCssBaseline: {
                    styleOverrides: {
                        body: {
                            backgroundColor: tokens.background, // 动态同步背景色
                        },
                    },
                },
                // 卡片组件重写：去除立体阴影投影，设为纯平透明设计
                MuiCard: {
                    defaultProps: { elevation: 0 },
                    styleOverrides: {
                        root: {
                            backgroundColor: 'transparent',
                            borderRadius: 16,
                            border: 'none',
                        },
                    },
                },
                // 按钮组件重写
                MuiButton: {
                    defaultProps: { disableElevation: true },
                    styleOverrides: {
                        root: {
                            borderRadius: 100, // 设为完全胶囊形状圆角
                            paddingLeft: 24,
                            paddingRight: 24,
                            paddingTop: 10,
                            paddingBottom: 10,
                            textTransform: 'none', // 禁用英文大写强制转换
                            fontWeight: 600,
                            fontSize: '0.875rem',
                            letterSpacing: '0.02857em',
                        },
                        // 实色填充按钮样式
                        contained: {
                            backgroundColor: tokens.primary,
                            color: tokens.primaryContrast,
                            '&:hover': {
                                backgroundColor: themeMode === 'dark' ? '#E8DDFF' : tokens.primaryLight,
                                boxShadow: '0 4px 12px rgba(103, 80, 164, 0.2)', // 悬浮添加半透明微发光投影
                            },
                        },
                        // 描边按钮样式
                        outlined: {
                            borderColor: tokens.outline,
                            color: tokens.primary,
                            '&:hover': {
                                backgroundColor: themeMode === 'dark'
                                    ? 'rgba(208, 188, 255, 0.08)'
                                    : 'rgba(103, 80, 164, 0.08)',
                                borderColor: tokens.primary,
                            },
                        },
                        // 纯文本按钮样式
                        text: {
                            color: tokens.primary,
                        },
                    },
                },
                // 导航列表按钮样式重写
                MuiListItemButton: {
                    styleOverrides: {
                        root: {
                            borderRadius: 100, // 侧边栏按钮胶囊造型
                            margin: '0 8px',
                            // 选中态配色样式
                            '&.Mui-selected': {
                                backgroundColor: themeMode === 'dark'
                                    ? 'rgba(208, 188, 255, 0.12)'
                                    : 'rgba(103, 80, 164, 0.12)',
                                color: themeMode === 'dark' ? tokens.primary : '#21005D',
                                '&:hover': {
                                    backgroundColor: themeMode === 'dark'
                                        ? 'rgba(208, 188, 255, 0.16)'
                                        : 'rgba(103, 80, 164, 0.16)',
                                },
                            },
                            // 悬浮态配色样式
                            '&:hover': {
                                backgroundColor: themeMode === 'dark'
                                    ? 'rgba(208, 188, 255, 0.08)'
                                    : 'rgba(103, 80, 164, 0.08)',
                            },
                        },
                    },
                },
                // 标签徽标组件样式重写
                MuiChip: {
                    styleOverrides: {
                        root: { borderRadius: 8, fontWeight: 600 },
                        // 成功状态标签（如运行正常，采用绿色调）
                        colorSuccess: {
                            backgroundColor: themeMode === 'dark' ? 'rgba(166, 211, 137, 0.12)' : 'rgba(56, 106, 32, 0.12)',
                            color: tokens.success,
                        },
                        // 错误状态标签（如发生故障，采用红色调）
                        colorError: {
                            backgroundColor: themeMode === 'dark' ? 'rgba(242, 184, 181, 0.12)' : 'rgba(179, 38, 30, 0.12)',
                            color: tokens.error,
                        },
                    },
                },
                // 面板纸张组件样式重写
                MuiPaper: {
                    defaultProps: { elevation: 0 },
                    styleOverrides: {
                        root: {
                            backgroundColor: tokens.surfaceContainer,
                            backgroundImage: 'none',
                            border: 'none',
                        },
                    },
                },
                // 分割线组件样式重写
                MuiDivider: {
                    styleOverrides: {
                        root: {
                            borderColor: tokens.divider,
                        },
                    },
                },
            },
        });
    }

    // 绑定至全局主题创建句柄
    window.createAppTheme = createAppTheme;
})();
