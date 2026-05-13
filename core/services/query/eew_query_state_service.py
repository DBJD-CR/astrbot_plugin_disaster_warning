"""
EEW 查询状态服务。
负责机构归一化、状态更新与查询视图构建，供灾害服务层委托调用。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ...domain.event_models import EarthquakeEvent, EventEnvelope
from ..identity.event_identity import (
    ensure_utc_datetime,
    resolve_event_publish_time_utc,
    resolve_report_num,
)


def build_institutions_from_catalog(
    institutions: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """规范化机构视图，确保统一目录中的结构可直接消费。"""
    result: dict[str, dict[str, Any]] = {}
    for institution_key, meta in (institutions or {}).items():
        if not isinstance(meta, dict):
            continue
        source_ids = [
            str(source_id).strip()
            for source_id in list(meta.get("source_ids") or [])
            if str(source_id).strip()
        ]
        if not source_ids:
            continue
        result[institution_key] = {
            "display_name": str(meta.get("display_name") or institution_key).strip(),
            "active_name": str(
                meta.get("active_name") or meta.get("display_name") or institution_key
            ).strip(),
            "source_ids": source_ids,
        }
    return result


class EEWQueryStateService:
    """EEW 查询状态服务。

    负责维护机构维度的最新预警状态，并构建供查询接口复用的结构化结果。
    """

    def __init__(
        self,
        *,
        institutions: dict[str, dict[str, Any]],
        valid_duration_seconds: int,
        source_enabled_checker,
    ):
        self.institutions = build_institutions_from_catalog(institutions)
        self.valid_duration_seconds = valid_duration_seconds
        self._source_enabled_checker = source_enabled_checker

    def normalize_institution(self, source_id: str) -> str | None:
        """将数据源标识归一化到机构维度。"""
        for institution_key, meta in self.institutions.items():
            if source_id in meta.get("source_ids", []):
                return institution_key
        return None

    def build_fingerprint(
        self,
        envelope: EventEnvelope,
        data: EarthquakeEvent,
        source_id: str,
        event_key: str,
    ) -> str:
        """构建机构内去重指纹。

        指纹需要尽量稳定地描述“同一机构下同一条预警更新链”。
        早期实现把震级也纳入指纹，但 EEW 后续报经常会修正震级，
        这会导致同一事件的第 N 报被误判成另一条链，进而无法稳定覆盖首报。

        因此这里仅使用更稳定的事件键、地点与发震时间分钟桶；
        其中分钟桶用于兼容少数来源缺少稳定 event_id 的情况。
        """
        del source_id
        place = (data.place_name or "未知地点").strip()
        shock_time = resolve_event_publish_time_utc(envelope)
        minute_bucket = shock_time.strftime("%Y%m%d%H%M")
        return f"{event_key}|{place}|{minute_bucket}"

    def should_replace(
        self, current: dict[str, Any], candidate: dict[str, Any]
    ) -> bool:
        """判断候选状态是否应覆盖当前状态。

        优先比较报次，报次一致时再比较发布时间的新旧。
        """
        current_fp = current.get("fingerprint", "")
        candidate_fp = candidate.get("fingerprint", "")

        if current_fp and candidate_fp and current_fp == candidate_fp:
            current_updates = int(current.get("updates", 1) or 1)
            candidate_updates = int(candidate.get("updates", 1) or 1)
            if candidate_updates > current_updates:
                return True
            if candidate_updates < current_updates:
                return False

        current_source_id = str(current.get("source_id") or "").strip()
        candidate_source_id = str(candidate.get("source_id") or "").strip()
        current_issued = ensure_utc_datetime(
            current.get("issued_at"), source_id=current_source_id
        )
        candidate_issued = ensure_utc_datetime(
            candidate.get("issued_at"), source_id=candidate_source_id
        )
        if current_issued is None:
            return True
        if candidate_issued is None:
            return False
        return candidate_issued >= current_issued

    def update_state(
        self,
        state: dict[str, dict[str, Any]],
        event: EventEnvelope,
    ) -> dict[str, dict[str, Any]]:
        """更新 EEW 查询状态。

        仅处理地震预警事件，并按机构维度保留当前最适合展示的一条状态。
        """
        envelope = event
        data = envelope.event
        if not isinstance(data, EarthquakeEvent):
            return state

        source_id = envelope.source_id
        institution_key = self.normalize_institution(source_id)
        if not institution_key:
            return state

        issued_at = resolve_event_publish_time_utc(envelope)
        expires_at = issued_at + timedelta(seconds=self.valid_duration_seconds)

        identity = envelope.identity
        event_key = str(identity.event_id or envelope.id or "").strip()
        place = (data.place_name or "未知地点").strip()
        magnitude = data.magnitude
        fingerprint = self.build_fingerprint(envelope, data, source_id, event_key)
        report_num = resolve_report_num(event) or 1

        candidate = {
            "source_id": source_id,
            "event_id": event_key,
            "display_place": place,
            "display_magnitude": magnitude,
            "updates": int(report_num),
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "fingerprint": fingerprint,
        }

        current = state.get(institution_key)
        if current and not self.should_replace(current, candidate):
            return state

        state[institution_key] = candidate
        return state

    def get_enabled_sources_by_institution(
        self, data_sources_cfg: dict[str, Any]
    ) -> dict[str, list[str]]:
        """返回每个机构当前启用的 source_id 列表。"""
        result: dict[str, list[str]] = {}
        for institution_key, meta in self.institutions.items():
            enabled_sources = [
                source_id
                for source_id in meta.get("source_ids", [])
                if self._source_enabled_checker(source_id, data_sources_cfg)
            ]
            result[institution_key] = enabled_sources
        return result

    @staticmethod
    def format_elapsed_seconds(total_seconds: int) -> str:
        """将秒数格式化为人类可读样式。"""
        total_seconds = max(0, int(total_seconds))
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)

        if days > 0:
            return f"{days}天{hours}时{minutes}分{seconds}秒"
        if hours > 0:
            return f"{hours}时{minutes}分{seconds}秒"
        if minutes > 0:
            return f"{minutes}分{seconds}秒"
        return f"{seconds}秒"

    def build_status_data(
        self,
        state: dict[str, dict[str, Any]],
        data_sources_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        """获取地震预警查询的结构化状态数据。

        返回结果可直接供命令查询与管理端接口复用。
        """
        now_utc = datetime.now(timezone.utc)
        enabled_sources_map = self.get_enabled_sources_by_institution(data_sources_cfg)

        institutions: list[dict[str, Any]] = []
        for institution_key, meta in self.institutions.items():
            enabled_sources = enabled_sources_map.get(institution_key, [])
            display_name = meta.get("display_name", institution_key)
            active_name = meta.get("active_name", display_name)

            item: dict[str, Any] = {
                "institution_key": institution_key,
                "display_name": display_name,
                "active_name": active_name,
                "enabled": bool(enabled_sources),
                "enabled_sources": enabled_sources,
                "status": "unavailable",
                "elapsed_seconds": None,
                "issued_at": None,
                "expires_at": None,
                "magnitude": None,
                "place": None,
            }

            if not enabled_sources:
                institutions.append(item)
                continue

            current = state.get(institution_key)
            if not isinstance(current, dict):
                item["status"] = "no_data"
                institutions.append(item)
                continue

            current_source_id = str(current.get("source_id") or "").strip()
            issued_at = ensure_utc_datetime(
                current.get("issued_at"), source_id=current_source_id
            )
            expires_at = ensure_utc_datetime(
                current.get("expires_at"), source_id=current_source_id
            )
            if issued_at is None:
                item["status"] = "no_data"
                institutions.append(item)
                continue

            if expires_at is None:
                expires_at = issued_at + timedelta(seconds=self.valid_duration_seconds)

            item["issued_at"] = issued_at.isoformat()
            item["expires_at"] = expires_at.isoformat()
            item["magnitude"] = current.get("display_magnitude")
            item["place"] = current.get("display_place") or "未知地点"

            elapsed = int((now_utc - issued_at).total_seconds())
            item["elapsed_seconds"] = max(0, elapsed)
            item["status"] = "active" if now_utc < expires_at else "inactive"
            institutions.append(item)

        return {
            "timestamp": now_utc.isoformat(),
            "valid_duration_seconds": self.valid_duration_seconds,
            "institutions": institutions,
        }
