"""
来源模型。

该模型用于描述一个数据源在系统中的静态画像，
例如它属于哪类来源、采用什么解析器、使用什么展示方式、
以及在配置、路由和去重时需要参考的固定字段。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    """数据源描述模型。"""

    # 以下字段共同决定一个数据源的基础身份与处理方式。
    source_id: str
    source_enum: str
    provider_family: str
    source_type: str
    parser_name: str
    presentation_type: str
    text_presenter_key: str
    config_group: str
    config_key: str
    report_policy: str
    intensity_mode: str
    priority: int
    display_name: str
    # 默认时区主要用于时间字段解释。
    default_timezone: str = "UTC"
    # 以下字段用于指导如何从来源数据中提取关键业务字段。
    event_time_field: str = ""
    publish_time_field: str = ""
    report_num_field: str = ""
    final_flag_field: str = ""
    issue_type_field: str = ""
    fingerprint_prefix: str = ""
    connection_group: str = ""
    # 一组别名和标签字段，用于兼容不同上游命名与路由匹配场景。
    provider_message_types: tuple[str, ...] = ()
    provider_source_names: tuple[str, ...] = ()
    provider_aliases: tuple[str, ...] = ()
    routing_tags: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)
