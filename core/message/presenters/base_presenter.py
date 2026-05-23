"""
统一展示器抽象定义。

该模块为各类文本展示器提供共同接口约束，
确保不同灾种、不同来源的展示器都能以一致方式被注册中心调用。
"""

from __future__ import annotations

from typing import Any

from ...domain.event_context import DisplayContext


class BasePresenter:
    """统一展示器接口。"""

    # 具体子类通常会覆写该名称，用于注册或调试输出。
    presenter_name = "base_presenter"

    @classmethod
    def present(
        cls, display_context: DisplayContext, options: dict[str, Any] | None = None
    ) -> str:
        """
        把展示上下文转换为最终文本。

        Args:
            display_context (DisplayContext): 标准化展示上下文
            options (Optional[dict]): 额外控制参数
        """
        raise NotImplementedError
