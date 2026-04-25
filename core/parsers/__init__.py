"""
解析器子系统导出。
统一收口解析器基类、解析器创建入口与目录一致性校验能力。
"""

from .base_parser import BaseParser
from .parser_registry import (
    create_parser_for_source,
    resolve_parser_class,
    validate_catalog_parser_names,
)

__all__ = [
    "BaseParser",
    "create_parser_for_source",
    "resolve_parser_class",
    "validate_catalog_parser_names",
]
