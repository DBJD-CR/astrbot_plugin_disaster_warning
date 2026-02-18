"""
灾害预警插件 - 数据库管理模块
使用 SQLite 存储历史事件数据（异步版本，使用 aiosqlite）
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiosqlite
from astrbot.api import logger


class DatabaseManager:
    """数据库管理器 - 负责历史事件数据的持久化存储（异步版本）"""

    def __init__(self, db_path: Path):
        """
        初始化数据库管理器

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.connection: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        """异步初始化数据库，创建必要的表结构"""
        try:
            # 确保数据目录存在
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # 连接数据库
            self.connection = await aiosqlite.connect(str(self.db_path))
            self.connection.row_factory = aiosqlite.Row  # 返回字典形式的结果

            cursor = await self.connection.cursor()

            # 创建事件表
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    real_event_id TEXT,
                    unique_id TEXT,
                    type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    description TEXT,
                    latitude REAL,
                    longitude REAL,
                    magnitude REAL,
                    depth REAL,
                    report_num INTEGER,
                    time TEXT,
                    timestamp TEXT NOT NULL,
                    update_count INTEGER DEFAULT 1,
                    weather_type_code TEXT,
                    level TEXT,
                    raw_data TEXT,
                    history TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 创建索引以提高查询性能
            await cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_event_id ON events(event_id)
            """
            )
            await cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_real_event_id ON events(real_event_id)
            """
            )
            await cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_unique_id ON events(unique_id)
            """
            )
            await cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_source ON events(source)
            """
            )
            await cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_type ON events(type)
            """
            )
            await cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)
            """
            )

            await self.connection.commit()
            logger.info(f"[灾害预警] 数据库初始化完成: {self.db_path}")

        except Exception as e:
            logger.error(f"[灾害预警] 数据库初始化失败: {e}")
            raise

    async def insert_event(self, event_data: dict[str, Any]) -> int:
        """
        插入新事件记录

        Args:
            event_data: 事件数据字典

        Returns:
            插入记录的 ID
        """
        try:
            cursor = await self.connection.cursor()

            # 将字典和列表字段序列化为 JSON
            raw_data = json.dumps(event_data.get("raw_data", {}), ensure_ascii=False)
            history = json.dumps(event_data.get("history", []), ensure_ascii=False)
            
            # 确保 timestamp 总是有值，避免 NOT NULL 约束失败
            timestamp = event_data.get("timestamp") or datetime.now().isoformat()

            await cursor.execute(
                """
                INSERT INTO events (
                    event_id, real_event_id, unique_id, type, source, 
                    description, latitude, longitude, magnitude, depth,
                    report_num, time, timestamp, update_count,
                    weather_type_code, level, raw_data, history
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    event_data.get("event_id"),
                    event_data.get("real_event_id"),
                    event_data.get("unique_id"),
                    event_data.get("type"),
                    event_data.get("source"),
                    event_data.get("description"),
                    event_data.get("latitude"),
                    event_data.get("longitude"),
                    event_data.get("magnitude"),
                    event_data.get("depth"),
                    event_data.get("report_num"),
                    event_data.get("time"),
                    timestamp,
                    event_data.get("update_count", 1),
                    event_data.get("weather_type_code"),
                    event_data.get("level"),
                    raw_data,
                    history,
                ),
            )

            await self.connection.commit()
            return cursor.lastrowid

        except Exception as e:
            logger.error(f"[灾害预警] 插入事件记录失败: {e}")
            await self.connection.rollback()
            raise

    async def update_event(
        self, event_id: str, source: str, event_data: dict[str, Any]
    ) -> bool:
        """
        更新已存在的事件记录

        Args:
            event_id: 事件ID
            source: 数据源
            event_data: 更新的事件数据

        Returns:
            是否更新成功
        """
        try:
            cursor = await self.connection.cursor()

            # 将字典和列表字段序列化为 JSON
            raw_data = json.dumps(event_data.get("raw_data", {}), ensure_ascii=False)
            history = json.dumps(event_data.get("history", []), ensure_ascii=False)
            
            # 确保 timestamp 总是有值，避免 NOT NULL 约束失败
            timestamp = event_data.get("timestamp") or datetime.now().isoformat()

            await cursor.execute(
                """
                UPDATE events SET
                    real_event_id = ?,
                    unique_id = ?,
                    description = ?,
                    latitude = ?,
                    longitude = ?,
                    magnitude = ?,
                    depth = ?,
                    report_num = ?,
                    time = ?,
                    timestamp = ?,
                    update_count = ?,
                    weather_type_code = ?,
                    level = ?,
                    raw_data = ?,
                    history = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE event_id = ? AND source = ?
            """,
                (
                    event_data.get("real_event_id"),
                    event_data.get("unique_id"),
                    event_data.get("description"),
                    event_data.get("latitude"),
                    event_data.get("longitude"),
                    event_data.get("magnitude"),
                    event_data.get("depth"),
                    event_data.get("report_num"),
                    event_data.get("time"),
                    timestamp,
                    event_data.get("update_count", 1),
                    event_data.get("weather_type_code"),
                    event_data.get("level"),
                    raw_data,
                    history,
                    event_id,
                    source,
                ),
            )

            await self.connection.commit()
            return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"[灾害预警] 更新事件记录失败: {e}")
            await self.connection.rollback()
            raise

    async def get_recent_events(self, limit: int = 250) -> list[dict[str, Any]]:
        """
        获取最近的事件记录

        Args:
            limit: 返回记录数量限制

        Returns:
            事件记录列表
        """
        try:
            cursor = await self.connection.cursor()
            await cursor.execute(
                """
                SELECT * FROM events
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (limit,),
            )

            events = []
            rows = await cursor.fetchall()
            for row in rows:
                event = dict(row)
                # 反序列化 JSON 字段
                if event.get("raw_data"):
                    try:
                        event["raw_data"] = json.loads(event["raw_data"])
                    except (json.JSONDecodeError, TypeError, ValueError):
                        event["raw_data"] = {}
                if event.get("history"):
                    try:
                        event["history"] = json.loads(event["history"])
                    except (json.JSONDecodeError, TypeError, ValueError):
                        event["history"] = []
                events.append(event)

            return events

        except Exception as e:
            logger.error(f"[灾害预警] 查询最近事件失败: {e}")
            return []

    async def find_event_by_id(
        self, event_id: str, source: str
    ) -> Optional[dict[str, Any]]:
        """
        根据事件ID和数据源查找事件

        Args:
            event_id: 事件ID
            source: 数据源

        Returns:
            事件记录，如果不存在返回 None
        """
        try:
            cursor = await self.connection.cursor()
            await cursor.execute(
                """
                SELECT * FROM events
                WHERE event_id = ? AND source = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """,
                (event_id, source),
            )

            row = await cursor.fetchone()
            if row:
                event = dict(row)
                # 反序列化 JSON 字段
                if event.get("raw_data"):
                    try:
                        event["raw_data"] = json.loads(event["raw_data"])
                    except (json.JSONDecodeError, TypeError, ValueError):
                        event["raw_data"] = {}
                if event.get("history"):
                    try:
                        event["history"] = json.loads(event["history"])
                    except (json.JSONDecodeError, TypeError, ValueError):
                        event["history"] = []
                return event

            return None

        except Exception as e:
            logger.error(f"[灾害预警] 查找事件失败: {e}")
            return None

    async def find_event_by_real_id(
        self, real_event_id: str, source: str
    ) -> Optional[dict[str, Any]]:
        """
        根据真实事件ID和数据源查找事件

        Args:
            real_event_id: 真实事件ID
            source: 数据源

        Returns:
            事件记录，如果不存在返回 None
        """
        try:
            cursor = await self.connection.cursor()
            await cursor.execute(
                """
                SELECT * FROM events
                WHERE real_event_id = ? AND source = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """,
                (real_event_id, source),
            )

            row = await cursor.fetchone()
            if row:
                event = dict(row)
                # 反序列化 JSON 字段
                if event.get("raw_data"):
                    try:
                        event["raw_data"] = json.loads(event["raw_data"])
                    except (json.JSONDecodeError, TypeError, ValueError):
                        event["raw_data"] = {}
                if event.get("history"):
                    try:
                        event["history"] = json.loads(event["history"])
                    except (json.JSONDecodeError, TypeError, ValueError):
                        event["history"] = []
                return event

            return None

        except Exception as e:
            logger.error(f"[灾害预警] 根据真实ID查找事件失败: {e}")
            return None

    async def get_statistics(self) -> dict[str, Any]:
        """
        获取数据库统计信息

        Returns:
            统计信息字典
        """
        try:
            cursor = await self.connection.cursor()

            # 总事件数
            await cursor.execute("SELECT COUNT(*) as total FROM events")
            total_row = await cursor.fetchone()
            total = total_row["total"]

            # 按类型统计
            await cursor.execute(
                """
                SELECT type, COUNT(*) as count
                FROM events
                GROUP BY type
            """
            )
            by_type_rows = await cursor.fetchall()
            by_type = {row["type"]: row["count"] for row in by_type_rows}

            # 按数据源统计
            await cursor.execute(
                """
                SELECT source, COUNT(*) as count
                FROM events
                GROUP BY source
            """
            )
            by_source_rows = await cursor.fetchall()
            by_source = {row["source"]: row["count"] for row in by_source_rows}

            # 数据库文件大小
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
