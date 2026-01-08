"""
报数控制器
"""

from collections import defaultdict

from astrbot.api import logger

from ...models.data_source_config import get_sources_needing_report_control
from ...models.models import DataSource, DisasterEvent, EarthquakeData


class ReportCountController:
    """报数控制器 - 仅对EEW数据源生效"""

    def __init__(
        self,
        cea_cwa_report_n: int = 1,
        jma_report_n: int = 3,
        gq_report_n: int = 5,
        final_report_always_push: bool = True,
        ignore_non_final_reports: bool = False,
    ):
        self.cea_cwa_report_n = cea_cwa_report_n
        self.jma_report_n = jma_report_n
        self.gq_report_n = gq_report_n
        self.final_report_always_push = final_report_always_push
        self.ignore_non_final_reports = ignore_non_final_reports
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

        # 确定当前数据源对应的报数限制和最终报支持情况
        push_every_n = self.cea_cwa_report_n  # 默认值
        supports_final = True

        if "jma" in source_id:
            push_every_n = self.jma_report_n
        elif "global_quake" in source_id:
            push_every_n = self.gq_report_n
            supports_final = False
        elif "cea" in source_id or "cwa" in source_id:
            supports_final = False

        is_final = getattr(earthquake, "is_final", False) if supports_final else False

        # 最终报总是推送
        if is_final and self.final_report_always_push:
            logger.debug(f"[灾害预警] 事件 {event_id} 是最终报，允许推送")
            return True

        # 第1报总是推送 (即使开启了忽略非最终报)
        if current_report == 1:
            logger.debug(f"[灾害预警] 事件 {event_id} 是第1报，允许推送")
            return True

        # 如果开启了"忽略非最终报"，且当前不是最终报或第1报，直接过滤
        if self.ignore_non_final_reports and not is_final:
            logger.debug(
                f"[灾害预警] 事件 {event_id} 第 {current_report} 报，因开启'忽略非最终报'被过滤"
            )
            return False

        # 检查报数控制
        if push_every_n <= 0:
            push_every_n = 1  # 防止除以零，默认每报都推

        if current_report % push_every_n == 0:
            logger.debug(
                f"[灾害预警] 事件 {event_id} 第 {current_report} 报，符合报数控制规则 (n={push_every_n})"
            )
            return True

        logger.debug(
            f"[灾害预警] 事件 {event_id} 第 {current_report} 报，被报数控制过滤 (n={push_every_n})"
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
