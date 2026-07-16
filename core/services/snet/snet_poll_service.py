"""
NIED S-Net / MSIL 瓦片轮询服务。

独立于通用 WebSocket / Wolfx HTTP 列表轮询：
需要下载 PNG 瓦片、解码测站颜色并进入统一事件流水线。

内置短时快照缓存：同一分钟瓦片与解码后的测站列表可在轮询与 /snet 之间复用，
降低对 MSIL 上游的重复请求。
"""

from __future__ import annotations

import asyncio
import base64
import copy
import io
import json
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from PIL import Image

from astrbot.api import logger

from ...parsers.snet_parser import MSIL_TILE_BASE, SNET_REAL_COORDS, _build_stations
from ..query.source_runtime_query_service import SourceRuntimeQueryService


class SnetPollService:
    """S-Net MSIL 瓦片轮询服务。"""

    SOURCE_ID = "snet_msil"
    DEFAULT_INTERVAL_SECONDS = 60
    TILE_NAMES = (("y11", "11"), ("y12", "12"))
    # 瓦片快照最短/最长 TTL（秒）；实际 TTL 会结合 poll_interval 收敛
    MIN_TILE_CACHE_TTL = 30.0
    MAX_TILE_CACHE_TTL = 600.0

    def __init__(self, service):
        self.service = service
        self._source_runtime_query = SourceRuntimeQueryService(service.config)
        self._task: asyncio.Task | None = None
        self._last_event_id: str | None = None
        self._last_payload_fingerprint: str | None = None
        # 最近一次成功抓取的快照：{timestamp, tiles, stations|None, fetched_at}
        self._latest_snapshot: dict[str, Any] | None = None
        self._fetch_lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def is_enabled(self) -> bool:
        return self._source_runtime_query.is_source_enabled(self.SOURCE_ID)

    def _resolve_interval(self) -> int:
        data_sources = self.service.config.get("data_sources", {})
        group = data_sources.get("snet", {}) if isinstance(data_sources, dict) else {}
        if not isinstance(group, dict):
            return self.DEFAULT_INTERVAL_SECONDS
        try:
            interval = int(
                group.get("poll_interval_seconds", self.DEFAULT_INTERVAL_SECONDS)
            )
        except (TypeError, ValueError):
            interval = self.DEFAULT_INTERVAL_SECONDS
        return max(30, min(interval, 600))

    def _resolve_tile_cache_ttl(self) -> float:
        """瓦片快照 TTL：略短于轮询间隔，避免过期数据拖太久。"""
        interval = float(self._resolve_interval())
        return max(
            self.MIN_TILE_CACHE_TTL,
            min(interval * 0.9, self.MAX_TILE_CACHE_TTL),
        )

    def _resolve_min_shindo(self) -> float:
        filters = self.service.config.get("earthquake_filters", {})
        snet_filter = (
            filters.get("snet_filter", {}) if isinstance(filters, dict) else {}
        )
        # 默认 0.5：日本震度 1 的計測震度起点
        if not isinstance(snet_filter, dict) or not snet_filter.get("enabled", True):
            return 0.5
        try:
            value = float(snet_filter.get("min_shindo", 0.5))
        except (TypeError, ValueError):
            value = 0.5
        # 允许负震度阈值（MSIL 低端色阶可到负值），但钳制在配置合法范围
        if value < -3.0:
            value = -3.0
        if value > 7.0:
            value = 7.0
        return value

    async def start(self) -> None:
        """启动后台轮询任务。"""
        if self.running:
            return
        if not self.is_enabled():
            logger.info("[灾害预警] S-Net 数据源未启用，跳过轮询启动")
            return
        self._task = asyncio.create_task(self._poll_loop(), name="dw_snet_poll")
        self.service.scheduled_tasks.append(self._task)
        logger.info("[灾害预警] S-Net 轮询任务已启动")

    async def stop(self) -> None:
        """停止后台轮询任务。"""
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _poll_loop(self) -> None:
        """后台轮询循环。"""
        # 启动后先立即抓一次（若仍处于静默期，流水线会自行吞掉推送）
        try:
            await self.fetch_once(emit_event=True)
        except Exception as exc:
            logger.error(f"[灾害预警] S-Net 首次抓取失败: {exc}")

        while getattr(self.service, "running", False):
            try:
                interval = self._resolve_interval()
                await asyncio.sleep(interval)
                if not getattr(self.service, "running", False):
                    break
                if not self.is_enabled():
                    logger.debug("[灾害预警] S-Net 已禁用，跳过本轮轮询")
                    continue
                await self.fetch_once(emit_event=True)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"[灾害预警] S-Net 轮询异常: {exc}")

    async def fetch_once(
        self,
        *,
        emit_event: bool = True,
        min_shindo: float | None = None,
        parse_stations: bool = False,
    ) -> dict[str, Any] | None:
        """抓取并（可选）推送一轮 S-Net 数据。

        Returns:
            成功时返回 {
              "timestamp", "tiles", "min_shindo",
              "stations"(可选), "triggered"(可选)
            }；失败返回 None。
        """
        tiles_payload = await self._download_latest_tiles()
        if not tiles_payload:
            return None

        threshold = (
            self._resolve_min_shindo() if min_shindo is None else float(min_shindo)
        )
        if threshold < -3.0:
            threshold = -3.0
        if threshold > 7.0:
            threshold = 7.0

        raw_dict: dict[str, Any] = {
            "tiles": tiles_payload["tiles"],
            "timestamp": tiles_payload["timestamp"],
            "min_shindo": threshold,
        }

        stations: list[dict[str, Any]] | None = None
        if parse_stations or emit_event:
            stations = self._get_or_decode_stations(tiles_payload)
            if stations is not None:
                raw_dict["stations"] = stations
                raw_dict["triggered"] = [
                    s for s in stations if float(s.get("shindo", -999.0)) >= threshold
                ]

        if emit_event:
            await self._emit_event(raw_dict)

        return raw_dict

    async def fetch_for_query(
        self,
        *,
        min_shindo: float = 0.0,
        debug_mode: str | None = None,
    ) -> dict[str, Any] | None:
        """供 /snet 命令使用的即时抓取。

        debug_mode:
          - None: 正常下载（优先复用轮询快照缓存）
          - "random": 随机震度
          - "7"/"6+"/"6-"/...: 全站统一震度
        """
        if debug_mode:
            stations = self._build_debug_stations(debug_mode)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M00")
            triggered = [
                s for s in stations if float(s.get("shindo", -999.0)) >= min_shindo
            ]
            return {
                "timestamp": timestamp,
                "tiles": {},
                "min_shindo": min_shindo,
                "stations": stations,
                "triggered": triggered,
                "debug_mode": debug_mode,
            }

        return await self.fetch_once(
            emit_event=False,
            min_shindo=min_shindo,
            parse_stations=True,
        )

    def _candidate_timestamps(self) -> list[str]:
        """最近 3 个整分钟时间戳（UTC），与下载回退策略一致。"""
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        return [
            (now - timedelta(minutes=offset)).strftime("%Y%m%d%H%M00")
            for offset in range(3)
        ]

    def _snapshot_if_fresh(self) -> dict[str, Any] | None:
        """若内存快照仍在 TTL 内且属于最近 3 分钟之一，返回只读副本。"""
        snap = self._latest_snapshot
        if not snap:
            return None
        age = time.time() - float(snap.get("fetched_at") or 0.0)
        if age > self._resolve_tile_cache_ttl():
            return None
        ts = str(snap.get("timestamp") or "")
        if ts not in self._candidate_timestamps():
            return None
        tiles = snap.get("tiles")
        if not isinstance(tiles, dict) or len(tiles) < 2:
            return None
        return {
            "timestamp": ts,
            "tiles": tiles,
            "stations": snap.get("stations"),
            "from_cache": True,
        }

    def _store_snapshot(
        self,
        *,
        timestamp: str,
        tiles: dict[str, str],
        stations: list[dict[str, Any]] | None = None,
    ) -> None:
        """写入/刷新最近快照。"""
        prev = self._latest_snapshot
        # 同 timestamp 保留已解码测站，避免重复 PNG 解码
        if (
            stations is None
            and prev
            and prev.get("timestamp") == timestamp
            and isinstance(prev.get("stations"), list)
        ):
            stations = prev.get("stations")
        self._latest_snapshot = {
            "timestamp": timestamp,
            "tiles": tiles,
            "stations": stations,
            "fetched_at": time.time(),
        }

    async def _download_latest_tiles(self) -> dict[str, Any] | None:
        """下载最近可用的 MSIL 瓦片（带短时快照缓存）。"""
        async with self._fetch_lock:
            cached = self._snapshot_if_fresh()
            if cached is not None:
                logger.debug(f"[灾害预警] S-Net 瓦片缓存命中 ts={cached['timestamp']}")
                return {
                    "timestamp": cached["timestamp"],
                    "tiles": cached["tiles"],
                }

            now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            timeout = aiohttp.ClientTimeout(total=12)

            # MSIL 为公网 HTTPS，保持默认证书校验，避免中间人风险。
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for offset_min in range(3):
                    try_ts = now - timedelta(minutes=offset_min)
                    ts = try_ts.strftime("%Y%m%d%H%M00")
                    tiles: dict[str, str] = {}
                    for tile_name, tile_y in self.TILE_NAMES:
                        url = f"{MSIL_TILE_BASE}/{ts}/{ts}/5/28/{tile_y}.png"
                        try:
                            async with session.get(url) as resp:
                                if resp.status != 200:
                                    continue
                                content = await resp.read()
                                if not content:
                                    continue
                                tiles[tile_name] = base64.b64encode(content).decode(
                                    "ascii"
                                )
                        except Exception as exc:
                            logger.debug(f"[灾害预警] S-Net 瓦片请求失败 {url}: {exc}")
                    if len(tiles) >= 2:
                        self._store_snapshot(timestamp=ts, tiles=tiles)
                        logger.debug(f"[灾害预警] S-Net 瓦片已下载并缓存 ts={ts}")
                        return {"timestamp": ts, "tiles": tiles}

            logger.warning("[灾害预警] S-Net 最近 3 分钟均未拿到完整瓦片")
            return None

    def _get_or_decode_stations(
        self, tiles_payload: dict[str, Any]
    ) -> list[dict[str, Any]] | None:
        """解码测站列表；同 timestamp 复用快照中的解码结果。"""
        ts = str(tiles_payload.get("timestamp") or "")
        tiles = tiles_payload.get("tiles")
        if not isinstance(tiles, dict):
            return None

        snap = self._latest_snapshot
        if (
            snap
            and snap.get("timestamp") == ts
            and isinstance(snap.get("stations"), list)
        ):
            logger.debug(f"[灾害预警] S-Net 测站解码缓存命中 ts={ts}")
            return copy.deepcopy(snap["stations"])

        stations = self._decode_stations(tiles)
        if stations is not None:
            self._store_snapshot(timestamp=ts, tiles=tiles, stations=stations)
            return copy.deepcopy(stations)
        return None

    @staticmethod
    def _decode_stations(tiles_b64: dict[str, str]) -> list[dict[str, Any]] | None:
        """把 base64 PNG 解码为测站列表。"""
        decoded = {}
        for tn in ("y11", "y12"):
            b64 = tiles_b64.get(tn)
            if not b64:
                continue
            try:
                png = base64.b64decode(b64)
                decoded[tn] = Image.open(io.BytesIO(png)).convert("RGB")
            except Exception as exc:
                logger.warning(f"[灾害预警] S-Net 瓦片解码失败 {tn}: {exc}")
        if not decoded:
            return None

        stations = _build_stations(decoded)
        normalized: list[dict[str, Any]] = []
        for item in stations:
            rgb = item.get("rgb")
            if isinstance(rgb, tuple):
                rgb = list(rgb)
            normalized.append(
                {
                    "name": str(item.get("name") or ""),
                    "lat": float(item.get("lat") or 0.0),
                    "lon": float(item.get("lon") or 0.0),
                    "shindo": float(item.get("shindo") or 0.0),
                    "rgb": rgb if isinstance(rgb, list) else None,
                    "tile": str(item.get("tile") or ""),
                    "px": int(item.get("px") or 0),
                    "py": int(item.get("py") or 0),
                }
            )
        return normalized

    async def _emit_event(self, raw_dict: dict[str, Any]) -> None:
        """解析并送入统一事件流水线。"""
        # 指纹：同一分钟 + 触发测站集合 + 最大震度，避免无变化重复推送
        triggered = (
            raw_dict.get("triggered")
            if isinstance(raw_dict.get("triggered"), list)
            else []
        )
        if not triggered:
            # 解析器也会在无触发时返回 None；这里提前短路减少噪声
            logger.debug(
                f"[灾害预警] S-Net 本轮无测站达到阈值 min_shindo={raw_dict.get('min_shindo')}"
            )
            return

        top = max(triggered, key=lambda s: float(s.get("shindo", -999.0)))
        fingerprint = json.dumps(
            {
                "ts": raw_dict.get("timestamp"),
                "max": round(float(top.get("shindo", 0.0)), 3),
                "count": len(triggered),
                "names": sorted(str(s.get("name") or "") for s in triggered[:20]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if fingerprint == self._last_payload_fingerprint:
            logger.debug("[灾害预警] S-Net 载荷未变化，跳过推送")
            return

        message = json.dumps(raw_dict, ensure_ascii=False)
        event = self.service.parse_event(self.SOURCE_ID, message)
        if event is None:
            return

        event_id = getattr(event, "id", None)
        if (
            event_id
            and event_id == self._last_event_id
            and fingerprint == self._last_payload_fingerprint
        ):
            return

        self._last_payload_fingerprint = fingerprint
        self._last_event_id = event_id
        await self.service._handle_disaster_event(event)

    @staticmethod
    def _build_debug_stations(mode: str) -> list[dict[str, Any]]:
        """构建调试用伪测站数据。"""
        mode = (mode or "").strip().lower()
        label_map = {
            "7": 7.0,
            "6+": 6.2,
            "6-": 5.7,
            "5+": 5.2,
            "5-": 4.7,
            "4": 4.0,
            "3": 3.0,
            "2": 2.0,
            "1": 1.0,
            "0": 0.0,
        }

        stations: list[dict[str, Any]] = []
        for name, (lat, lon) in SNET_REAL_COORDS.items():
            if mode == "random":
                shindo = round(random.uniform(0.0, 7.0), 3)
            else:
                shindo = float(label_map.get(mode, 0.0))
            stations.append(
                {
                    "name": name,
                    "lat": float(lat),
                    "lon": float(lon),
                    "shindo": shindo,
                    "rgb": None,
                    "tile": "debug",
                    "px": 0,
                    "py": 0,
                }
            )
        return stations
