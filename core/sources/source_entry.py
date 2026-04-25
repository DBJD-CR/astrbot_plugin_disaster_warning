"""
统一数据源注册项模型定义。
负责描述数据源类型、连接信息、路由标签、展示方式与融合策略等元数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SourceType(Enum):
    """统一数据源领域类型。"""

    EARTHQUAKE_WARNING = "earthquake_warning"
    EARTHQUAKE_INFO = "earthquake_info"
    TSUNAMI = "tsunami"
    WEATHER = "weather"


class ProviderFamily(Enum):
    """连接与提供方家族。"""

    FAN_STUDIO = "fan_studio"
    P2P = "p2p"
    WOLFX = "wolfx"
    GLOBAL_QUAKE = "global_quake"


class FusionRole(Enum):
    """融合策略中的数据源角色。"""

    PRIMARY = "primary"
    SECONDARY = "secondary"


@dataclass(frozen=True, slots=True)
class SourceEntry:
    """统一数据源注册项。

    单个实例完整描述一个可接入数据源在配置、路由、展示、查询和融合链路中的定位。
    """

    # 统一身份字段：用于跨模块稳定引用同一数据源。
    source_id: str
    source_enum: str
    source_type: SourceType
    provider_family: ProviderFamily
    # 配置定位字段：用于映射到 data_sources 下的具体开关位置。
    config_group: str
    config_key: str
    # 解析与展示字段：决定消息进入哪类解析器和展示链路。
    parser_name: str
    presentation_type: str
    text_presenter_key: str
    # 规则相关字段：控制报次策略、强度模式与排序优先级。
    report_policy: str
    intensity_mode: str
    priority: int
    display_name: str
    description: str = ""
    default_timezone: str = "Asia/Shanghai"
    event_time_field: str = "occurred_at"
    publish_time_field: str = ""
    report_num_field: str = ""
    final_flag_field: str = "is_final"
    issue_type_field: str = ""
    fingerprint_prefix: str = ""
    # 连接相关字段：用于生成 WebSocket 或其他接入通道的连接计划。
    connection_group: str = ""
    connection_handler: str = ""
    connection_data_source: str = ""
    connection_url: str = ""
    connection_backup_url: str = ""
    # 提供方映射字段：用于来源名称、消息类型和路由标签匹配。
    provider_message_types: tuple[str, ...] = ()
    provider_source_names: tuple[str, ...] = ()
    provider_aliases: tuple[str, ...] = ()
    routing_tags: tuple[str, ...] = ()
    payload_signatures: tuple[tuple[str, ...], ...] = ()
    payload_exclusions: tuple[tuple[str, ...], ...] = ()
    payload_predicates: tuple[str, ...] = ()
    # 查询与融合字段：用于机构分组、查询视图、融合策略和分发族。
    institution_key: str = ""
    institution_display_name: str = ""
    institution_active_name: str = ""
    query_group: str = ""
    fusion_group: str = ""
    fusion_role: FusionRole | None = None
    dispatch_family: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def config_path(self) -> tuple[str, str]:
        """返回数据源配置路径。"""
        return self.config_group, self.config_key

    @property
    def timezone_name(self) -> str:
        """返回数据源默认时区名称。"""
        return (self.default_timezone or "UTC").strip() or "UTC"

    @property
    def identity_fingerprint_prefix(self) -> str:
        """返回统一事件指纹前缀。"""
        return (self.fingerprint_prefix or self.source_id).strip()

    def resolve_metadata_field(self, field_name: str, default: str = "") -> str:
        """解析当前注册项对应的元数据字段名。"""
        value = getattr(self, field_name, default)
        # 某些字段允许在注册表中留空，这里统一做字符串化兜底，避免上层重复判空。
        if not isinstance(value, str):
            return default
        return value.strip() or default

    def build_connection_plan(self) -> dict[str, str]:
        """构建当前数据源所属连接组的连接计划片段。

        若连接信息不完整，则返回空字典，表示该数据源不能独立形成连接计划。
        """
        group_key = (self.connection_group or "").strip()
        handler = (self.connection_handler or "").strip()
        data_source = (self.connection_data_source or self.source_id).strip()
        url = (self.connection_url or "").strip()
        backup_url = (self.connection_backup_url or "").strip()
        # 连接分组、处理器和主地址任一缺失时，都视为该注册项无法独立产出连接计划。
        if not group_key or not handler or not url:
            return {}

        result = {
            "group_key": group_key,
            "url": url,
            "handler": handler,
            "data_source": data_source,
        }
        if backup_url:
            result["backup_url"] = backup_url
        return result
