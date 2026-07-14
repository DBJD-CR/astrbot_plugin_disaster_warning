"""
统计记录工厂。
负责将事件转换为事件摘要记录，供 recent_pushes / major_events / 数据库存储共用。
"""

from __future__ import annotations

from typing import Any

from ...domain.event_models import (
    EarthquakeEvent,
    EventEnvelope,
    TsunamiEvent,
    TyphoonEvent,
    WeatherEvent,
)
from ...domain.event_payload import SourcePayload
from ...domain.typhoon import (
    format_display_name,
    merge_peak_metrics,
    resolve_data_mode,
    to_float,
)
from ...services.identity.event_identity import resolve_report_num, resolve_source_id


def _adapt_event_envelope(event: EventEnvelope) -> EventEnvelope:
    """统一获取领域 envelope。"""
    return event


def _resolve_weather_level(
    weather_event: WeatherEvent | None,
    payload: dict[str, Any],
    metadata: dict[str, Any],
) -> str | None:
    """统一解析气象预警级别。"""
    # 先从领域事件自身元数据中取值，再逐层回退到统一元数据和原始载荷。
    event_metadata = (
        getattr(weather_event, "metadata", None)
        if isinstance(weather_event, WeatherEvent)
        else None
    )
    if not isinstance(event_metadata, dict):
        event_metadata = {}

    for source_dict, keys in (
        # 不同来源的级别字段命名并不一致，因此这里按一组候选键逐层兜底查找。
        (event_metadata, ["level", "alert_level", "alertLevel", "warningLevel"]),
        (metadata, ["level", "alert_level", "alertLevel", "warningLevel"]),
        (payload, ["alert_level", "alertLevel", "warningLevel", "level"]),
    ):
        for key in keys:
            value = source_dict.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    title_text = ""
    # 若结构化字段全部缺失，则退回到标题文本中按颜色关键词推断预警级别。
    if weather_event is not None:
        title_text = f"{weather_event.title or ''}{weather_event.headline or ''}"
    if not title_text:
        title_text = f"{metadata.get('title', '')}{metadata.get('headline', '')}"
    if not title_text:
        title_text = f"{payload.get('title', '')}{payload.get('headline', '')}"
    for color in ["红色", "橙色", "黄色", "蓝色", "白色"]:
        if color in title_text:
            return color
    return None


