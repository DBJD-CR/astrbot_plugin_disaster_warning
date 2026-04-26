"""
统计加载服务。
负责统计管理器的 JSON / 数据库加载、历史迁移与内存状态恢复，
减少主管理器中的持久化读取与迁移编排职责。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from astrbot.api import logger

from ...services.identity.event_classifier import is_major_record


class StatsLoadService:
    """统计加载与迁移服务。"""

    def __init__(self, manager):
        self.manager = manager

    async def load(self) -> None:
        """加载统计数据。"""
        # 当前加载顺序是“先从 JSON 补基础状态，再从数据库恢复 recent_pushes 与聚合结果”，
        # 同时兼容历史版本仅使用 JSON 的迁移场景。
        json_has_events = False
        if self.manager.stats_file.exists():
            try:
                saved_stats = self.manager.repository.load_stats_file()
                json_has_events = bool(saved_stats.get("recent_pushes"))

                # 先剥离旧的近期事件列表，只把基础统计字段合并回当前内存态。
                recent_pushes_backup = saved_stats.pop("recent_pushes", None)
                self.manager._merge_stats(self.manager.stats, saved_stats)
                # 合并完成后恢复去重集合，避免历史记录在启动后被重复计数。
                self._restore_recorded_ids()

                if recent_pushes_backup:
                    saved_stats["recent_pushes"] = recent_pushes_backup
            except Exception as e:
                logger.error(f"[灾害预警] 加载统计数据失败: {e}")

        try:
            db_events = await self.manager.db.get_recent_events(500)
            if db_events:
                # 数据库是当前版本的主要历史来源，命中后优先以数据库结果覆盖近期事件缓存。
                logger.info(f"[灾害预警] 从数据库加载了 {len(db_events)} 条历史记录")
                self.manager.stats["recent_pushes"] = db_events
                self._restore_recorded_ids_from_db(db_events)

                db_stats = await self.manager.db.get_statistics()
                by_source_from_db = db_stats.get("by_source", {}) if db_stats else {}
                by_type_from_db = db_stats.get("by_type", {}) if db_stats else {}
                total_events_from_db = (
                    db_stats.get("total_events", 0) if db_stats else 0
                )
                if by_source_from_db or by_type_from_db or total_events_from_db:
                    # 把数据库聚合结果重新包回 defaultdict，保持后续写入逻辑无需额外判空。
                    if by_source_from_db:
                        self.manager.stats["by_source"] = defaultdict(
                            int, by_source_from_db
                        )
                    if by_type_from_db:
                        self.manager.stats["by_type"] = defaultdict(
                            int, by_type_from_db
                        )
                    if total_events_from_db:
                        self.manager.stats["total_events"] = int(total_events_from_db)

                if json_has_events and self.manager.stats_file.exists():
                    # 数据库恢复成功后，清理 JSON 中残留的旧事件列表，避免双份历史来源并存。
                    self._cleanup_json_recent_pushes()
            elif json_has_events:
                logger.info("[灾害预警] 检测到 JSON 历史记录，开始迁移到数据库...")
                await self.migrate_json_from_file()
        except Exception as e:
            logger.error(f"[灾害预警] 从数据库加载失败: {e}")

    async def migrate_json_from_file(self) -> None:
        """将 JSON 文件中的历史记录一次性迁移到数据库。"""
        try:
            saved_stats = self.manager.repository.load_stats_file()
            recent_pushes = saved_stats.get("recent_pushes", [])
            # 没有旧 recent_pushes 时说明无需迁移，直接返回。
            if not recent_pushes:
                return

            logger.info(
                f"[灾害预警] 开始迁移 {len(recent_pushes)} 条历史记录到数据库..."
            )
            migrated = 0
            failed_records = []
            for record in recent_pushes:
                try:
                    record["is_major"] = is_major_record(record)
                    await self.manager.db.insert_event(record)
                    migrated += 1
                except Exception as e:
                    logger.warning(f"[灾害预警] 迁移记录失败: {e}")
                    failed_records.append(record)

            logger.info(f"[灾害预警] 历史记录迁移完成，成功 {migrated} 条")

            saved_stats["recent_pushes"] = failed_records
            self.manager.repository.save_stats(saved_stats)
        except Exception as e:
            logger.error(f"[灾害预警] 迁移 JSON 历史记录失败: {e}")

    def _restore_recorded_ids(self) -> None:
        # 从 JSON 恢复最近事件集合，避免重启后短时间内重复统计同一批历史事件。
        if "recent_event_ids" in self.manager.stats:
            self.manager._recorded_event_ids.update(
                self.manager.stats["recent_event_ids"]
            )
        if "recent_source_event_ids" in self.manager.stats:
            self.manager._recorded_source_event_ids.update(
                self.manager.stats["recent_source_event_ids"]
            )

    def _restore_recorded_ids_from_db(self, db_events: list[dict[str, Any]]) -> None:
        """根据数据库事件列表恢复去重集合。"""
        for evt in db_events:
            unique_id = evt.get("unique_id")
            source_key = evt.get("source_id") or evt.get("source")
            if unique_id:
                self.manager._recorded_event_ids.add(unique_id)
                if source_key:
                    self.manager._recorded_source_event_ids.add(
                        f"{source_key}:{unique_id}"
                    )

    def _cleanup_json_recent_pushes(self) -> None:
        """清理 JSON 文件中已迁移或已被数据库接管的近期事件列表。"""
        try:
            saved_on_disk = self.manager.repository.load_stats_file()
            if saved_on_disk.get("recent_pushes"):
                saved_on_disk["recent_pushes"] = []
                self.manager.repository.save_stats(saved_on_disk)
                logger.debug("[灾害预警] 已清理 JSON 文件中残留的 recent_pushes")
        except Exception as e:
            logger.debug(f"[灾害预警] 清理 JSON recent_pushes 失败（非致命）: {e}")
