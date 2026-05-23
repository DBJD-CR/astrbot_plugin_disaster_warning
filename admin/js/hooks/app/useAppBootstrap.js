/**
 * @file useAppBootstrap.js
 * @description 应用冷启动数据初始化钩子。
 * 
 * 技术细节说明：
 * 1. 启动调度：在组件首次挂载时触发异步状态拉取。为了避开 React 初始渲染周期对 DOM 的集中争夺，
 *    通过 `setTimeout(..., 0)` 将高开销的 HTTP API 调用推迟到浏览器微任务队列执行完毕后的宏任务事件循环中。
 * 2. 垃圾回收：在组件卸载时，自动清理未执行的超时定时器句柄，防止内存泄露。
 */
function useAppBootstrap({
    refreshData,      // 刷新运行状态与心跳的方法
    fetchConfig,      // 读取插件全局配置的方法
    fetchConnections, // 载入各数据源网络链路状态的方法
    fetchStatistics,  // 读取灾害分类历史统计的方法
}) {
    React.useEffect(() => {
        // 利用 setTimeout(fn, 0) 将 API 载入任务推迟到下一个事件循环迭代中
        const timer = setTimeout(() => {
            refreshData();
            fetchConfig();
            fetchConnections();
            fetchStatistics();
        }, 0);

        // 卸载钩子时执行闭包垃圾回收，擦除定时器
        return () => clearTimeout(timer);
    }, [refreshData, fetchConfig, fetchConnections, fetchStatistics]);
}
