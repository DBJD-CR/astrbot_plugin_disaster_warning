"""
应用层专用服务导出。

当前模块只暴露命令查询与文本拼装相关的辅助函数，
目的是为入口层提供稳定的导入边界，避免 main.py 直接感知过多内部实现细节。
"""

from .query_helpers import format_earthquake_list_text, quoted_plain_result

# __all__ 用于显式声明对外公开的入口，
# 后续若新增仅供内部使用的辅助函数，可不纳入该列表。
__all__ = [
    "quoted_plain_result",
    "format_earthquake_list_text",
]
