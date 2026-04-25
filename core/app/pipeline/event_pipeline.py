"""
事件处理流水线。
负责串联灾害事件的日志记录、推送、统计与 Web 实时通知，减少 DisasterWarningService 中的编排职责。
"""

from __future__ import annotations

from datetime import datetime

from astrbot.api import logger

from ...domain.event_models import EventEnvelope


class EventPipeline:
    """灾害事件处理流水线。

    该流水线聚焦“事件进入应用层后的统一后处理”，
    将推送、统计、管理端广播等横切逻辑从主服务中剥离，
    让主服务更专注于依赖装配与总入口编排。
    """

    def __init__(self, service):
        # 这里保存的是主服务实例引用，不复制任何运行时状态，
        # 以确保流水线始终读取到最新的配置、连接状态与消息推送结果。
        self.service = service

    async def handle(self, event: EventEnvelope) -> None:
        """执行事件主处理流程。"""
        # 这里保留 envelope 别名，便于后续阅读时明确：
        # 流水线处理的是已经标准化完成的事件对象，而非原始数据源消息。
        envelope = event

        # 第一阶段（在上游已完成）：解析器与主服务负责把原始消息转换为统一事件。
        # 流水线从这里开始只处理“标准化后的应用层事件”。

        # 第二阶段：按会话级配置执行推送。
        # 目标会话列表给出候选范围，会话配置读取函数则按会话返回生效配置，
        # 两者组合后，消息管理器即可在一次事件处理中执行差异化过滤与渲染。
        target_sessions = self.service.session_config_manager.list_target_sessions()
        push_result = await self.service.message_manager.push_event(
            event,
            target_sessions=target_sessions,
            session_config_getter=self.service.session_config_manager.get_effective_config,
        )
        if not push_result:
            # 未推送不一定代表异常，常见原因包括规则过滤未命中、会话未订阅，或事件被静默策略抑制。
            logger.debug(f"[灾害预警] 事件未产生实际推送: {envelope.id}")

        # 第三阶段：记录统计结果。
        # 统计记录与实际是否推送成功解耦，这样后续仍可分析规则过滤命中率、会话覆盖情况，以及“收到事件但未推送”的业务原因。
        await self.service.statistics_manager.record_push(
            event,
            pushed_sessions=self.service.message_manager.last_success_sessions,
        )

        # 第四阶段：向管理端广播轻量摘要。
        # 这里只发送最小必要字段，避免把完整事件对象直接传给管理端，
        # 从而降低实时面板负载，并减少内部模型字段外露带来的耦合风险。
        if self.service.web_admin_server:
            try:
                event_summary = {
                    "id": envelope.id,
                    "type": envelope.event_type,
                    "source": envelope.source_id,
                    "time": datetime.now().isoformat(),
                }
                await self.service.web_admin_server.notify_event(event_summary)
            except Exception as ws_e:
                # 管理端广播失败不影响主链路；用户侧推送与统计已完成，因此这里按可降级的旁路处理。
                logger.debug(f"[灾害预警] WebSocket 通知失败: {ws_e}")
