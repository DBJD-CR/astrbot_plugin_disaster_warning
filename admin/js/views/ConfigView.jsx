/**
 * 模块名称：配置管理视图组件
 * 功能描述：作为配置管理面板的顶层视图容器，负责渲染整个参数配置页面的外壳结构，
 *          内部嵌入了具体的配置项渲染器组件以展示可视化参数项。
 */

const { Typography } = MaterialUI;

/**
 * 配置管理视图主组件
 * 构建包含装饰条、标题栏以及主体配置渲染器的表单外壳
 */
function ConfigView() {
    return (
        // 整个配置管理视图的外层包裹容器，应用特定的视图壳样式
        <div className="config-view-shell">
            {/* 卡片化包装容器，提供一致的阴影、圆角和背景表现 */}
            <div className="card config-card">
                {/* 视图头部区域，包含侧边装饰点缀和文字标题 */}
                <div className="config-header">
                    <div className="config-view-title-row">
                        {/* 标题左侧的彩色高亮修饰块 */}
                        <div className="config-view-title-accent"></div>
                        {/* 标题文本内容，使用六级标题排版样式 */}
                        <Typography variant="h6" className="config-view-title">配置管理</Typography>
                    </div>
                </div>
                {/* 实际执行核心配置项树渲染的子组件 */}
                <ConfigRenderer />
            </div>
        </div>
    );
}
