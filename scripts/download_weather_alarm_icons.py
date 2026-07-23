"""批量镜像 FAN Studio 气象预警图标到本地 resources/weatheralarm_logo/。

优先从 events.db 提取真实 weather_type_code，再补充国标扫描。
支持断点续传、低并发、502 退避。
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "resources" / "weatheralarm_logo"
DB = Path(
    r"F:/tools/AstrBot/AstrBotLauncher-0.1.5.6/AstrBot/data/plugin_data/"
    r"astrbot_plugin_disaster_warning/events.db"
)
BASES = [
    "https://api.fanstudio.tech/we/img/alarm_icon.php?type=",
    "https://api.fanstudio.hk/we/img/alarm_icon.php?type=",
]
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AstrBotDisasterWarningIconMirror/1.0"
    )
}
COLORS = ["blue", "yellow", "orange", "red", "white"]
MIN_PNG_BYTES = 1500
MAX_RETRIES = 5
REQUEST_GAP = 0.35


def safe_name(type_code: str) -> str:
    return type_code.replace("/", "_").replace("\\", "_").replace(" ", "_").strip()


def load_db_codes() -> list[str]:
    if not DB.exists():
        print(f"db missing: {DB}")
        return []
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    codes: list[str] = []
    for table in ("events", "events_v1_backup"):
        try:
            rows = cur.execute(
                f"""
                SELECT DISTINCT weather_type_code
                FROM {table}
                WHERE weather_type_code IS NOT NULL
                  AND TRIM(weather_type_code) != ''
                """
            ).fetchall()
        except sqlite3.Error as exc:
            print(f"skip table {table}: {exc}")
            continue
        for (code,) in rows:
            text = str(code or "").strip()
            if text and text not in {"unknow_y", "unknow_o", "unknow_b", "unknow_r"}:
                # 跳过中文脏数据
                if any("\u4e00" <= ch <= "\u9fff" for ch in text):
                    continue
                codes.append(text)
    conn.close()
    return list(dict.fromkeys(codes))


def expand_from_db(codes: list[str]) -> list[str]:
    """基于库中编码扩展同类型其他颜色。"""
    expanded: list[str] = list(codes)
    for code in codes:
        if "_" in code:
            prefix, color = code.rsplit("_", 1)
            if color.lower() in COLORS:
                for col in COLORS:
                    expanded.append(f"{prefix}_{col}")
        elif code.startswith("p") and code[1:].isdigit() and len(code) >= 2:
            # 旧 p 格式末位颜色：1红2橙3黄4蓝
            body = code[:-1]
            for digit in "1234":
                expanded.append(body + digit)
        elif code.startswith("11") and len(code) >= 5 and code[-2:].isdigit():
            # 紧凑 11B2002
            body = code[:-2]
            for suf in ("01", "02", "03", "04"):
                expanded.append(body + suf)
    return list(dict.fromkeys(expanded))


def build_scan_codes() -> list[str]:
    """补充扫描常见 11B 类型。"""
    codes: list[str] = []
    for i in range(0, 50):
        base = f"11B{i:02d}"
        for col in COLORS:
            codes.append(f"{base}_{col}")
        for suf in ("01", "02", "03", "04"):
            codes.append(base + suf)
    # 库里出现过 11E06
    for i in range(0, 20):
        base = f"11E{i:02d}"
        for col in COLORS:
            codes.append(f"{base}_{col}")
    return codes


def fetch_one(type_code: str) -> tuple[str, bytes | None, str, int]:
    path = OUT / f"{safe_name(type_code)}.png"
    if path.exists() and path.stat().st_size >= MIN_PNG_BYTES:
        data = path.read_bytes()
        if data.startswith(b"\x89PNG"):
            return type_code, data, "cached", len(data)

    last_info = "unknown"
    for attempt in range(1, MAX_RETRIES + 1):
        for base in BASES:
            url = base + type_code
            req = urllib.request.Request(url, headers=UA)
            try:
                time.sleep(REQUEST_GAP)
                with urllib.request.urlopen(req, timeout=25) as response:
                    data = response.read()
                    if not data.startswith(b"\x89PNG"):
                        last_info = "not_png"
                        continue
                    if len(data) < MIN_PNG_BYTES:
                        last_info = "too_small"
                        continue
                    return type_code, data, "ok", len(data)
            except urllib.error.HTTPError as exc:
                last_info = f"HTTP{exc.code}"
                if exc.code in {400, 404}:
                    return type_code, None, last_info, 0
                # 502/503/429 换 host / 退避
                time.sleep(1.2 * attempt)
            except Exception as exc:  # noqa: BLE001
                last_info = type(exc).__name__
                time.sleep(1.0 * attempt)
    return type_code, None, last_info, 0


def wait_until_api_ready(timeout_seconds: int = 180) -> bool:
    probe = "11B01_blue"
    deadline = time.time() + timeout_seconds
    print("waiting for icon API recovery...")
    while time.time() < deadline:
        code, data, info, size = fetch_one(probe)
        if data is not None and info in {"ok", "cached"}:
            print(f"API ready via probe {probe} ({info}, {size} bytes)")
            return True
        print(f"  not ready: {info}, sleep 8s")
        time.sleep(8)
    print("API still unavailable after wait")
    return False


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    db_codes = load_db_codes()
    print(f"db codes: {len(db_codes)}")
    for code in db_codes:
        print(f"  {code}")

    candidates = expand_from_db(db_codes)
    # 库内优先，再补扫描
    for code in build_scan_codes():
        if code not in candidates:
            candidates.append(code)
    print(f"candidates after expand/scan: {len(candidates)}")

    if not wait_until_api_ready():
        print("abort: API not ready")
        return

    ok: list[tuple[str, int, str, str]] = []
    fail = 0
    cached = 0
    started = time.time()

    for index, code in enumerate(candidates, start=1):
        type_code, data, info, size = fetch_one(code)
        if data is None:
            fail += 1
        else:
            if info == "cached":
                cached += 1
            else:
                path = OUT / f"{safe_name(type_code)}.png"
                path.write_bytes(data)
            digest = hashlib.sha1(data).hexdigest()[:10]
            ok.append((type_code, size, digest, f"{safe_name(type_code)}.png"))
        if index % 20 == 0 or index == len(candidates):
            print(
                f"progress {index}/{len(candidates)} "
                f"ok={len(ok)} cached={cached} fail={fail} "
                f"elapsed={time.time() - started:.1f}s last={type_code}:{info}"
            )

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    manifest = OUT / "icons_manifest.txt"
    with manifest.open("w", encoding="utf-8") as handle:
        handle.write(f"# downloaded {len(ok)} icons at {stamp}\n")
        handle.write(f"# db_codes={len(db_codes)} candidates={len(candidates)}\n")
        for code, size, digest, name in sorted(ok):
            handle.write(f"{code}\t{size}\t{digest}\t{name}\n")

    print(
        f"DONE ok={len(ok)} cached={cached} fail={fail} "
        f"elapsed={time.time() - started:.1f}s"
    )
    print(f"manifest={manifest}")


if __name__ == "__main__":
    main()
