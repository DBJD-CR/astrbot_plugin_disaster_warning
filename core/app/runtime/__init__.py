"""
core.app.runtime 模块。

该包包含灾害预警服务的运行时辅助组件：
1. 缓存管理服务 (disaster_service_cache.py)；
2. 生命周期服务 (disaster_service_lifecycle.py)；
3. 断线重连机制 (disaster_service_reconnect.py)；
4. 消息通知服务 (disaster_service_notice.py)；
5. 运行状态管理服务 (disaster_service_status.py)；
6. 运行时核心网络/轮询驱动服务 (disaster_service_runtime.py)。
"""
