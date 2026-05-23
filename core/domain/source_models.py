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
    source_id: str  # 唯一数据源ID
    source_enum: str  # 旧枚举兼容标识
    provider_family: str  # 供应商家族
    source_type: str  # 数据源类型
    parser_name: str  # 解析器注册名称
    presentation_type: str  # 卡片渲染表示类型
    text_presenter_key: str  # 文本生成器注册键
    config_group: str  # 配置父组
    config_key: str  # 配置项键
    report_policy: str  # 警报合并报告策略
    intensity_mode: str  # 烈度计算/映射模式
    priority: int  # 推送和查询显示优先级数值
    display_name: str  # 人类可读的数据源友好显示名称
    # 默认时区主要用于时间字段解释。
    default_timezone: str = "UTC"
    # 以下字段用于指导如何从来源数据中提取关键业务字段。
    event_time_field: str = ""  # 事件发生时间字段名
    publish_time_field: str = ""  # 发布时间字段名
    report_num_field: str = ""  # 第几报字段名
    final_flag_field: str = ""  # 终报标志字段名
    issue_type_field: str = ""  # 发布类型字段名
    fingerprint_prefix: str = ""  # 排重指纹前缀
    connection_group: str = ""  # 归属连接组名
    # 一组别名和标签字段，用于兼容不同上游命名与路由匹配场景。
    provider_message_types: tuple[str, ...] = ()
    provider_source_names: tuple[str, ...] = ()
    provider_aliases: tuple[str, ...] = ()
    routing_tags: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)
