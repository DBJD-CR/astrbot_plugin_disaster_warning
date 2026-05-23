"""
原始事件载荷模型。
仅用于 parser / logging / trace 等原始数据保留场景，
避免展示层与规则层直接依赖松散原始字典。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SourcePayload:
    """统一原始载荷包装。"""

    # source_id 标识该原始数据来自哪个接入源。
    source_id: str
    provider_family: str = ""  # 数据服务商标识家族
    message_type: str = ""  # 原始消息类型字段
    # raw 存放原始字典内容；attributes 存放补充描述信息。
    raw: dict[str, Any] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """从原始载荷中按键取值。"""
        return self.raw.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        """返回原始载荷字典的浅拷贝。"""
        return dict(self.raw)


__all__ = ["SourcePayload"]