class EventRecordFactory:
    """事件记录工厂。"""

    @staticmethod
    def apply_common_fields(
        record: dict[str, Any],
        event: EventEnvelope,
        *,
        current_time: str,
        event_unique_id: str,
        description: str,
        source_id: str | None = None,
        update_count: int = 1,
    ) -> dict[str, Any]:
        """填充各类事件记录共享字段。"""
        envelope = _adapt_event_envelope(event)
        # 来源标识优先使用显式传入值，其次回退到事件自身来源或统一解析结果。
        resolved_source_id = source_id or envelope.source_id or resolve_source_id(event)
        event_id = envelope.id
        event_type = envelope.event_type
        record.update(
            {
                "timestamp": current_time,
                "event_id": event_id,
                "type": event_type,
                "source": resolved_source_id,
                "source_id": envelope.source_id or resolved_source_id,
                "description": description,
                "unique_id": event_unique_id,
                "update_count": update_count,
            }
        )
        return record

    @staticmethod
    def apply_earthquake_fields(
        record: dict[str, Any],
        event: EventEnvelope,
        *,
        earthquake_level: float | None = None,
    ) -> dict[str, Any]:
        """填充地震事件专有字段。"""
        envelope = _adapt_event_envelope(event)
        data = envelope.event
        if not isinstance(data, EarthquakeEvent):
            return record

        occurred_at = data.occurred_at.isoformat() if data.occurred_at else None
        # 地震记录除通用字段外，还需要补齐位置、震级、深度和报次相关信息。
        event_metadata = getattr(data, "metadata", None)
        if not isinstance(event_metadata, dict):
            event_metadata = {}
        info_type = str(event_metadata.get("info_type") or "").strip()
        record.update(
            {
                "latitude": data.latitude,
                "longitude": data.longitude,
                "place_name": data.place_name,
                "magnitude": data.magnitude,
                "depth": data.depth,
                "time": occurred_at,
                "real_event_id": envelope.id,
                "level": earthquake_level,
                "info_type": info_type,
            }
        )

        report_num = resolve_report_num(event)
        if report_num is not None:
            record["report_num"] = report_num
        return record

    @staticmethod
    def apply_weather_fields(
        record: dict[str, Any],
        event: EventEnvelope,
    ) -> dict[str, Any]:
        """填充气象预警专有字段。"""
        envelope = _adapt_event_envelope(event)
        domain_event = envelope.event
        if not isinstance(domain_event, WeatherEvent):
            return record

        # 气象来源字段差异较大，因此需要同时查看载荷、统一元数据和领域事件对象。
        payload = (
            envelope.payload.to_dict()
            if isinstance(envelope.payload, SourcePayload)
            else {}
        )
        metadata = envelope.metadata if isinstance(envelope.metadata, dict) else {}
        description = (
            getattr(domain_event, "description", None)
            or metadata.get("description")
            or metadata.get("detail")
            or payload.get("description")
            or payload.get("detail")
            or ""
        )
        record.update(
            {
                "subtitle": domain_event.headline or "",
                "weather_detail": description,
                "time": domain_event.effective_at.isoformat()
                if domain_event.effective_at
                else None,
            }
        )
        event_metadata = (
            getattr(domain_event, "metadata", None)
            if isinstance(domain_event, WeatherEvent)
            else None
        )
        if not isinstance(event_metadata, dict):
            event_metadata = {}

        # 天气类型编码可能分散在多个来源字段中，这里统一做多层兜底提取。
        weather_type_code = (
            event_metadata.get("weather_code")
            or event_metadata.get("weather_type")
            or event_metadata.get("type")
            or event_metadata.get("alert_code")
            or event_metadata.get("alertCode")
            or event_metadata.get("code")
            or metadata.get("weather_code")
            or metadata.get("weather_type")
            or metadata.get("type")
            or metadata.get("alert_code")
            or metadata.get("alertCode")
            or metadata.get("code")
            or payload.get("weather_code")
            or payload.get("weather_type")
            or payload.get("type")
            or payload.get("alert_code")
            or payload.get("alertCode")
            or payload.get("code")
            or ""
        )
        if weather_type_code:
            record["weather_type_code"] = weather_type_code
        else:
            record.pop("weather_type_code", None)

        level = _resolve_weather_level(domain_event, payload, metadata)
        if level is not None:
            record["level"] = level
        else:
            record.pop("level", None)
        return record

    @staticmethod
    def apply_tsunami_fields(
        record: dict[str, Any],
        event: EventEnvelope,
    ) -> dict[str, Any]:
        """填充海啸事件专有字段。"""
        envelope = _adapt_event_envelope(event)
        data = envelope.event
        if not isinstance(data, TsunamiEvent):
            return record

        # 海啸记录当前主要补齐发布时间与预警级别，结构保持尽量精简。
        record.update(
            {
                "time": data.issued_at.isoformat() if data.issued_at else None,
                "level": data.level,
            }
        )
        return record

    @staticmethod
    def _resolve_typhoon_data_mode(event: EventEnvelope) -> str:
        """解析台风数据形态标签（thin wrapper）。

        只负责从事件中提取原始 mode 候选值；别名映射统一由
        domain.resolve_data_mode 处理，不在工厂内维护第二套规则。
        规范化字段已收敛到 TyphoonEvent + envelope.metadata，
        payload.attributes 不再作为第三份存储扫描。
        """
        envelope = _adapt_event_envelope(event)
        candidates: list[Any] = []

        # 优先读取流水线元数据（parser / enrichment 写入位置）
        envelope_metadata = (
            envelope.metadata if isinstance(envelope.metadata, dict) else {}
        )
        candidates.extend(
            [
                envelope_metadata.get("typhoon_data_mode"),
                envelope_metadata.get("info_type"),
                envelope_metadata.get("data_source"),
            ]
        )

        # 兼容旧数据：领域事件自身 metadata 可能残留 mode 标记
        data = envelope.event
        if isinstance(data, TyphoonEvent):
            event_metadata = getattr(data, "metadata", None)
            if isinstance(event_metadata, dict):
                candidates.extend(
                    [
                        event_metadata.get("typhoon_data_mode"),
                        event_metadata.get("info_type"),
                        event_metadata.get("data_source"),
                    ]
                )

        for raw in candidates:
            text = str(raw or "").strip()
            if text:
                return resolve_data_mode(text, default="fan")
        return "fan"

    @staticmethod
    def apply_typhoon_fields(
        record: dict[str, Any],
        event: EventEnvelope,
    ) -> dict[str, Any]:
        """填充台风事件专有字段。"""
        envelope = _adapt_event_envelope(event)
        data = envelope.event
        if not isinstance(data, TyphoonEvent):
            return record

        # 台风记录补齐中心位置、强度参数与更新时间，便于历史查询与展示。
        # 注意：magnitude 字段在数据库语义上专属于地震震级，台风不复用该列，
        # 为了避免前端震级筛选器误命中台风事件；全部强度参数统一存入 weather_detail。
        # info_type 复用为台风数据形态标签（fan / enriched / eqsc_rebuild），
        # source_id 仍统一为 typhoon_fanstudio，避免拆成并列双源。
        #
        # 关键：level / wind_speed 列必须保存历史峰值，而不是当前瞬时强度。
        # 否则台风减弱后（如巴威从强台风回落到热带风暴）会把风王榜与
        # by_max_level 统计所需的峰值字段覆盖掉，重启后统计重建就会丢榜。
        data_mode = EventRecordFactory._resolve_typhoon_data_mode(event)
        peak_level, peak_wind, min_pressure = merge_peak_metrics(
            existing_level=record.get("level"),
            existing_wind=record.get("wind_speed"),
            existing_pressure=record.get("pressure"),
            incoming_level=data.typhoon_type,
            incoming_wind=data.wind_speed,
            incoming_pressure=data.pressure,
        )
        # 主表 level/wind_speed/pressure 存峰值；额外保留当次观测，供 event_updates 快照使用。
        current_level = str(data.typhoon_type or "").strip()
        current_wind = to_float(data.wind_speed)
        if current_wind is not None and current_wind <= 0:
            current_wind = None
        current_pressure = to_float(data.pressure)
        if current_pressure is not None and current_pressure <= 0:
            current_pressure = None
        record.update(
            {
                "real_event_id": data.typhoon_id,
                "latitude": data.latitude,
                "longitude": data.longitude,
                "level": peak_level,
                "wind_speed": peak_wind,
                "pressure": min_pressure,
                "time": data.updated_at.isoformat() if data.updated_at else None,
                "place_name": f"{data.name or data.name_en or data.typhoon_id}",
                "info_type": data_mode,
                "_snapshot_level": current_level,
                "_snapshot_wind_speed": current_wind,
                "_snapshot_pressure": current_pressure,
            }
        )
        # weather_detail 仅用于详情展示；统计峰值以独立列 level/wind_speed/pressure 为准。
        detail_parts: list[str] = []
        if min_pressure is not None:
            pressure_text = (
                int(min_pressure) if float(min_pressure).is_integer() else min_pressure
            )
            detail_parts.append(f"气压 {pressure_text} hPa")
        if peak_wind is not None:
            wind_text = int(peak_wind) if float(peak_wind).is_integer() else peak_wind
            detail_parts.append(f"风速 {wind_text} m/s")
        if data.power is not None:
            detail_parts.append(f"风力 {data.power} 级")
        if data.move_direction:
            detail_parts.append(f"移向 {data.move_direction}")
        if data.move_speed is not None:
            detail_parts.append(f"移速 {data.move_speed} km/h")
        if data.radius7 is not None:
            detail_parts.append(f"七级风圈 {data.radius7} km")
        if data.radius10 is not None:
            detail_parts.append(f"十级风圈 {data.radius10} km")
        record["weather_detail"] = "，".join(detail_parts)
        # 台风名称作为副标题展示；统一走领域展示名格式化，避免中英文拼接双实现。
        record["subtitle"] = format_display_name(
            data.name,
            data.name_en,
            data.typhoon_id,
            fallback=str(data.typhoon_id or "未知台风"),
        )
        # description 同步为可读标题，避免前端回退到“未知事件”
        if not record.get("description"):
            record["description"] = record["subtitle"]
        return record

    @staticmethod
    def build_base_record(
        event: EventEnvelope,
        *,
        current_time: str,
        event_unique_id: str,
        description: str,
        earthquake_level: float | None = None,
    ) -> dict[str, Any]:
        """构建基础统计记录。"""
        envelope = _adapt_event_envelope(event)
        source_id = envelope.source_id or resolve_source_id(event)
        record: dict[str, Any] = {
            "subtitle": "",
            "weather_detail": "",
        }
        # 先填充全部事件共享字段，再按事件类型补专有字段。
        EventRecordFactory.apply_common_fields(
            record,
            event,
            current_time=current_time,
            event_unique_id=event_unique_id,
            description=description,
            source_id=source_id,
            update_count=1,
        )

        if isinstance(envelope.event, EarthquakeEvent):
            # 地震事件需要补齐震级、深度、位置和报次等摘要字段。
            EventRecordFactory.apply_earthquake_fields(
                record,
                event,
                earthquake_level=earthquake_level,
            )
        elif isinstance(envelope.event, WeatherEvent):
            # 气象事件重点补充副标题、详细说明、颜色级别和类型编码。
            EventRecordFactory.apply_weather_fields(record, event)
        elif isinstance(envelope.event, TsunamiEvent):
            # 海啸事件则补充发布时间与等级字段即可。
            EventRecordFactory.apply_tsunami_fields(record, event)
        elif isinstance(envelope.event, TyphoonEvent):
            # 台风事件补充中心位置、强度参数与更新时间。
            EventRecordFactory.apply_typhoon_fields(record, event)

        return record
