"""
报数控制器
"""
from collections import defaultdict
from astrbot.api import logger
from ...models.models import DataSource, DisasterEvent, EarthquakeData
from ...models.data_source_config import get_sources_needing_report_control

class ReportCountController:
    """报数控制器 - 仅对EEW数据源生效"""

    def __init__(
        self,
        push_every_n_reports: int = 3,
        first_report_always_push: bool = True,
        final_report_always_push: bool = True,
    ):
        self.push_every_n_reports = push_every_n_reports
        self.first_report_always_push = first_report_always_push
        self.final_report_always_push = final_report_always_push
        # 记录每个事件的报数推送情况
        self.event_report_counts: dict[str, int] = defaultdict(int)

    def should_push_report(self, event: DisasterEvent) -> bool:
        """判断是否推送该报数"""
        if not isinstance(event.data, EarthquakeData):
            return True  # 非地震事件直接推送

        earthquake = event.data
        source_id = self._get_source_id(event)

        # 只对需要报数控制的数据源生效
        if source_id not in get_sources_needing_report_control():
            return True

        event_id = earthquake.event_id or earthquake.id
        current_report = getattr(earthquake, "updates", 1)
        is_final = getattr(earthquake, "is_final", False)

        # 最终报总是推送
        if is_final and self.final_report_always_push:
            logger.debug(f"[灾害预警] 事件 {event_id} 是最终报，允许推送")
            return True

        # 第1报总是推送
        if current_report == 1 and self.first_report_always_push:
            logger.debug(f"[灾害预警] 事件 {event_id} 是第1报，允许推送")
            return True

        # 检查报数控制
        if current_report % self.push_every_n_reports == 0:
            logger.debug(
                f"[灾害预警] 事件 {event_id} 第 {current_report} 报，符合报数控制规则"
            )
            return True

        logger.debug(
            f"[灾害预警] 事件 {event_id} 第 {current_report} 报，被报数控制过滤"
        )
        return False

    def _get_source_id(self, event: DisasterEvent) -> str:
        """获取事件的数据源ID"""
        # 将DataSource映射到我们的source_id
        source_mapping = {
            DataSource.FAN_STUDIO_CEA.value: "cea_fanstudio",
            DataSource.WOLFX_CENC_EEW.value: "cea_wolfx",
            DataSource.FAN_STUDIO_CWA.value: "cwa_fanstudio",
            DataSource.WOLFX_CWA_EEW.value: "cwa_wolfx",
            DataSource.FAN_STUDIO_JMA.value: "jma_fanstudio",
            DataSource.P2P_EEW.value: "jma_p2p",
            DataSource.WOLFX_JMA_EEW.value: "jma_wolfx",
            DataSource.GLOBAL_QUAKE.value: "global_quake",
        }

        return source_mapping.get(event.source.value, "")
