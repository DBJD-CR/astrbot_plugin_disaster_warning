"""Fan Studio 消息适配器。

统一处理 Fan Studio / 地方局 / EMSC 等风格的原始 payload，
将字段映射到当前解析器可消费的标准结构，并保留原始 payload 以便后续排查。
"""

from __future__ import annotations

from typing import Any


class FanStudioAdapter:
    """将不同风格的 Fan Studio 消息规范化为统一字典。"""

    @staticmethod
    def normalize(raw_payload: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(raw_payload, dict):
            return {}

        payload = dict(raw_payload)
        source_value = str(
            payload.get("source")
            or payload.get("sourceName")
            or payload.get("agency")
            or payload.get("source_name")
            or ""
        ).strip()

        data_container = payload.get("Data")
        if not isinstance(data_container, dict):
            data_container = payload.get("data")
        if not isinstance(data_container, dict):
            data_container = payload

        message_data = dict(data_container)
        normalized_source = FanStudioAdapter._infer_source(source_value, message_data)

        # 统一字段名，兼容地方局与 EMSC 的常见写法
        normalized_data = {
            "id": FanStudioAdapter._find_first_value(
                message_data,
                ["id", "event_id"],
                fallback=payload.get("id"),
            ),
            "eventId": FanStudioAdapter._find_first_value(
                message_data,
                ["eventId", "event_id"],
            ),
            "latitude": FanStudioAdapter._coerce_float(
                FanStudioAdapter._find_first_value(
                    message_data,
                    ["latitude", "lat", "Latitude"],
                )
            ),
            "longitude": FanStudioAdapter._coerce_float(
                FanStudioAdapter._find_first_value(
                    message_data,
                    ["longitude", "lon", "Longitude"],
                )
            ),
            "depth": FanStudioAdapter._coerce_float(
                FanStudioAdapter._find_first_value(
                    message_data,
                    ["depth", "depth_km", "Depth"],
                )
            ),
            "magnitude": FanStudioAdapter._coerce_float(
                FanStudioAdapter._find_first_value(
                    message_data,
                    ["magnitude", "mag", "Magnitude"],
                )
            ),
            "epiIntensity": FanStudioAdapter._find_first_value(
                message_data,
                ["epiIntensity", "intensity", "maxIntensity"],
            ),
            "placeName": FanStudioAdapter._find_first_value(
                message_data,
                ["placeName", "location", "place_name", "region"],
                fallback="",
            ),
            "province": FanStudioAdapter._find_first_value(
                message_data,
                ["province", "region"],
                fallback="",
            ),
            "shockTime": FanStudioAdapter._find_first_value(
                message_data,
                ["shockTime", "time", "origin_time"],
                fallback="",
            ),
            "updates": FanStudioAdapter._find_first_value(
                message_data,
                ["updates"],
                fallback=1,
            ),
            "isFinal": FanStudioAdapter._find_first_value(
                message_data,
                ["isFinal", "is_final"],
                fallback=False,
            ),
        }

        if normalized_data["epiIntensity"] is None and normalized_data["magnitude"] is not None:
            normalized_data["epiIntensity"] = normalized_data["magnitude"]

        normalized_payload = {
            "type": payload.get("type", "update"),
            "source": normalized_source,
            "raw": raw_payload,
            "Data": normalized_data,
            "id": normalized_data.get("id"),
            "eventId": normalized_data.get("eventId"),
            "latitude": normalized_data.get("latitude"),
            "longitude": normalized_data.get("longitude"),
            "depth": normalized_data.get("depth"),
            "magnitude": normalized_data.get("magnitude"),
            "epiIntensity": normalized_data.get("epiIntensity"),
            "placeName": normalized_data.get("placeName"),
            "province": normalized_data.get("province"),
            "shockTime": normalized_data.get("shockTime"),
            "updates": normalized_data.get("updates"),
            "isFinal": normalized_data.get("isFinal"),
        }

        # 保留原始 payload 中可能存在的额外字段，便于后续扩展
        for key, value in message_data.items():
            if key not in normalized_payload["Data"]:
                normalized_payload["Data"][key] = value

        return normalized_payload

    @staticmethod
    def _infer_source(source_value: str, message_data: dict[str, Any]) -> str:
        lowered = source_value.lower()
        if lowered in {"cea-pr", "cea_pr", "cea-pr-fanstudio", "china_earthquake_warning_provincial"}:
            return "cea-pr"
        if lowered in {"cea", "cea-fanstudio", "china_earthquake_warning"}:
            return "cea"
        if lowered in {"emsc", "emsc-fanstudio"}:
            return "emsc"
        if lowered in {"cwa", "cwa-eew", "taiwan_cwa_earthquake"}:
            return "cwa-eew"
        if "province" in message_data or message_data.get("province"):
            return "cea-pr"
        if "epiIntensity" in message_data or "event_id" in message_data:
            return "cea"
        return source_value or "cea"

    @staticmethod
    def _find_first_value(
        data: dict[str, Any],
        keys: list[str],
        fallback: Any = None,
    ) -> Any:
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            if isinstance(value, str) and value.strip() == "":
                continue
            return value
        return fallback

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() in {"", "null", "None"}:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
