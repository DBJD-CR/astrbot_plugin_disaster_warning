"""
海啸历史重复记录清理服务。

将旧版「同事件多次 insert」产生的脏数据折叠为：
- events 主表：每组稳定事件键仅保留最新一行
- event_updates：同组历史行转为报次快照，便于前端多报时间线
- 本文件将在后续版本中视情况移除

不写入 DatabaseManager 本体，仅复用其连接生命周期。
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger

from .source_compat import normalize_source_name


class TsunamiHistoryCleanupService:
    """海啸历史脏数据清理服务。"""

    CN_SOURCE_ALIASES = ("fan_studio_tsunami", "china_tsunami_fanstudio")

    def __init__(self, db):
        """
        Args:
            db: DatabaseManager 实例（复用连接与 initialize 生命周期）。
        """
        self.db = db
        self._done = False

    @staticmethod
    def _normalize_event_key(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if "|" in text:
            return text.split("|", 1)[-1].strip()
        return text

    @classmethod
    def _group_key(cls, row: dict[str, Any]) -> str:
        unique_id = str(row.get("unique_id") or "").strip()
        real_event_id = str(row.get("real_event_id") or "").strip()
        bare_unique = cls._normalize_event_key(unique_id)
        if bare_unique:
            return f"uid:{bare_unique}"
        if real_event_id:
            return f"rid:{real_event_id}"
        return f"id:{row.get('id')}"

    @staticmethod
    def _row_sort_key(row: dict[str, Any]) -> tuple:
        return (
            str(row.get("updated_at") or ""),
            str(row.get("time") or ""),
            str(row.get("created_at") or ""),
            int(row.get("id") or 0),
        )

    @classmethod
    def _preferred_source(cls, rows: list[dict[str, Any]]) -> str:
        for row in reversed(rows):
            source = str(row.get("source") or row.get("source_id") or "").strip()
            if not source:
                continue
            normalized = normalize_source_name(source) or source
            if normalized:
                return normalized
        return "china_tsunami_fanstudio"

    @classmethod
    def _preferred_real_event_id(cls, rows: list[dict[str, Any]]) -> str:
        for row in reversed(rows):
            real_event_id = str(row.get("real_event_id") or "").strip()
            if real_event_id:
                return real_event_id
            bare = cls._normalize_event_key(row.get("unique_id"))
            if bare:
                return bare
        return ""

    @classmethod
    def _preferred_unique_id(
        cls, rows: list[dict[str, Any]], *, source: str, real_event_id: str
    ) -> str:
        # 优先保留已带 source| 前缀的规范 unique_id
        for row in reversed(rows):
            unique_id = str(row.get("unique_id") or "").strip()
            if unique_id and "|" in unique_id:
                return unique_id
        bare = cls._normalize_event_key(real_event_id) or cls._normalize_event_key(
            rows[-1].get("unique_id") if rows else ""
        )
        if bare and source:
            return f"{source}|{bare}"
        return bare

    async def run_once(self, *, force: bool = False) -> dict[str, int]:
        """执行一次清理；默认进程内只跑一次。"""
        if self._done and not force:
            return {"kept": 0, "deleted": 0, "groups": 0, "skipped": 1}

        connection = await self.db._ensure_connection()
        cursor = await connection.cursor()
        try:
            await cursor.execute(
                """
                SELECT *
                FROM events
                WHERE type='tsunami'
                ORDER BY id ASC
                """
            )
            rows = [dict(item) for item in await cursor.fetchall()]
            if not rows:
                self._done = True
                return {"kept": 0, "deleted": 0, "groups": 0, "skipped": 0}

            groups: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                groups.setdefault(self._group_key(row), []).append(row)

            multi_groups = [items for items in groups.values() if len(items) > 1]
            if not multi_groups:
                self._done = True
                logger.debug("[灾害预警] 海啸历史清理：未发现重复组，跳过")
                return {
                    "kept": len(groups),
                    "deleted": 0,
                    "groups": 0,
                    "skipped": 0,
                }

            delete_ids: list[int] = []
            kept = 0
            for items in groups.values():
                if len(items) == 1:
                    # 单行也尽量补齐 real_event_id / source_id
                    only = items[0]
                    await self._normalize_keep_row(cursor, [only], keep=only)
                    kept += 1
                    continue

                items_sorted = sorted(items, key=self._row_sort_key)
                keep = items_sorted[-1]
                await self._fold_group_to_keep(cursor, items_sorted, keep=keep)
                kept += 1
                for item in items_sorted[:-1]:
                    delete_ids.append(int(item["id"]))

            if delete_ids:
                placeholders = ",".join("?" for _ in delete_ids)
                # 重复主表行对应的 updates 一并删除；同组历史已转写到 keep 的 updates
                await cursor.execute(
                    f"DELETE FROM event_updates WHERE event_id IN ({placeholders})",
                    tuple(delete_ids),
                )
                await cursor.execute(
                    f"DELETE FROM events WHERE id IN ({placeholders})",
                    tuple(delete_ids),
                )

            await connection.commit()
            self._done = True

            try:
                from ..network.admin.api.events_routes import invalidate_sources_cache

                invalidate_sources_cache()
            except Exception:
                pass

            result = {
                "kept": kept,
                "deleted": len(delete_ids),
                "groups": len(multi_groups),
                "skipped": 0,
            }
            logger.info(
                "[灾害预警] 海啸历史重复清理完成: "
                f"保留 {kept}, 删除 {len(delete_ids)}, 多报折叠 {len(multi_groups)}"
            )
            return result
        except Exception as exc:
            logger.error(f"[灾害预警] 海啸历史清理失败: {exc}")
            await connection.rollback()
            raise

    async def _normalize_keep_row(
        self,
        cursor,
        rows: list[dict[str, Any]],
        *,
        keep: dict[str, Any],
    ) -> None:
        source = self._preferred_source(rows)
        real_event_id = self._preferred_real_event_id(rows)
        unique_id = self._preferred_unique_id(
            rows, source=source, real_event_id=real_event_id
        )
        update_count = max(len(rows), int(keep.get("update_count", 1) or 1))
        await cursor.execute(
            """
            UPDATE events
            SET source = ?,
                source_id = ?,
                real_event_id = COALESCE(NULLIF(?, ''), real_event_id),
                unique_id = COALESCE(NULLIF(?, ''), unique_id),
                update_count = ?,
                report_num = COALESCE(report_num, ?)
            WHERE id = ?
            """,
            (
                source,
                source,
                real_event_id or None,
                unique_id or None,
                update_count,
                update_count,
                keep["id"],
            ),
        )

    async def _fold_group_to_keep(
        self,
        cursor,
        items_sorted: list[dict[str, Any]],
        *,
        keep: dict[str, Any],
    ) -> None:
        """把同组历史行折叠到 keep，并写入 event_updates 报次快照。"""
        await self._normalize_keep_row(cursor, items_sorted, keep=keep)

        keep_id = int(keep["id"])
        # 清掉 keep 原有 updates，按时间线重建
        await cursor.execute(
            "DELETE FROM event_updates WHERE event_id = ?",
            (keep_id,),
        )

        for index, item in enumerate(items_sorted, start=1):
            description = item.get("description")
            level = item.get("level")
            magnitude = item.get("magnitude")
            depth = item.get("depth")
            latitude = item.get("latitude")
            longitude = item.get("longitude")
            event_time = item.get("time")
            source_event_id = (
                str(item.get("real_event_id") or "").strip()
                or self._normalize_event_key(item.get("unique_id"))
                or str(item.get("id") or "")
            )
            recorded_at = (
                item.get("updated_at") or item.get("created_at") or item.get("time")
            )
            await cursor.execute(
                """
                INSERT INTO event_updates
                    (event_id, source_event_id, report_num, magnitude, depth,
                     description, level, wind_speed, pressure, latitude, longitude,
                     time, recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    keep_id,
                    source_event_id,
                    index,
                    magnitude,
                    depth,
                    description,
                    level,
                    item.get("max_wave_height") or item.get("wind_speed"),
                    item.get("pressure"),
                    latitude,
                    longitude,
                    event_time,
                    recorded_at,
                ),
            )
