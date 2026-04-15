"""
报数控制器
"""

from collections import defaultdict

from astrbot.api import logger

from ...models.data_source_config import get_sources_needing_report_control
from ...models.models import DisasterEvent, EarthquakeData
from ..support.event_metadata import resolve_report_num, resolve_source_id


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

    def should_push_report(
        self,
        event: DisasterEvent,
        *,
        commit_state: bool = True,
    ) -> bool:
        """判断是否推送该报数。

        参数:
            commit_state: 是否提交本次判定产生的状态副作用。
                在多会话预筛选阶段应传入 False，避免前面的会话判定污染后续会话。
        """
        # 报数控制器只作用于地震类多报事件，其他灾种不参与“第 N 报推送”判断。
        if not isinstance(event.data, EarthquakeData):
            return True  # 非地震事件直接推送

        earthquake = event.data
        source_id = resolve_source_id(event)

        # 只对需要报数控制的数据源生效
        if source_id not in get_sources_needing_report_control():
            return True

        event_id = earthquake.event_id or earthquake.id
        current_report = resolve_report_num(event) or 1

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

        # “忽略非最终报”仅应作用于支持最终报语义的数据源。
        # 对 Global Quake / CEA / CWA 等无最终报标识的数据源，不能据此直接过滤，
        # 否则会退化成“只推第一报”。
        if self.ignore_non_final_reports and supports_final and not is_final:
            logger.debug(
                f"[灾害预警] 事件 {event_id} 第 {current_report} 报，因开启'忽略非最终报'被过滤"
            )
            return False

        # 报数控制的核心规则：第1报默认放行，其余按 N 的倍数控制；
        # push_every_n 非法时兜底为 1，等价于“每报都推”。
        if push_every_n <= 0:
            push_every_n = 1  # 防止除以零，默认每报都推

        should_push = current_report % push_every_n == 0
        if should_push:
            logger.debug(
                f"[灾害预警] 事件 {event_id} 第 {current_report} 报，符合报数控制规则 (n={push_every_n})"
            )
        else:
            logger.debug(
                f"[灾害预警] 事件 {event_id} 第 {current_report} 报，被报数控制过滤 (n={push_every_n})"
            )

        if commit_state:
            self.event_report_counts[event_id] = current_report

        return should_push
