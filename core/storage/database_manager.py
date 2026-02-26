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
        """检测 schema 版本，必要时执行迁移"""
        await cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        events_exists = bool(await cursor.fetchone())

        if events_exists:
            # 旧 schema 特征：含 history 或 raw_data 列
            await cursor.execute("PRAGMA table_info(events)")
            columns = {row[1] for row in await cursor.fetchall()}
            if "history" in columns or "raw_data" in columns:
                logger.info("[灾害预警] 检测到旧版数据库 schema (v1)，开始迁移到 v2...")
                await self._migrate_v1_to_v2(cursor)
                return

            # 关键修复：在创建索引前先补齐缺失列，避免 idx_ev_source_id 创建失败
            if "source_id" not in columns:
                await cursor.execute("ALTER TABLE events ADD COLUMN source_id TEXT")

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

    async def _migrate_v1_to_v2(self, cursor):
        """将 v1 schema（含 history JSON blob）迁移到 v2（events + event_updates）
        使用游标分页，每批 BATCH_SIZE 条，避免一次性将全表载入内存。
        """
        BATCH_SIZE = 1000

        try:
            # 1. 备份旧表，创建新表（先做结构变更，再分批写数据）
            await cursor.execute("SELECT COUNT(*) FROM events")
            total = (await cursor.fetchone())[0]
            logger.info(
                f"[灾害预警] 开始迁移 {total} 条旧记录（每批 {BATCH_SIZE} 条）..."
            )

            await cursor.execute("DROP TABLE IF EXISTS events_v1_backup")
            await cursor.execute("ALTER TABLE events RENAME TO events_v1_backup")
            await cursor.execute("DROP TABLE IF EXISTS event_updates")
            await self._create_tables(cursor)
            await self.connection.commit()

            # 2. 分批迁移（以旧表 id 为游标）
            migrated = 0
            last_id = 0

            while True:
                await cursor.execute(
                    "SELECT * FROM events_v1_backup WHERE id > ? ORDER BY id ASC LIMIT ?",
                    (last_id, BATCH_SIZE),
                )
                batch = [dict(row) for row in await cursor.fetchall()]
                if not batch:
                    break

                for row in batch:
                    try:
                        history: list = []
                        if row.get("history"):
                            try:
                                parsed = json.loads(row["history"])
                                if isinstance(parsed, list):
                                    history = parsed
                            except (json.JSONDecodeError, TypeError):
                                pass

                        is_major = is_major_event(row)

                        await cursor.execute(
                            """
                            INSERT INTO events (
                                real_event_id, unique_id, type, source,
                                source_id, description, latitude, longitude,
                                magnitude, depth, report_num,
                                weather_type_code, level, time,
                                is_major, update_count, created_at, updated_at
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                row.get("real_event_id"),
                                row.get("unique_id"),
                                row.get("type", "unknown"),
                                row.get("source", "unknown"),
                                row.get("source_id"),
                                row.get("description"),
                                row.get("latitude"),
                                row.get("longitude"),
                                row.get("magnitude"),
                                row.get("depth"),
                                row.get("report_num"),
                                row.get("weather_type_code"),
                                row.get("level"),
                                row.get("time"),
                                1 if is_major else 0,
                                row.get("update_count", 1),
                                row.get("created_at", datetime.now().isoformat()),
                                row.get(
                                    "updated_at",
                                    row.get("timestamp", datetime.now().isoformat()),
                                ),
                            ),
                        )
                        new_event_db_id = cursor.lastrowid

                        # 历史报（从旧到新）插入 event_updates
                        for hist in reversed(history):
                            await cursor.execute(
                                """
                                INSERT INTO event_updates
                                    (event_id, source_event_id, report_num, magnitude, depth, description, time)
                                VALUES (?,?,?,?,?,?,?)
                                """,
                                (
                                    new_event_db_id,
                                    hist.get("event_id"),
                                    hist.get("report_num"),
                                    hist.get("magnitude"),
                                    hist.get("depth"),
                                    hist.get("description"),
                                    hist.get("time"),
                                ),
                            )

                        # 当前状态作为最新一条 event_update
                        await cursor.execute(
                            """
                            INSERT INTO event_updates
                                (event_id, source_event_id, report_num, magnitude, depth, description, time)
                            VALUES (?,?,?,?,?,?,?)
                            """,
                            (
                                new_event_db_id,
                                row.get("event_id"),
                                row.get("report_num"),
                                row.get("magnitude"),
                                row.get("depth"),
                                row.get("description"),
                                row.get("time"),
                            ),
                        )
                        migrated += 1
                    except Exception as e:
                        logger.warning(
                            f"[灾害预警] 迁移单条记录失败 (id={row.get('id')}): {e}"
                        )

                # 每批提交一次，降低峰值内存并支持失败重试
                await self.connection.commit()
                last_id = batch[-1]["id"]
                logger.info(
                    f"[灾害预警] 迁移进度：{migrated}/{total}（id > {last_id}）"
                )

            logger.info(
                f"[灾害预警] 数据库迁移完成：成功迁移 {migrated}/{total} 条记录"
            )
            # events_v1_backup 保留作为安全备份，不立即删除

        except Exception as e:
            logger.error(f"[灾害预警] 数据库迁移失败: {e}")
            # 尝试回滚到旧表
            try:
                await cursor.execute("DROP TABLE IF EXISTS event_updates")
                await cursor.execute("DROP TABLE IF EXISTS events")
                await cursor.execute("ALTER TABLE events_v1_backup RENAME TO events")
                await self.connection.commit()
                logger.info("[灾害预警] 已回滚到旧数据库 schema")
            except Exception as re:
                logger.error(f"[灾害预警] 回滚失败: {re}")
            raise

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
                    description, latitude, longitude,
                    magnitude, depth, report_num,
                    weather_type_code, level, time,
                    is_major, update_count
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event_data.get("real_event_id"),
                    event_data.get("unique_id"),
                    event_data.get("type"),
                    event_data.get("source"),
                    event_data.get("source_id"),
                    event_data.get("description"),
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
                    latitude          = ?,
                    longitude         = ?,
                    magnitude         = ?,
                    depth             = ?,
                    report_num        = ?,
                    time              = ?,
                    update_count      = ?,
                    weather_type_code = ?,
                    level             = ?,
                    is_major          = CASE WHEN ? = 1 THEN 1 ELSE is_major END,
                    updated_at        = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    event_data.get("source_id"),
                    event_data.get("description"),
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
            # 去掉最后一条（当前状态已在 events 主表），其余倒序排列（最新在前）
            event["history"] = list(reversed(updates[:-1])) if len(updates) > 1 else []

        return events

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
    ) -> int:
        """获取事件总数（支持按类型、数据源过滤）"""
        try:
            cursor = await self.connection.cursor()
            clauses = []
            params: list[Any] = []

            if event_type:
                clauses.append("type=?")
                params.append(event_type)

            normalized_sources = [s for s in (sources or []) if s]
            if normalized_sources:
                placeholders = ",".join(["?"] * len(normalized_sources))
                clauses.append(f"source IN ({placeholders})")
                params.extend(normalized_sources)

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
    ) -> list[dict[str, Any]]:
        """分页获取事件（含 history，支持按类型与数据源过滤）"""
        try:
            offset = (page - 1) * limit
            cursor = await self.connection.cursor()

            clauses = []
            params: list[Any] = []

            if event_type:
                clauses.append("type=?")
                params.append(event_type)

            normalized_sources = [s for s in (sources or []) if s]
            if normalized_sources:
                placeholders = ",".join(["?"] * len(normalized_sources))
                clauses.append(f"source IN ({placeholders})")
                params.extend(normalized_sources)

            where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = (
                "SELECT * FROM events"
                f"{where_sql}"
                " ORDER BY updated_at DESC, time DESC LIMIT ? OFFSET ?"
            )
            params.extend([limit, offset])
            await cursor.execute(sql, tuple(params))

            events = [dict(row) for row in await cursor.fetchall()]
            return await self._attach_history(events)
        except Exception as e:
            logger.error(f"[灾害预警] 分页查询失败: {e}")
            return []

    async def get_event_sources(self, event_type: str | None = None) -> list[str]:
        """获取事件数据源列表（可按类型过滤）"""
        try:
            cursor = await self.connection.cursor()
            if event_type:
                await cursor.execute(
                    "SELECT DISTINCT source FROM events WHERE type=? ORDER BY source ASC",
                    (event_type,),
                )
            else:
                await cursor.execute(
                    "SELECT DISTINCT source FROM events ORDER BY source ASC"
                )
            rows = await cursor.fetchall()
            return [r[0] for r in rows if r and r[0]]
        except Exception as e:
            logger.error(f"[灾害预警] 查询数据源列表失败: {e}")
            return []

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
