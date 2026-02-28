"""
灾害预警插件 - 数据库管理模块
使用 SQLite 存储历史事件数据（异步版本，使用 aiosqlite）

Schema v2：
  events        - 每个物理事件一行（按 real_event_id+source 去重）
  event_updates - 每次推送/更新一行（原 history JSON 拆解）
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from astrbot.api import logger

from ...utils.converters import is_major_event


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, db_path: Path):
        """
        初始化数据库管理器

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.connection: aiosqlite.Connection | None = None

    # ──────────────────────────── 初始化 / 迁移 ────────────────────────────

    async def initialize(self):
        """异步初始化数据库，检测并执行必要的 schema 迁移"""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = await aiosqlite.connect(str(self.db_path))
            self.connection.row_factory = aiosqlite.Row

            cursor = await self.connection.cursor()
            await self._ensure_schema(cursor)
            await self.connection.commit()
            logger.info(f"[灾害预警] 数据库初始化完成: {self.db_path}")
        except Exception as e:
            logger.error(f"[灾害预警] 数据库初始化失败: {e}")
            raise

    async def _ensure_schema(self, cursor):
        """检测并补齐 schema 列，创建表和索引（幂等）"""
        await cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        events_exists = bool(await cursor.fetchone())

        if events_exists:
            # 补齐早期 v2 版本可能缺失的列，避免建索引失败
            await cursor.execute("PRAGMA table_info(events)")
            columns = {row[1] for row in await cursor.fetchall()}
            if "source_id" not in columns:
                await cursor.execute("ALTER TABLE events ADD COLUMN source_id TEXT")
            if "subtitle" not in columns:
                await cursor.execute("ALTER TABLE events ADD COLUMN subtitle TEXT")

        await self._create_tables(cursor)

    async def _create_tables(self, cursor):
        """创建 v2 表结构（幂等）"""
        await cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                real_event_id   TEXT,
                unique_id       TEXT,
                type            TEXT NOT NULL,
                source          TEXT NOT NULL,
                source_id       TEXT,
                description     TEXT,
                subtitle        TEXT,
                latitude        REAL,
                longitude       REAL,
                magnitude       REAL,
                depth           REAL,
                report_num      INTEGER,
                weather_type_code TEXT,
                level           TEXT,
                time            TEXT,
                is_major        INTEGER DEFAULT 0,
                update_count    INTEGER DEFAULT 1,
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS event_updates (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id        INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                source_event_id TEXT,
                report_num      INTEGER,
                magnitude       REAL,
                depth           REAL,
                description     TEXT,
                time            TEXT,
                recorded_at     TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for sql in (
            "CREATE INDEX IF NOT EXISTS idx_ev_real_id   ON events(real_event_id)",
            "CREATE INDEX IF NOT EXISTS idx_ev_unique_id ON events(unique_id)",
            "CREATE INDEX IF NOT EXISTS idx_ev_source    ON events(source)",
            "CREATE INDEX IF NOT EXISTS idx_ev_type      ON events(type)",
            "CREATE INDEX IF NOT EXISTS idx_ev_source_id ON events(source_id)",
            "CREATE INDEX IF NOT EXISTS idx_ev_time      ON events(time)",
            "CREATE INDEX IF NOT EXISTS idx_ev_is_major  ON events(is_major)",
            "CREATE INDEX IF NOT EXISTS idx_upd_event_id ON event_updates(event_id)",
        ):
            await cursor.execute(sql)

    # ──────────────────────────── 写操作 ────────────────────────────

    async def insert_event(self, event_data: dict[str, Any]) -> int:
        """
        插入新事件，同时在 event_updates 记录首次推送。
        返回新记录的数据库 id。
        """
        try:
            cursor = await self.connection.cursor()
            is_major = bool(event_data.get("is_major")) or is_major_event(event_data)

            await cursor.execute(
                """
                INSERT INTO events (
                    real_event_id, unique_id, type, source, source_id,
                    description, subtitle, latitude, longitude,
                    magnitude, depth, report_num,
                    weather_type_code, level, time,
                    is_major, update_count
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event_data.get("real_event_id"),
                    event_data.get("unique_id"),
                    event_data.get("type"),
                    event_data.get("source"),
                    event_data.get("source_id"),
                    event_data.get("description"),
                    event_data.get("subtitle"),
                    event_data.get("latitude"),
                    event_data.get("longitude"),
                    event_data.get("magnitude"),
                    event_data.get("depth"),
                    event_data.get("report_num"),
                    event_data.get("weather_type_code"),
                    event_data.get("level"),
                    event_data.get("time"),
                    1 if is_major else 0,
                    event_data.get("update_count", 1),
                ),
            )
            new_id = cursor.lastrowid

            await cursor.execute(
                """
                INSERT INTO event_updates
                    (event_id, source_event_id, report_num, magnitude, depth, description, time)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    new_id,
                    event_data.get("event_id"),
                    event_data.get("report_num"),
                    event_data.get("magnitude"),
                    event_data.get("depth"),
                    event_data.get("description"),
                    event_data.get("time"),
                ),
            )

            await self.connection.commit()
            return new_id
        except Exception as e:
            logger.error(f"[灾害预警] 插入事件失败: {e}")
            await self.connection.rollback()
            raise

    async def update_event(self, source: str, event_data: dict[str, Any]) -> bool:
        """
        更新已有事件（以 real_event_id+source 或 unique_id+source 查找），
        同时在 event_updates 追加一条更新记录。
        """
        try:
            cursor = await self.connection.cursor()
            real_event_id = event_data.get("real_event_id")
            unique_id = event_data.get("unique_id")
            is_major = bool(event_data.get("is_major")) or is_major_event(event_data)

            # 查找 events.id
            db_id = None
            if real_event_id:
                await cursor.execute(
                    "SELECT id FROM events WHERE real_event_id=? AND source=? LIMIT 1",
                    (real_event_id, source),
                )
                r = await cursor.fetchone()
                if r:
                    db_id = r[0]
            if db_id is None and unique_id:
                await cursor.execute(
                    "SELECT id FROM events WHERE unique_id=? AND source=? LIMIT 1",
                    (unique_id, source),
                )
                r = await cursor.fetchone()
                if r:
                    db_id = r[0]

            if db_id is None:
                return False

            await cursor.execute(
                """
                UPDATE events SET
                    source_id         = ?,
                    description       = ?,
                    subtitle          = ?,
                    latitude          = ?,
                    longitude         = ?,
                    magnitude         = ?,
                    depth             = ?,
                    report_num        = ?,
                    time              = ?,
                    update_count      = ?,
                    weather_type_code = ?,
                    level             = ?,
                    is_major          = ?,
                    updated_at        = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    event_data.get("source_id"),
                    event_data.get("description"),
                    event_data.get("subtitle"),
                    event_data.get("latitude"),
                    event_data.get("longitude"),
                    event_data.get("magnitude"),
                    event_data.get("depth"),
                    event_data.get("report_num"),
                    event_data.get("time"),
                    event_data.get("update_count", 1),
                    event_data.get("weather_type_code"),
                    event_data.get("level"),
                    1 if is_major else 0,
                    db_id,
                ),
            )

            await cursor.execute(
                """
                INSERT INTO event_updates
                    (event_id, source_event_id, report_num, magnitude, depth, description, time)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    db_id,
                    event_data.get("event_id"),
                    event_data.get("report_num"),
                    event_data.get("magnitude"),
                    event_data.get("depth"),
                    event_data.get("description"),
                    event_data.get("time"),
                ),
            )

            await self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"[灾害预警] 更新事件失败: {e}")
            await self.connection.rollback()
            raise

    # ──────────────────────────── 读操作 ────────────────────────────

    async def _attach_history(self, events: list[dict]) -> list[dict]:
        """为事件列表批量附加 event_updates（重建 history 数组）"""
        if not events:
            return events
        # 用 json_each(?) 传递 ID 列表，避免动态拼接 IN 子句
        ids = json.dumps([e["id"] for e in events])
        cursor = await self.connection.cursor()
        await cursor.execute(
            """
            SELECT * FROM event_updates
            WHERE event_id IN (SELECT value FROM json_each(?))
            ORDER BY event_id, recorded_at ASC
            """,
            (ids,),
        )
        rows = await cursor.fetchall()

        updates_by_event: dict[int, list] = {}
        for row in rows:
            r = dict(row)
            updates_by_event.setdefault(r["event_id"], []).append(r)

        for event in events:
            updates = updates_by_event.get(event["id"], [])
            # 只有 update_count > 1（即后端明确记录了多报次）时才返回历史条目
            # 这样可以避免 weather/tsunami 事件因重推写入多条 event_updates 但 update_count=1
            # 而在前端被错误地计入更新数量
            if event.get("update_count", 1) > 1 and len(updates) > 1:
                event["history"] = list(reversed(updates[:-1]))
            else:
                event["history"] = []

        return events

    def _append_source_filter_clause(
        self,
        sources: list[str] | None,
        clauses: list[str],
        params: list[Any],
    ) -> None:
        """追加数据源过滤子句：优先 source_id，兼容历史 source。"""
        normalized_sources = [s for s in (sources or []) if s]
        if not normalized_sources:
            return

        placeholders = ",".join(["?"] * len(normalized_sources))
        clauses.append(
            "(COALESCE(NULLIF(source_id, ''), source) "
            f"IN ({placeholders}) OR source IN ({placeholders}))"
        )
        params.extend(normalized_sources)
        params.extend(normalized_sources)

    async def get_recent_events(self, limit: int = 500) -> list[dict[str, Any]]:
        """获取最近事件（含 history），按更新时间倒序"""
        try:
            cursor = await self.connection.cursor()
            await cursor.execute(
                "SELECT * FROM events ORDER BY updated_at DESC, time DESC LIMIT ?",
                (limit,),
            )
            events = [dict(row) for row in await cursor.fetchall()]
            return await self._attach_history(events)
        except Exception as e:
            logger.error(f"[灾害预警] 查询最近事件失败: {e}")
            return []

    async def find_event_by_real_id(
        self, real_event_id: str, source: str
    ) -> dict[str, Any] | None:
        """按 real_event_id + source 查找事件"""
        try:
            cursor = await self.connection.cursor()
            await cursor.execute(
                "SELECT * FROM events WHERE real_event_id=? AND source=? LIMIT 1",
                (real_event_id, source),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            events = await self._attach_history([dict(row)])
            return events[0]
        except Exception as e:
            logger.error(f"[灾害预警] 查找事件失败: {e}")
            return None

    async def get_major_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取重大事件（is_major=1），按同源同事件去重后返回最新记录"""
        try:
            cursor = await self.connection.cursor()
            await cursor.execute(
                """
                WITH ranked AS (
                    SELECT
                        *,
                        ROW_NUMBER() OVER (
                            PARTITION BY
                                source,
                                COALESCE(real_event_id, unique_id, CAST(id AS TEXT))
                            ORDER BY
                                updated_at DESC,
                                time DESC,
                                id DESC
                        ) AS rn
                    FROM events
                    WHERE is_major = 1
                      AND (
                          type != 'weather_alarm'
                          OR (
                              -- 气象预警仅保留红/橙级别：优先 level，缺失时回退 description
                              (
                                  COALESCE(TRIM(level), '') != ''
                                  AND (level LIKE '%红%' OR level LIKE '%橙%')
                              )
                              OR (
                                  COALESCE(TRIM(level), '') = ''
                                  AND (description LIKE '%红%' OR description LIKE '%橙%')
                              )
                          )
                      )
                )
                SELECT *
                FROM ranked
                WHERE rn = 1
                ORDER BY time DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            events = [dict(row) for row in await cursor.fetchall()]
            return await self._attach_history(events)
        except Exception as e:
            logger.error(f"[灾害预警] 查询重大事件失败: {e}")
            return []

    async def get_events_count(
        self,
        event_type: str | None = None,
        sources: list[str] | None = None,
        min_magnitude: float | None = None,
    ) -> int:
        """获取事件总数（支持按类型、数据源、最小震级过滤）"""
        try:
            cursor = await self.connection.cursor()
            clauses = []
            params: list[Any] = []

            if event_type:
                clauses.append("type=?")
                params.append(event_type)

            self._append_source_filter_clause(sources, clauses, params)

            if min_magnitude is not None:
                clauses.append(
                    "(type IN ('earthquake', 'earthquake_warning') AND magnitude IS NOT NULL AND magnitude >= ?)"
                )
                params.append(min_magnitude)

            where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            await cursor.execute(
                f"SELECT COUNT(*) FROM events{where_sql}",
                tuple(params),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"[灾害预警] 查询事件总数失败: {e}")
            return 0

    async def get_events_paginated(
        self,
        page: int = 1,
        limit: int = 50,
        event_type: str | None = None,
        sources: list[str] | None = None,
        min_magnitude: float | None = None,
        magnitude_order: str | None = None,
    ) -> list[dict[str, Any]]:
        """分页获取事件（含 history，支持按类型、数据源、最小震级过滤与震级排序）"""
        try:
            offset = (page - 1) * limit
            cursor = await self.connection.cursor()

            clauses = []
            params: list[Any] = []

            if event_type:
                clauses.append("type=?")
                params.append(event_type)

            self._append_source_filter_clause(sources, clauses, params)

            if min_magnitude is not None:
                clauses.append(
                    "(type IN ('earthquake', 'earthquake_warning') AND magnitude IS NOT NULL AND magnitude >= ?)"
                )
                params.append(min_magnitude)

            where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""

            normalized_order = (magnitude_order or "").lower().strip()
            if normalized_order in {"asc", "desc"}:
                order_sql = (
                    " ORDER BY "
                    "CASE WHEN magnitude IS NULL THEN 1 ELSE 0 END ASC, "
                    f"magnitude {normalized_order.upper()}, "
                    "updated_at DESC, time DESC"
                )
            else:
                order_sql = " ORDER BY updated_at DESC, time DESC"

            sql = f"SELECT * FROM events{where_sql}{order_sql} LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            await cursor.execute(sql, tuple(params))

            events = [dict(row) for row in await cursor.fetchall()]
            return await self._attach_history(events)
        except Exception as e:
            logger.error(f"[灾害预警] 分页查询失败: {e}")
            return []

    async def get_event_source_options(
        self, event_type: str | None = None
    ) -> list[dict[str, str]]:
        """获取事件数据源选项（value/label），value 优先 source_id，label 兼容 source。"""
        try:
            cursor = await self.connection.cursor()
            if event_type:
                await cursor.execute(
                    """
                    SELECT
                        COALESCE(NULLIF(source_id, ''), source) AS source_value,
                        MIN(source) AS source_label
                    FROM events
                    WHERE type=?
                    GROUP BY COALESCE(NULLIF(source_id, ''), source)
                    ORDER BY source_value ASC
                    """,
                    (event_type,),
                )
            else:
                await cursor.execute(
                    """
                    SELECT
                        COALESCE(NULLIF(source_id, ''), source) AS source_value,
                        MIN(source) AS source_label
                    FROM events
                    GROUP BY COALESCE(NULLIF(source_id, ''), source)
                    ORDER BY source_value ASC
                    """
                )
            rows = await cursor.fetchall()
            result: list[dict[str, str]] = []
            for row in rows:
                source_value = row[0] if row and row[0] else ""
                source_label = row[1] if row and row[1] else source_value
                if source_value:
                    result.append(
                        {
                            "source_value": str(source_value),
                            "source_label": str(source_label),
                        }
                    )
            return result
        except Exception as e:
            logger.error(f"[灾害预警] 查询数据源选项失败: {e}")
            return []

    async def get_event_sources(self, event_type: str | None = None) -> list[str]:
        """获取事件数据源列表（可按类型过滤，兼容旧前端）"""
        options = await self.get_event_source_options(event_type)
        return [
            opt.get("source_label", "") for opt in options if opt.get("source_label")
        ]

    async def get_statistics(self) -> dict[str, Any]:
        """获取数据库统计信息"""
        try:
            cursor = await self.connection.cursor()
            await cursor.execute("SELECT COUNT(*) FROM events")
            total = (await cursor.fetchone())[0]

            await cursor.execute("SELECT type, COUNT(*) FROM events GROUP BY type")
            by_type = {r[0]: r[1] for r in await cursor.fetchall()}

            await cursor.execute("SELECT source, COUNT(*) FROM events GROUP BY source")
            by_source = {r[0]: r[1] for r in await cursor.fetchall()}

            db_size_mb = self.db_path.stat().st_size / (1024 * 1024)
            return {
                "total_events": total,
                "by_type": by_type,
                "by_source": by_source,
                "database_size_mb": round(db_size_mb, 2),
            }
        except Exception as e:
            logger.error(f"[灾害预警] 获取统计信息失败: {e}")
            return {}

    async def clear_all_events(self) -> bool:
        """清除所有事件记录"""
        try:
            cursor = await self.connection.cursor()
            await cursor.execute("DELETE FROM event_updates")
            await cursor.execute("DELETE FROM events")
            await self.connection.commit()
            logger.info("[灾害预警] 数据库所有事件记录已清除")
            return True
        except Exception as e:
            logger.error(f"[灾害预警] 清除失败: {e}")
            await self.connection.rollback()
            return False

    # ──────────────────────────── 生命周期 ────────────────────────────

    async def close(self):
        """关闭数据库连接"""
        if self.connection:
            await self.connection.close()
            self.connection = None
            logger.info("[灾害预警] 数据库连接已关闭")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()
