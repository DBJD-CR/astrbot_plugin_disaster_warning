"""
插件入口层的查询展示辅助方法。
用于承载命令查询文本拼装等纯展示逻辑，减少 main.py 中入口类的体积。
"""

from __future__ import annotations

from datetime import datetime

import astrbot.api.message_components as Comp

from ....utils.version import get_plugin_version


def quoted_plain_result(plugin, event, text: str):
    """构造带引用回复的纯文本结果。"""
    # 统一复用插件入口层的引用回复包装，避免多个命令重复拼接相同逻辑。
    # 这里直接返回事件结果对象，调用方可继续保持与 AstrBot 事件回复接口一致的使用方式。
    return event.chain_result(plugin._with_quote_reply(event, [Comp.Plain(text)]))


def format_earthquake_list_text(data_list: list[dict], source: str) -> str:
    """格式化地震列表文本（仿原始消息记录风格）。"""
    if not data_list:
        return "暂无数据"

    # 文本输出沿用日志风格，方便用户侧查询结果与调试日志在视觉结构上保持一致。
    # 这里故意保留 source_name 的内部标识格式，是为了让用户查询结果与来源标签一一对应。
    source_name = "http_wolfx_cenc" if source == "cenc" else "http_wolfx_jma"
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"🕐 查询时间: {current_time}",
        f"📡 来源: {source_name}",
        "📋 类型: earthquake_list_query",
        "",
        "📊 列表数据:",
        f"    📋 total_events: {len(data_list)} (显示数量)",
        f"    📋 sample_events ({len(data_list)}项):",
    ]

    # 循环写入地震条目文本
    for i, item in enumerate(data_list):
        idx = i + 1
        lines.append(f"      [{idx}]:")
        # 这里直接按既有字段名读取，说明 data_list 在进入本方法前已经过上游标准化。
        lines.append(f"        📋 发生时间: {item['time']}")
        lines.append(f"        📋 震中: {item['location']}")
        lines.append(f"        📋 震级: {item['magnitude']}")
        depth_label = item.get("depth_label", "深度")
        lines.append(f"        📋 {depth_label}: {item['depth']}")

        # CENC 列表更适合展示“烈度”，JMA 列表则延续“震度”术语，
        # 保持与各数据源原始表达习惯一致，避免用户对字段语义产生歧义。
        if source == "cenc":
            lines.append(f"        📋 烈度: {item['intensity_display']}")
        else:
            lines.append(f"        📋 震度: {item['intensity_display']}")

    lines.append("")
    version = get_plugin_version()  # 获取当前插件的版本号
    lines.append(f"🔧 @DBJD-CR/astrbot_plugin_disaster_warning (灾害预警) {version}")
    return "\n".join(lines)
