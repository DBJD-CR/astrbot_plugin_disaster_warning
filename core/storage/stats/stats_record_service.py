"""
统计记录更新服务。
负责事件摘要记录在 recent_pushes / major_events 中的合并、数据库写入与列表裁剪，
减少 StatisticsManager 中的写模型编排职责。
"""

from __future__ import annotations

from astrbot.api import logger

from ...domain.event_models import EarthquakeEvent, EventEnvelope, TyphoonEvent
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
                    # 台风事件可能已通过 EQSC 历史重建写入数据库但不在内存列表中，
                    # 此时走 insert_event 会创建重复主表记录。
                    # 先检查数据库是否已有该台风，若有则走 update_event 追加新报次。
                    if isinstance(event.event, TyphoonEvent):
                        existing = await self.manager.db.find_event_by_real_id(
                            push_record.get("real_event_id"),
                            push_record.get("source"),
                        )
                        if existing:
                            # 数据库已有记录（来自 EQSC 重建），走更新而非插入
                            push_record["update_count"] = (
                                int(existing.get("update_count", 1) or 1) + 1
                            )
                            await self.manager.db.update_event(
                                push_record.get("source"), push_record
                            )
                        else:
                            await self.manager.db.insert_event(push_record)
                    else:
                        await self.manager.db.insert_event(push_record)
                except Exception as e:
                    logger.debug(f"[灾害预警] 保存到数据库失败（可能已存在）: {e}")

        if len(target_list) > max_len:
            del target_list[max_len:]
