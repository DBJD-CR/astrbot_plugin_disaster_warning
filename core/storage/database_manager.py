"""
灾害预警插件 - 数据库管理模块
使用 SQLite 存储历史事件数据（异步版本，使用 aiosqlite）

Schema v2：
  events        - 每个物理事件一行（按 real_event_id+source 去重）
  event_updates - 每次推送/更新一行（原 history JSON 拆解）
"""

import json
from pathlib import Path
from typing import Any

import aiosqlite

from astrbot.api import logger

from ..services.identity.event_classifier import (
    MAJOR_EARTHQUAKE_MAGNITUDE_THRESHOLD,
    MAJOR_WEATHER_LEVEL_KEYWORD,
    MAJOR_WEATHER_TEXT_PHRASES,
    is_major_record,
)
from .source_compat import (
    expand_source_aliases,
    format_source_name,
    normalize_source_name,
)


class DatabaseManager:
    """数据库管理器。

    负责事件历史的建库、迁移、写入、查询与统计，
    同时维护主事件表与事件更新表之间的配套关系。
    """

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
        """异步初始化数据库，检测并执行必要的结构迁移。"""
        try:
            # 先确保数据库目录存在，再建立连接并统一使用字典风格行对象。
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
        """检测并补齐数据表字段，再创建表和索引。"""
        # 检查 events 主表是否存在
        await cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        events_exists = bool(await cursor.fetchone())

        if events_exists:
            # 补齐早期 v2 版本可能缺失的列，避免由于 schema 差异造成运行故障
            await cursor.execute("PRAGMA table_info(events)")
            columns = {row[1] for row in await cursor.fetchall()}
            if "source_id" not in columns:
                await cursor.execute("ALTER TABLE events ADD COLUMN source_id TEXT")
            if "subtitle" not in columns:
                await cursor.execute("ALTER TABLE events ADD COLUMN subtitle TEXT")
            if "weather_detail" not in columns:
                await cursor.execute(
                    "ALTER TABLE events ADD COLUMN weather_detail TEXT"
                )
            if "info_type" not in columns:
                await cursor.execute("ALTER TABLE events ADD COLUMN info_type TEXT")
            if "place_name" not in columns:
                await cursor.execute("ALTER TABLE events ADD COLUMN place_name TEXT")

        # 检查 event_updates 报次更新表是否存在
        await cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='event_updates'"
        )
        updates_exists = bool(await cursor.fetchone())
        if updates_exists:
            await cursor.execute("PRAGMA table_info(event_updates)")
            updates_columns = {row[1] for row in await cursor.fetchall()}
            if "level" not in updates_columns:
                await cursor.execute("ALTER TABLE event_updates ADD COLUMN level TEXT")

        # 创建不存在的表
        await self._create_tables(cursor)

    async def _create_tables(self, cursor):
        """创建当前版本所需的表结构与索引。"""
        # 主事件表：保存每个物理事件的最新综合状态
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
                weather_detail  TEXT,
                info_type       TEXT,
                place_name      TEXT,
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
        # 事件更新表：保存每次历史报次的详细快照，用于重建更新轨迹
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
                level           TEXT,
                time            TEXT,
                recorded_at     TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # 索引集中覆盖事件标识、来源、类型、时间等高频检索维度，加速分页与汇总查询
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
            # 是否重大事件既允许外部直接传入，也允许在入库前重新按规则补判一次
            is_major = bool(event_data.get("is_major")) or is_major_record(event_data)

            # 向 events 表插入主记录
            await cursor.execute(
                """
                INSERT INTO events (
                    real_event_id, unique_id, type, source, source_id,
                    description, subtitle, weather_detail, info_type, place_name, latitude, longitude,
                    magnitude, depth, report_num,
                    weather_type_code, level, time,
                    is_major, update_count
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event_data.get("real_event_id"),
                    event_data.get("unique_id"),
                    event_data.get("type"),
                    event_data.get("source"),
                    event_data.get("source_id"),
                    event_data.get("description"),
                    event_data.get("subtitle"),
                    event_data.get("weather_detail"),
                    event_data.get("info_type"),
                    event_data.get("place_name"),
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

            # 首次写入主事件表后，同步写入一条更新记录，保证历史链条从首报开始完整
            await cursor.execute(
                """
                INSERT INTO event_updates
                    (event_id, source_event_id, report_num, magnitude, depth, description, level, time)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    new_id,
                    event_data.get("event_id"),
                    event_data.get("report_num"),
                    event_data.get("magnitude"),
                    event_data.get("depth"),
                    event_data.get("description"),
                    event_data.get("level"),
                    event_data.get("time"),
                ),
            )

            await self.connection.commit()

            # 清理缓存，保证接口能够立刻加载出最新写入的数据
            try:
                from ..network.admin.api.events_routes import invalidate_sources_cache

                invalidate_sources_cache()
            except Exception:
                pass

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
            is_major = bool(event_data.get("is_major")) or is_major_record(event_data)

            # 先在主事件表中找到对应物理记录，再决定是更新还是返回未命中。
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

            # 更新主表中的事件字段
            await cursor.execute(
                """
                UPDATE events SET
                    source_id         = ?,
                    description       = ?,
                    subtitle          = ?,
                    weather_detail    = ?,
                    info_type         = ?,
                    place_name        = ?,
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
                    event_data.get("weather_detail"),
                    event_data.get("info_type"),
                    event_data.get("place_name"),
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

            # 主事件表字段更新后，再追加一条报次快照记录，保留每次演进轨迹
            await cursor.execute(
                """
                INSERT INTO event_updates
                    (event_id, source_event_id, report_num, magnitude, depth, description, level, time)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    db_id,
                    event_data.get("event_id"),
                    event_data.get("report_num"),
                    event_data.get("magnitude"),
                    event_data.get("depth"),
                    event_data.get("description"),
                    event_data.get("level"),
                    event_data.get("time"),
                ),
            )

            await self.connection.commit()

            # 更新完毕后清理缓存
            try:
                from ..network.admin.api.events_routes import invalidate_sources_cache

                invalidate_sources_cache()
            except Exception:
                pass

            return True
        except Exception as e:
            logger.error(f"[灾害预警] 更新事件失败: {e}")
            await self.connection.rollback()
            raise

    # ──────────────────────────── 读操作 ────────────────────────────

    async def _attach_history(self, events: list[dict]) -> list[dict]:
        """为事件列表批量附加更新历史记录。"""
        if not events:
            return events

        # 仅对 update_count > 1 的事件查询历史更新记录，update_count <= 1 的事件 history 必然为空
        events_need_history = [e for e in events if e.get("update_count", 1) > 1]

        for event in events:
            event["history"] = []

        if not events_need_history:
            return events

        # 用 json_each(?) 传递编号列表，避免动态拼接 IN 子句带来的复杂性。
        ids = json.dumps([e["id"] for e in events_need_history])
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

        for event in events_need_history:
            updates = updates_by_event.get(event["id"], [])
            if len(updates) > 1:
                # 历史链条中去掉了当前最新报本身，只保存以前的变更快照
                event["history"] = list(reversed(updates[:-1]))

        return events

    def _append_source_filter_clause(
        self,
        sources: list[str] | None,
        clauses: list[str],
        params: list[Any],
    ) -> None:
        """追加数据源过滤子句：按原值、标准化值与展示名兼容匹配 source/source_id。"""
        normalized_sources = [
            str(s or "").strip() for s in (sources or []) if str(s or "").strip()
        ]
        if not normalized_sources:
            return

        expanded_sources = expand_source_aliases(normalized_sources)
        normalized_aliases = sorted(
            {
                normalize_source_name(item)
                for item in expanded_sources
                if str(item or "").strip()
            }
        )

        raw_placeholders = ",".join(["?"] * len(expanded_sources))
        normalized_placeholders = ",".join(["?"] * len(normalized_aliases))
        clauses.append(
            "("
            "COALESCE(NULLIF(source_id, ''), source) IN (" + raw_placeholders + ") "
            "OR source IN (" + raw_placeholders + ") "
            "OR lower(COALESCE(NULLIF(source_id, ''), source)) IN ("
            + normalized_placeholders
            + ") "
            "OR lower(source) IN (" + normalized_placeholders + ")"
            ")"
        )
        params.extend(expanded_sources)
        params.extend(expanded_sources)
        params.extend(normalized_aliases)
        params.extend(normalized_aliases)

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

    async def find_weather_event_by_alarm_id(
        self, alarm_id: str
    ) -> dict[str, Any] | None:
        """按气象预警 ID（unique_id/real_event_id）查找事件。"""
        try:
            cursor = await self.connection.cursor()
            await cursor.execute(
                """
                SELECT *
                FROM events
                WHERE type='weather_alarm'
                  AND (unique_id=? OR real_event_id=?)
                ORDER BY updated_at DESC, time DESC, id DESC
                LIMIT 1
                """,
                (alarm_id, alarm_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            events = await self._attach_history([dict(row)])
            return events[0]
        except Exception as e:
            logger.error(f"[灾害预警] 按预警ID查找气象事件失败: {e}")
            return None

    async def get_recent_weather_events(
        self, limit: int = 5000
    ) -> list[dict[str, Any]]:
        """获取最近气象预警事件（含 history），按更新时间倒序。"""
        try:
            cursor = await self.connection.cursor()
            await cursor.execute(
                """
                SELECT *
                FROM events
                WHERE type='weather_alarm'
                ORDER BY updated_at DESC, time DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            events = [dict(row) for row in await cursor.fetchall()]
            return await self._attach_history(events)
        except Exception as e:
            logger.error(f"[灾害预警] 查询最近气象事件失败: {e}")
            return []

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
                          type NOT IN ('earthquake', 'earthquake_warning', 'weather_alarm')
                          OR (
                              type IN ('earthquake', 'earthquake_warning')
                              AND magnitude IS NOT NULL
                              AND magnitude >= ?
                          )
                          OR (
                              type = 'weather_alarm'
                              AND (
                                  (
                                      COALESCE(TRIM(level), '') != ''
                                      AND level LIKE ?
                                  )
                                  OR (
                                      COALESCE(TRIM(level), '') = ''
                                      AND description LIKE ?
                                  )
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
                (
                    MAJOR_EARTHQUAKE_MAGNITUDE_THRESHOLD,
                    f"%{MAJOR_WEATHER_LEVEL_KEYWORD}%",
                    *(f"%{phrase}%" for phrase in MAJOR_WEATHER_TEXT_PHRASES),
                    limit,
                ),
            )
            events = [dict(row) for row in await cursor.fetchall()]
            return await self._attach_history(events)
        except Exception as e:
            logger.error(f"[灾害预警] 查询重大事件失败: {e}")
            return []

    def _append_level_filter_clause(
        self,
        level_filter: str | None,
        clauses: list[str],
        params: list[Any],
    ) -> None:
        """追加气象颜色或海啸级别筛选条件。"""
        normalized = str(level_filter or "").strip().lower()
        weather_color_map = {
            "weather_white": "白色",
            "weather_blue": "蓝色",
            "weather_yellow": "黄色",
            "weather_orange": "橙色",
            "weather_red": "红色",
        }
        if normalized in weather_color_map:
            color = weather_color_map[normalized]
            like = f"%{color}%"
            clauses.append(
                "(type='weather_alarm' AND ("
                "COALESCE(level, '') LIKE ? OR "
                "COALESCE(description, '') LIKE ? OR "
                "COALESCE(subtitle, '') LIKE ?"
                "))"
            )
            params.extend([like, like, like])
            return

        if normalized == "tsunami_info":
            clauses.append(
                "(type='tsunami' AND ("
                "COALESCE(level, '') LIKE ? OR "
                "COALESCE(level, '') LIKE ? OR "
                "COALESCE(description, '') LIKE ? OR "
                "COALESCE(subtitle, '') LIKE ? OR "
                "COALESCE(info_type, '') LIKE ?"
                "))"
            )
            params.extend(
                ["%信息%", "%Unknown%", "%津波予報%", "%津波予報%", "%津波予报%"]
            )
            return

        if normalized == "tsunami_warning":
            clauses.append(
                "(type='tsunami' AND ("
                "COALESCE(level, '') LIKE ? OR "
                "COALESCE(level, '') LIKE ? OR "
                "COALESCE(level, '') LIKE ? OR "
                "COALESCE(level, '') LIKE ? OR "
                "COALESCE(level, '') LIKE ? OR "
                "COALESCE(description, '') LIKE ? OR "
                "COALESCE(description, '') LIKE ? OR "
                "COALESCE(description, '') LIKE ? OR "
                "COALESCE(subtitle, '') LIKE ? OR "
                "COALESCE(subtitle, '') LIKE ? OR "
                "COALESCE(subtitle, '') LIKE ?"
                "))"
            )
            params.extend(
                [
                    "%Warning%",
                    "%Watch%",
                    "%警报%",
                    "%警報%",
                    "%预警%",
                    "%海啸预警%",
                    "%津波警報%",
                    "%大津波警報%",
                    "%海啸预警%",
                    "%津波警報%",
                    "%大津波警報%",
                ]
            )

    async def get_events_count(
        self,
        event_type: str | None = None,
        sources: list[str] | None = None,
        min_magnitude: float | None = None,
        keyword: str | None = None,
        level_filter: str | None = None,
    ) -> int:
        """获取事件总数（支持按类型、数据源、最小震级与关键词过滤）"""
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

            self._append_level_filter_clause(level_filter, clauses, params)

            normalized_keyword = str(keyword or "").strip()
            if normalized_keyword:
                keyword_like = f"%{normalized_keyword}%"
                clauses.append(
                    "("
                    "COALESCE(description, '') LIKE ? OR "
                    "COALESCE(subtitle, '') LIKE ? OR "
                    "COALESCE(place_name, '') LIKE ? OR "
                    "COALESCE(level, '') LIKE ? OR "
                    "COALESCE(info_type, '') LIKE ? OR "
                    "COALESCE(source, '') LIKE ? OR "
                    "COALESCE(source_id, '') LIKE ?"
                    ")"
                )
                params.extend([keyword_like] * 7)

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
        keyword: str | None = None,
        level_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """分页获取事件（含 history，支持按类型、数据源、最小震级、关键词过滤与震级排序）"""
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

            self._append_level_filter_clause(level_filter, clauses, params)

            normalized_keyword = str(keyword or "").strip()
            if normalized_keyword:
                keyword_like = f"%{normalized_keyword}%"
                clauses.append(
                    "("
                    "COALESCE(description, '') LIKE ? OR "
                    "COALESCE(subtitle, '') LIKE ? OR "
                    "COALESCE(place_name, '') LIKE ? OR "
                    "COALESCE(level, '') LIKE ? OR "
                    "COALESCE(info_type, '') LIKE ? OR "
                    "COALESCE(source, '') LIKE ? OR "
                    "COALESCE(source_id, '') LIKE ?"
                    ")"
                )
                params.extend([keyword_like] * 7)

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
        """获取事件数据源选项（value/label），按最终展示语义去重。"""
        try:
            cursor = await self.connection.cursor()
            if event_type:
                await cursor.execute(
                    """
                    SELECT
                        COALESCE(NULLIF(source_id, ''), '') AS source_id_value,
                        COALESCE(NULLIF(source, ''), '') AS source_label
                    FROM events
                    WHERE type=?
                    GROUP BY source_id_value, source_label
                    """,
                    (event_type,),
                )
            else:
                await cursor.execute(
                    """
                    SELECT
                        COALESCE(NULLIF(source_id, ''), '') AS source_id_value,
                        COALESCE(NULLIF(source, ''), '') AS source_label
                    FROM events
                    GROUP BY source_id_value, source_label
                    """
                )
            rows = await cursor.fetchall()

            result_map: dict[str, dict[str, str]] = {}
            for row in rows:
                source_id_value = str(row[0] or "").strip()
                source_label = str(row[1] or "").strip()
                raw_source = source_id_value or source_label
                if not raw_source:
                    continue

                normalized_source = normalize_source_name(raw_source)
                display_label = format_source_name(raw_source)
                current = result_map.get(display_label)
                candidate = {
                    "source_value": raw_source,
                    "source_label": display_label,
                    "normalized_source": normalized_source,
                }

                if current is None:
                    result_map[display_label] = candidate
                    continue

                current_value = str(current.get("source_value") or "")
                current_normalized = str(current.get("normalized_source") or "")
                prefers_source_id = bool(source_id_value)
                current_is_raw_label = (
                    current_value.casefold()
                    == str(source_label or "").strip().casefold()
                )
                normalized_changed = (
                    normalized_source and normalized_source != current_normalized
                )

                if prefers_source_id or current_is_raw_label or normalized_changed:
                    result_map[display_label] = candidate

            return [
                {
                    "source_value": str(item.get("source_value") or ""),
                    "source_label": str(item.get("source_label") or ""),
                }
                for item in sorted(
                    result_map.values(),
                    key=lambda item: str(item.get("source_label") or "").casefold(),
                )
            ]
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
        """获取数据库统计信息（按稳定事件集合去重，而非按物理行计数）。"""
        try:
            cursor = await self.connection.cursor()

            dedup_group_expr = "COALESCE(NULLIF(unique_id, ''), NULLIF(real_event_id, ''), CAST(id AS TEXT))"

            await cursor.execute(
                f"SELECT COUNT(DISTINCT {dedup_group_expr}) FROM events"
            )
            total = (await cursor.fetchone())[0]

            await cursor.execute(
                f"SELECT type, COUNT(DISTINCT {dedup_group_expr}) FROM events GROUP BY type"
            )
            by_type = {r[0]: r[1] for r in await cursor.fetchall()}

            await cursor.execute(
                f"""
                SELECT COALESCE(NULLIF(source_id, ''), source) AS source_key,
                       COUNT(DISTINCT {dedup_group_expr}) AS source_count
                FROM events
                GROUP BY source_key
                """
            )
            by_source: dict[str, int] = {}
            for row in await cursor.fetchall():
                normalized_source = normalize_source_name(str(row[0] or ""))
                by_source[normalized_source] = by_source.get(
                    normalized_source, 0
                ) + int(row[1] or 0)

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

    async def get_statistics_rebuild_events(self) -> list[dict[str, Any]]:
        """获取去重后的全量事件，用于从数据库重建内存派生统计。"""
        try:
            cursor = await self.connection.cursor()
            dedup_group_expr = "COALESCE(NULLIF(unique_id, ''), NULLIF(real_event_id, ''), CAST(id AS TEXT))"
            source_group_expr = "COALESCE(NULLIF(source_id, ''), source)"
            await cursor.execute(
                f"""
                WITH ranked AS (
                    SELECT
                        *,
                        ROW_NUMBER() OVER (
                            PARTITION BY type, {source_group_expr}, {dedup_group_expr}
                            ORDER BY
                                CASE WHEN NULLIF(updated_at, '') IS NULL THEN 1 ELSE 0 END ASC,
                                updated_at DESC,
                                time DESC,
                                id DESC
                        ) AS rn
                    FROM events
                )
                SELECT
                    id,
                    type,
                    source,
                    source_id,
                    description,
                    subtitle,
                    weather_detail,
                    info_type,
                    place_name,
                    magnitude,
                    depth,
                    level,
                    weather_type_code,
                    time,
                    unique_id,
                    real_event_id,
                    update_count
                FROM ranked
                WHERE rn = 1
                """
            )
            return [dict(row) for row in await cursor.fetchall()]
        except Exception as e:
            logger.error(f"[灾害预警] 获取统计重建事件失败: {e}")
            return []

    async def get_time_series_counts(self) -> dict[str, dict[str, int]]:
        """按数据库全量事件重建趋势图/热力图所需的小时桶与天桶。"""
        try:
            cursor = await self.connection.cursor()

            dedup_group_expr = "COALESCE(NULLIF(unique_id, ''), NULLIF(real_event_id, ''), CAST(id AS TEXT))"
            normalized_time_expr = "COALESCE(NULLIF(time, ''), NULLIF(updated_at, ''), NULLIF(created_at, ''))"

            await cursor.execute(
                f"""
                WITH ranked AS (
                    SELECT
                        {dedup_group_expr} AS dedup_key,
                        {normalized_time_expr} AS event_time,
                        ROW_NUMBER() OVER (
                            PARTITION BY {dedup_group_expr}
                            ORDER BY
                                CASE WHEN NULLIF(updated_at, '') IS NULL THEN 1 ELSE 0 END ASC,
                                updated_at DESC,
                                time DESC,
                                id DESC
                        ) AS rn
                    FROM events
                    WHERE {normalized_time_expr} IS NOT NULL
                )
                SELECT event_time
                FROM ranked
                WHERE rn = 1
                """
            )
            rows = await cursor.fetchall()

            hourly_counts: dict[str, int] = {}
            daily_counts: dict[str, int] = {}
            for row in rows:
                raw_time = row[0]
                if not raw_time:
                    continue
                try:
                    from datetime import datetime, timezone

                    normalized_time = str(raw_time).replace("Z", "+00:00")
                    event_time = datetime.fromisoformat(normalized_time)
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=timezone.utc)
                    event_time_utc = event_time.astimezone(timezone.utc)
                except Exception:
                    continue

                hour_key = event_time_utc.strftime("%Y-%m-%d %H:00")
                day_key = event_time_utc.strftime("%Y-%m-%d")
                hourly_counts[hour_key] = hourly_counts.get(hour_key, 0) + 1
                daily_counts[day_key] = daily_counts.get(day_key, 0) + 1

            return {
                "hourly_counts": hourly_counts,
                "daily_counts": daily_counts,
            }
        except Exception as e:
            logger.error(f"[灾害预警] 获取时间序列统计失败: {e}")
            return {
                "hourly_counts": {},
                "daily_counts": {},
            }

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
