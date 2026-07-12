"""Pure parsing and state primitives for China Weather reconciliation."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import PurePosixPath
import re
from time import monotonic
from typing import Any
from urllib.parse import unquote, urlsplit


_INDEX_PREFIX = "var alarminfo="
_DETAIL_FILE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_WARNING_IDENTIFIER_PATTERN = re.compile(r"^(?P<prefix>\d{14})_(?P<issued_at>\d{14})$")
_WARNING_LEVEL_COLORS = {
    "01": "blue",
    "02": "yellow",
    "03": "orange",
    "04": "red",
    "05": "white",
}


@dataclass(frozen=True)
class WeatherFallbackConfig:
    """Validated runtime settings for optional China Weather reconciliation."""

    enabled: bool = False
    poll_interval_seconds: int = 180
    request_timeout_seconds: int = 15
    detail_concurrency: int = 4


@dataclass(frozen=True)
class WarningReference:
    """Stable identity and lookup fields from a China Weather index row."""

    identifier: str
    detail_path: str
    longitude: str
    latitude: str
    title: str


@dataclass(frozen=True)
class ReconciliationCycleResult:
    """Sanitized outcome counters for one reconciliation cycle."""

    index_valid: bool
    reference_count: int = 0
    new_count: int = 0
    consumed_count: int = 0
    failed_identifiers: tuple[str, ...] = ()
    consumed_error_identifiers: tuple[str, ...] = ()

    @property
    def dispatched_count(self) -> int:
        """Compatibility alias for callers written before consumption was explicit."""
        return self.consumed_count


def resolve_fallback_config(config: object) -> WeatherFallbackConfig:
    """Read and clamp the optional top-level reconciliation configuration."""
    root = config if isinstance(config, dict) else {}
    raw = root.get("weather_alarm_fallback", {})
    values = raw if isinstance(raw, dict) else {}
    return WeatherFallbackConfig(
        enabled=values.get("enabled", False) is True,
        poll_interval_seconds=_bounded_int(
            values.get("poll_interval_seconds"), default=180, minimum=60, maximum=3600
        ),
        request_timeout_seconds=_bounded_int(
            values.get("request_timeout_seconds"), default=15, minimum=3, maximum=30
        ),
        detail_concurrency=_bounded_int(
            values.get("detail_concurrency"), default=4, minimum=1, maximum=8
        ),
    )


def parse_warning_index(script: str) -> list[WarningReference] | None:
    """Parse a successful CMA index, or return ``None`` for invalid payloads."""
    payload = _parse_index_payload(script)
    if payload is None:
        return None

    rows = payload.get("data")
    if not isinstance(rows, list):
        return None

    references: list[WarningReference] = []
    for row in rows:
        reference = _parse_index_row(row)
        if reference is not None:
            references.append(reference)
    if rows and not references:
        return None
    return references


def parse_warning_detail(script: str, reference: WarningReference) -> dict[str, object]:
    """Normalize a China Weather detail wrapper into a FAN-compatible payload."""
    detail = _parse_detail_payload(script)
    _validate_detail_identifier(detail, reference.identifier)
    type_code = _required_code(detail, "TYPECODE", "typeCode", "type_code")
    level_code = _required_code(detail, "LEVELCODE", "levelCode", "level_code")
    color = _WARNING_LEVEL_COLORS.get(level_code)
    if color is None:
        raise ValueError("warning level code is not supported")

    headline = (
        _first_text(detail, "head", "HEAD", "headline", "HEADLINE", "title", "TITLE")
        or reference.title
    )
    title = (
        _first_text(detail, "head", "HEAD", "title", "TITLE", "headline", "HEADLINE")
        or headline
    )

    return {
        "id": build_fan_weather_event_id(reference.identifier, type_code, level_code),
        "effective": _first_text(
            detail, "ISSUETIME", "issueTime", "issuetime", "effective", "EFFECTIVE"
        ),
        "headline": headline,
        "title": title,
        "description": _first_text(
            detail,
            "ISSUECONTENT",
            "issueContent",
            "issuecontent",
            "description",
            "DESCRIPTION",
            "content",
            "CONTENT",
        ),
        "longitude": reference.longitude,
        "latitude": reference.latitude,
        "type": f"11B{type_code}_{color}",
        "transport_metadata": {
            "transport": "china_weather_http",
            "identifier": reference.identifier,
            "detail_path": reference.detail_path,
            "type_code": type_code,
            "level_code": level_code,
        },
    }


def build_fan_weather_event_id(identifier: str, type_code: str, level_code: str) -> str:
    """Reconstruct the FAN Studio weather event identity for one warning."""
    if not isinstance(identifier, str):
        raise ValueError("warning identifier must be a string")

    match = _WARNING_IDENTIFIER_PATTERN.fullmatch(identifier)
    if match is None:
        raise ValueError(
            "warning identifier does not contain a FAN-compatible identity"
        )
    prefix = match.group("prefix")
    issued_at = match.group("issued_at")
    try:
        datetime.strptime(issued_at, "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise ValueError(
            "warning identifier does not contain a valid issue timestamp"
        ) from exc

    return (
        f"{prefix[:6]}-{issued_at}-11B"
        f"{_normalize_code(type_code)}{_normalize_code(level_code)}"
    )


class WarningSnapshotTracker:
    """Track a bounded set of observed warnings with warm-start semantics."""

    def __init__(self, max_entries: int) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._observed: OrderedDict[str, None] = OrderedDict()
        self._is_warm = False

    def observe(
        self, references: list[WarningReference] | None
    ) -> list[WarningReference]:
        """Return new references without warming on an invalid index result."""
        if references is None:
            return []

        new_references: list[WarningReference] = []
        for reference in references:
            if reference.identifier not in self._observed and self._is_warm:
                new_references.append(reference)
            self._remember(reference.identifier)

        self._is_warm = True
        return new_references

    def forget(self, identifier: str) -> None:
        """Make one failed warning eligible for the next snapshot cycle."""
        self._observed.pop(identifier, None)

    def _remember(self, identifier: str) -> None:
        self._observed.pop(identifier, None)
        self._observed[identifier] = None
        while len(self._observed) > self._max_entries:
            self._observed.popitem(last=False)


class BoundedTTLSet:
    """A bounded membership set whose entries expire after a fixed TTL."""

    def __init__(
        self,
        ttl_seconds: float,
        max_entries: int,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock or monotonic
        self._entries: OrderedDict[str, float] = OrderedDict()

    def add(self, value: str) -> None:
        """Add or refresh a value, evicting expired and oldest entries first."""
        now = self._clock()
        self._purge_expired(now)
        self._entries.pop(value, None)
        self._entries[value] = now
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def __contains__(self, value: object) -> bool:
        self._purge_expired(self._clock())
        return value in self._entries

    def _purge_expired(self, now: float) -> None:
        expired = [
            value
            for value, added_at in self._entries.items()
            if now - added_at >= self._ttl_seconds
        ]
        for value in expired:
            del self._entries[value]


class ChinaWeatherReconciler:
    """Reconcile snapshots with an at-most-once boundary at callback return.

    Path validation and detail fetch/parse failures are retryable. Calling the
    authoritative downstream handler is the at-most-once boundary: both a
    normal return and an exception consume the reference because downstream
    work may already have completed partially.
    """

    def __init__(self, detail_concurrency: int, max_entries: int = 4096) -> None:
        if not 1 <= detail_concurrency <= 8:
            raise ValueError("detail_concurrency must be between 1 and 8")
        self._tracker = WarningSnapshotTracker(max_entries=max_entries)
        self._detail_semaphore = asyncio.Semaphore(detail_concurrency)

    async def reconcile(
        self,
        index_script: str,
        fetch_detail: Callable[[str], Awaitable[str]],
        dispatch: Callable[[dict[str, object]], Awaitable[object]],
    ) -> ReconciliationCycleResult:
        """Process one valid snapshot without coupling to a specific HTTP client."""
        references = parse_warning_index(index_script)
        if references is None:
            return ReconciliationCycleResult(index_valid=False)

        new_references = self._tracker.observe(references)
        if not new_references:
            return ReconciliationCycleResult(
                index_valid=True,
                reference_count=len(references),
            )

        outcomes = await asyncio.gather(
            *(
                self._process_reference(reference, fetch_detail, dispatch)
                for reference in new_references
            )
        )
        failed_identifiers = tuple(
            outcome[0] for outcome in outcomes if outcome[0] is not None
        )
        consumed_error_identifiers = tuple(
            outcome[1] for outcome in outcomes if outcome[1] is not None
        )
        return ReconciliationCycleResult(
            index_valid=True,
            reference_count=len(references),
            new_count=len(new_references),
            consumed_count=len(new_references) - len(failed_identifiers),
            failed_identifiers=failed_identifiers,
            consumed_error_identifiers=consumed_error_identifiers,
        )

    async def _process_reference(
        self,
        reference: WarningReference,
        fetch_detail: Callable[[str], Awaitable[str]],
        dispatch: Callable[[dict[str, object]], Awaitable[object]],
    ) -> tuple[str | None, str | None]:
        try:
            detail_path = validate_detail_path(reference.detail_path)
            async with self._detail_semaphore:
                detail_script = await fetch_detail(detail_path)
                payload = parse_warning_detail(detail_script, reference)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._tracker.forget(reference.identifier)
            return reference.identifier, None

        try:
            async with self._detail_semaphore:
                await dispatch(payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            return None, reference.identifier
        return None, None


def validate_detail_path(detail_path: object) -> str:
    """Accept only an unencoded relative file name from the compact index."""
    if not isinstance(detail_path, str) or not detail_path:
        raise ValueError("warning detail path must be a non-empty string")
    if detail_path != detail_path.strip() or unquote(detail_path) != detail_path:
        raise ValueError("warning detail path must be an unencoded file name")

    parsed = urlsplit(detail_path)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("warning detail path cannot contain URL components")
    if "\\" in detail_path:
        raise ValueError("warning detail path cannot contain backslashes")

    path = PurePosixPath(parsed.path)
    if path.is_absolute() or len(path.parts) != 1 or path.name in {".", ".."}:
        raise ValueError("warning detail path must be a relative file name")
    if _DETAIL_FILE_PATTERN.fullmatch(path.name) is None:
        raise ValueError("warning detail path contains unsupported characters")
    return path.name


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        resolved = default
    else:
        try:
            resolved = int(value)
        except (TypeError, ValueError, OverflowError):
            resolved = default
    return min(max(resolved, minimum), maximum)


def _parse_index_payload(script: str) -> dict[str, Any] | None:
    return _parse_alarminfo_payload(script)


def _parse_alarminfo_payload(script: str) -> dict[str, Any] | None:
    if not isinstance(script, str):
        return None
    stripped = script.strip()
    if not stripped.startswith(_INDEX_PREFIX):
        return None
    payload_text = stripped[len(_INDEX_PREFIX) :]
    if payload_text.endswith(";"):
        payload_text = payload_text[:-1]
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_index_row(row: object) -> WarningReference | None:
    if not isinstance(row, list) or len(row) != 7:
        return None
    detail_path, longitude, latitude, identifier, title = (
        row[1],
        row[2],
        row[3],
        row[4],
        row[6],
    )
    values = (detail_path, longitude, latitude, identifier, title)
    if not all(isinstance(value, str) and value.strip() for value in values):
        return None
    return WarningReference(
        identifier=identifier.strip(),
        detail_path=detail_path.strip(),
        longitude=longitude.strip(),
        latitude=latitude.strip(),
        title=title.strip(),
    )


def _parse_detail_payload(script: str) -> dict[str, Any]:
    payload = _parse_alarminfo_payload(script)
    if payload is None:
        raise ValueError("warning detail does not use the expected alarminfo wrapper")
    return payload


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    value = _first_value(payload, *keys)
    return value.strip() if isinstance(value, str) else ""


def _first_value(payload: dict[str, Any], *keys: str) -> object:
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
    return ""


def _required_code(payload: dict[str, Any], *keys: str) -> str:
    value = _first_value(payload, *keys)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("warning detail is missing a required code field")
    return _normalize_code(value.strip())


def _validate_detail_identifier(
    payload: dict[str, Any], reference_identifier: str
) -> None:
    for key in ("identifier", "IDENTIFIER"):
        if key not in payload:
            continue
        identifier = payload[key]
        if (
            not isinstance(identifier, str)
            or identifier.strip() != reference_identifier
        ):
            raise ValueError(
                "warning detail identifier does not match its index reference"
            )
        return
    raise ValueError("warning detail is missing an identifier")


def _normalize_code(code: str) -> str:
    if not isinstance(code, str) or not code.isdigit() or len(code) > 2:
        raise ValueError("warning type and level codes must be one or two digits")
    return code.zfill(2)
