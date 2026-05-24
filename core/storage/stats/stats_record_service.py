"""
统计记录更新服务。
负责事件摘要记录在 recent_pushes / major_events 中的合并、数据库写入与列表裁剪，
减少 StatisticsManager 中的写模型编排职责。
"""

from __future__ import annotations

from astrbot.api import logger

from ...domain.event_models import EarthquakeEvent, EventEnvelope
from .event_record_factory import EventRecordFactory
from .event_record_merger import EventRecordMerger


class StatsRecordService:
    """统计记录更新服务。"""

    def __init__(self, manager):
        self.manager = manager

    async def update_push_list(
        self,
        target_list: list,
        event: EventEnvelope,
        *,
        source_id: str,
        event_unique_id: str,
        current_time: str,
        max_len: int = 100,
        is_major: bool = False,
        persist_db: bool = True,
    ) -> None:
        """更新事件摘要列表（支持合并更新与数据库同步）。"""
        # recent_pushes / major_events 在统计侧统一视为事件摘要缓存，仅通过 is_major / max_len 控制差异。
        description = (
            self.manager.event_support_service.get_event_description_from_envelope(
                event
            )
        )
        earthquake_level = (
            self.manager.event_support_service.get_earthquake_level(event.event)
            if isinstance(event.event, EarthquakeEvent)
            else None
        )

        updated_record = EventRecordMerger.merge_existing_record(
            target_list,
            event,
            source_id=source_id,
            event_unique_id=event_unique_id,
            current_time=current_time,
            description=description,
            earthquake_level=earthquake_level,
        )

        if updated_record is not None:
            # 命中已有记录时走 update，而非重复 insert，保证数据库中的同一事件多报按更新演进。
            if persist_db:
                try:
                    if is_major:
                        updated_record["is_major"] = True
                    await self.manager.db.update_event(source_id, updated_record)
                except Exception as e:
                    logger.error(f"[灾害预警] 更新数据库事件失败: {e}")
        else:
            push_record = EventRecordFactory.build_base_record(
                event,
                current_time=current_time,
                event_unique_id=event_unique_id,
                description=description,
                earthquake_level=earthquake_level,
            )
            target_list.insert(0, push_record)

            if persist_db:
                try:
                    if is_major:
                        push_record["is_major"] = True
                    await self.manager.db.insert_event(push_record)
                except Exception as e:
                    logger.debug(f"[灾害预警] 保存到数据库失败（可能已存在）: {e}")

        if len(target_list) > max_len:
            del target_list[max_len:]
