"""从 events.db 提取历史气象预警 weather_type_code。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(
    r"F:/tools/AstrBot/AstrBotLauncher-0.1.5.6/AstrBot/data/plugin_data/"
    r"astrbot_plugin_disaster_warning/events.db"
)


def main() -> None:
    print("exists", DB.exists(), "size", DB.stat().st_size if DB.exists() else 0)
    if not DB.exists():
        return

    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    tables = [
        row[0]
        for row in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    print("tables", tables)

    for table in tables:
        cols = [row[1] for row in cur.execute(f"PRAGMA table_info({table})")]
        if "weather_type_code" not in cols:
            continue
        print(
            f"\n== {table} columns with weather =",
            [
                c
                for c in cols
                if "weather" in c or c in {"type", "event_type", "source_id", "level"}
            ],
        )
        rows = cur.execute(
            f"""
            SELECT weather_type_code, COUNT(*) AS cnt
            FROM {table}
            WHERE weather_type_code IS NOT NULL AND TRIM(weather_type_code) != ''
            GROUP BY weather_type_code
            ORDER BY cnt DESC
            """
        ).fetchall()
        print(f"distinct codes: {len(rows)}")
        for code, cnt in rows[:80]:
            print(f"{cnt:6d}\t{code}")
        if len(rows) > 80:
            print(f"... and {len(rows) - 80} more")

        # also sample event_type/source for weather
        if "event_type" in cols:
            samples = cur.execute(
                f"""
                SELECT event_type, source_id, weather_type_code, level, COUNT(*)
                FROM {table}
                WHERE weather_type_code IS NOT NULL AND TRIM(weather_type_code) != ''
                GROUP BY event_type, source_id, weather_type_code, level
                ORDER BY COUNT(*) DESC
                LIMIT 30
                """
            ).fetchall()
            print("\nsamples:")
            for row in samples:
                print(row)

    conn.close()


if __name__ == "__main__":
    main()
