"""
插件查询与模拟命令服务。
负责气象预警查询、地震预警查询、地震列表查询与灾害预警模拟命令逻辑，
减少 main.DisasterWarningPlugin 中的查询与展示流程实现。
"""

from __future__ import annotations

import asyncio
import traceback

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain

from ...core.app.services import format_earthquake_list_text, quoted_plain_result
from ...core.services.query.weather_query_service import query_weather_alarm_data
from ...core.services.simulation.simulation_service import build_earthquake_simulation
from .telemetry_mixin import CommandTelemetryMixin


class PluginQueryCommandService(CommandTelemetryMixin):
    """插件查询与模拟命令服务。"""

    def __init__(self, plugin):
        self.plugin = plugin

    async def handle_query_weather_alarm(
        self,
        event,
        keyword: str | None = None,
        optional_a: str | None = None,
        optional_b: str | None = None,
    ):
        def _quoted_plain_result(text: str):
            return quoted_plain_result(self.plugin, event, text)

        def _build_forward_nodes(
            blocks: list[str],
            total_blocks: int,
            batch_index: int,
            batch_total: int,
            include_header: bool = True,
        ) -> Comp.Nodes | None:
            if not blocks:
                return None

            bot_id = event.get_self_id() or "0"
            bot_name = "灾害预警"
            nodes = Comp.Nodes([])
            if include_header:
                header = (
                    f"📋 全国气象预警列表（共 {total_blocks} 段）"
                    f"\n📦 分段发送：{batch_index + 1}/{batch_total}"
                )
                nodes.nodes.append(
                    Comp.Node(uin=bot_id, name=bot_name, content=[Comp.Plain(header)])
                )

            for block in blocks:
                nodes.nodes.append(
                    Comp.Node(uin=bot_id, name=bot_name, content=[Comp.Plain(block)])
                )
            return nodes

        async def _send_forward_batches(blocks: list[str]) -> bool:
            if not blocks:
                return False

            max_nodes_per_forward = 8
            total_blocks = len(blocks)
            batches = [
                blocks[i : i + max_nodes_per_forward]
                for i in range(0, total_blocks, max_nodes_per_forward)
            ]

            for idx, batch in enumerate(batches):
                nodes = _build_forward_nodes(
                    batch,
                    total_blocks=total_blocks,
                    batch_index=idx,
                    batch_total=len(batches),
                    include_header=idx == 0,
                )
                if not nodes:
                    continue
                chain = MessageChain([nodes])
                await self.plugin.context.send_message(event.unified_msg_origin, chain)

            return True

        async def _send_text_blocks(blocks: list[str], total_count: int) -> None:
            if not blocks:
                return

            for idx, block in enumerate(blocks):
                prefix = f"📋 气象预警列表（共 {total_count} 条）\n" if idx == 0 else ""
                if idx == 0:
                    chain = MessageChain(
                        self.plugin._with_quote_reply(
                            event, [Comp.Plain(prefix + block)]
                        )
                    )
                else:
                    chain = MessageChain([Comp.Plain(block)])
                await self.plugin.context.send_message(event.unified_msg_origin, chain)

        if not self.plugin.disaster_service:
            yield _quoted_plain_result("❌ 灾害预警服务未启动")
            return

        if not keyword:
            yield _quoted_plain_result(
                "❌ 参数不足。\n"
                "用法：\n"
                "• /气象预警查询 <省份/地名> [<预警类型>] [<预警颜色>]\n"
                "• /气象预警查询 全国 [<预警类型>] [<预警颜色>]\n"
                "• /气象预警查询 <预警ID>"
            )
            return

        try:
            db = self.plugin.disaster_service.statistics_manager.db
            result = await query_weather_alarm_data(db, keyword, optional_a, optional_b)

            if not result.get("success"):
                error_text = str(result.get("error") or "查询失败")
                if "官方渠道" not in error_text:
                    error_text = f"{error_text} 可尝试通过其他官方渠道进行查询"
                filters = result.get("filters")
                if isinstance(filters, dict) and result.get("query_mode") == "search":
                    desc = [f"地区={filters.get('location')}"]
                    if filters.get("type"):
                        desc.append(f"预警类型={filters.get('type')}")
                    if filters.get("color"):
                        desc.append(f"预警颜色={filters.get('color')}")
                    if desc:
                        error_text = f"❌ {error_text}\n检索条件：{'，'.join(desc)}"
                    else:
                        error_text = f"❌ {error_text}"
                else:
                    error_text = f"❌ {error_text}"

                if result.get("usage"):
                    usage_lines = "\n".join(f"• {line}" for line in result["usage"])
                    error_text = f"{error_text}\n用法：\n{usage_lines}"

                await self._track_command_feature(
                    "command_weather_query",
                    {
                        "success": False,
                        "query_mode": str(result.get("query_mode") or "unknown"),
                        "has_optional_type": bool(optional_a),
                        "has_optional_level": bool(optional_b),
                    },
                )
                yield _quoted_plain_result(error_text)
                return

            if result.get("query_mode") == "id":
                detail = result.get("data") or {}
                title_text = str(detail.get("title_text") or "").strip()
                headline_text = str(detail.get("headline_text") or "").strip()
                body_text = str(detail.get("body_text") or "").strip()
                color_emoji = str(detail.get("color_emoji") or "")

                if title_text:
                    title_line = f"📋{title_text}{color_emoji}"
                elif headline_text:
                    title_line = f"📋{headline_text}{color_emoji}"
                else:
                    title_line = "📋气象预警详情"

                lines = [title_line]
                if body_text:
                    lines.append(f"📝{body_text}")
                else:
                    lines.append("📝暂无详细描述")

                guideline_text = str(detail.get("guideline_text") or "").strip()
                if guideline_text:
                    lines.append(guideline_text)

                detail_text = "\n".join(lines)
                icon_url = detail.get("icon_url")
                await self._track_command_feature(
                    "command_weather_query",
                    {
                        "success": True,
                        "query_mode": "id",
                        "has_icon": bool(icon_url),
                    },
                )
                if icon_url:
                    try:
                        yield event.chain_result(
                            self.plugin._with_quote_reply(
                                event,
                                [
                                    Comp.Plain(detail_text),
                                    Comp.Image.fromURL(str(icon_url)),
                                ],
                            )
                        )
                    except Exception as icon_error:
                        logger.warning(
                            f"[灾害预警] 发送气象预警图标失败，已回退文本: {icon_error}"
                        )
                        yield _quoted_plain_result(detail_text)
                else:
                    yield _quoted_plain_result(detail_text)
                return

            items = result.get("items") or []
            text_blocks = result.get("text_blocks") or []
            is_nationwide = bool(result.get("is_nationwide"))
            total = result.get("total", len(items))

            if is_nationwide and text_blocks:
                try:
                    ok = await _send_forward_batches(text_blocks)
                    if ok:
                        await self._track_command_feature(
                            "command_weather_query",
                            {
                                "success": True,
                                "query_mode": str(result.get("query_mode") or "search"),
                                "is_nationwide": True,
                                "result_count": int(total or 0),
                                "has_optional_type": bool(optional_a),
                                "has_optional_level": bool(optional_b),
                                "delivery_mode": "forward_batches",
                            },
                        )
                        return
                except Exception as forward_error:
                    logger.warning(
                        f"[灾害预警] 合并转发送失败，回退文本: {forward_error}"
                    )
                    try:
                        await _send_text_blocks(text_blocks, total)
                        await self._track_command_feature(
                            "command_weather_query",
                            {
                                "success": True,
                                "query_mode": str(result.get("query_mode") or "search"),
                                "is_nationwide": True,
                                "result_count": int(total or 0),
                                "has_optional_type": bool(optional_a),
                                "has_optional_level": bool(optional_b),
                                "delivery_mode": "text_blocks",
                            },
                        )
                        return
                    except Exception as text_error:
                        logger.warning(f"[灾害预警] 文本回退发送失败: {text_error}")

            lines = [f"📋 气象预警列表（共 {total} 条）"]
            for idx, item in enumerate(items):
                lines.append(f"发布时间：{item.get('issue_time') or '未知时间'}")
                lines.append(f"ID：{item.get('alarm_id') or '未知ID'}")
                lines.append(f"发布机构：{item.get('publish_org') or '未知发布机构'}")
                lines.append(
                    f"预警类型：{item.get('weather_type_line') or '未知类型预警'}"
                )
                if idx != len(items) - 1:
                    lines.append("")

            await self._track_command_feature(
                "command_weather_query",
                {
                    "success": True,
                    "query_mode": str(result.get("query_mode") or "search"),
                    "is_nationwide": is_nationwide,
                    "result_count": int(total or 0),
                    "has_optional_type": bool(optional_a),
                    "has_optional_level": bool(optional_b),
                },
            )
            yield _quoted_plain_result("\n".join(lines))
        except Exception as e:
            logger.error(f"[灾害预警] 查询气象预警失败: {e}")
            yield _quoted_plain_result(f"❌ 查询失败: {e}")

    async def handle_query_earthquake_warning(self, event):
        def _quoted_plain_result(text: str):
            return quoted_plain_result(self.plugin, event, text)

        if not self.plugin.disaster_service:
            yield _quoted_plain_result("❌ 灾害预警服务未启动")
            return

        try:
            text = self.plugin.disaster_service.get_eew_query_text()
            await self._track_command_feature(
                "command_eew_status_query",
                {"success": True},
            )
            yield _quoted_plain_result(text)
        except Exception as e:
            logger.error(f"[灾害预警] 查询地震预警状态失败: {e}")
            yield _quoted_plain_result(f"❌ 查询失败: {e}")

    async def handle_query_earthquake_list(
        self,
        event,
        source: str = "cenc",
        count: int = 9,
        mode: str = "card",
    ):
        def _quoted_plain_result(text: str):
            return quoted_plain_result(self.plugin, event, text)

        if not self.plugin.disaster_service:
            yield _quoted_plain_result("❌ 灾害预警服务未启动")
            return

        source = source.lower()
        if source not in ["cenc", "jma"]:
            yield _quoted_plain_result("❌ 无效的数据源，仅支持 cenc 或 jma")
            return

        try:
            show_card = mode.lower() != "text"
            max_count = 50 if show_card else 50
            if count > max_count:
                count = max_count
                yield _quoted_plain_result(
                    f"⚠️ 提示：{'卡片' if show_card else '文本'}模式最多支持显示 {max_count} 条记录"
                )
            elif count < 1:
                count = 1

            request_count = 50
            formatted_list = self.plugin.disaster_service.earthquake_list_service.get_formatted_list_data(
                source, request_count
            )
            if not formatted_list:
                yield _quoted_plain_result(
                    f"❌ 未找到 {source.upper()} 的地震列表数据，可能是因为服务刚启动，尚未获取到数据。"
                )
                return

            if show_card and self.plugin.disaster_service.message_manager:
                display_list = formatted_list[:count]
                source_name = (
                    "中国地震台网 (CENC)" if source == "cenc" else "日本气象厅 (JMA)"
                )
                img_path = await self.plugin.disaster_service.message_manager.render_earthquake_list_card(
                    display_list, source_name
                )
                if img_path:
                    await self._track_command_feature(
                        "command_earthquake_list_query",
                        {
                            "success": True,
                            "source": source,
                            "mode": "card",
                            "count": int(count),
                        },
                    )
                    yield event.chain_result(
                        self.plugin._with_quote_reply(
                            event,
                            [Comp.Image.fromFileSystem(img_path)],
                        )
                    )
                    return

            text = format_earthquake_list_text(formatted_list[:count], source)
            await self._track_command_feature(
                "command_earthquake_list_query",
                {
                    "success": True,
                    "source": source,
                    "mode": "card" if show_card else "text",
                    "count": int(count),
                },
            )
            yield _quoted_plain_result(text)
        except Exception as e:
            logger.error(f"[灾害预警] 查询地震列表失败: {e}")
            yield _quoted_plain_result(f"❌ 查询失败: {e}")

    async def handle_simulate_disaster(
        self,
        event,
        lat: float,
        lon: float,
        magnitude: float,
        depth: float,
        source: str = "cea_fanstudio",
    ):
        def _quoted_plain_result(text: str):
            return quoted_plain_result(self.plugin, event, text)

        if not self.plugin.disaster_service:
            yield _quoted_plain_result("❌ 灾害预警服务未启动")
            return

        try:
            manager = self.plugin.disaster_service.message_manager
            simulation_result = build_earthquake_simulation(
                manager,
                lat=lat,
                lon=lon,
                magnitude=magnitude,
                depth=depth,
                source=source,
            )

            if simulation_result.global_pass and simulation_result.local_pass:
                msg_chain = await manager.build_message_async(
                    simulation_result.disaster_event
                )
                await self._track_command_feature(
                    "command_simulation_result",
                    {
                        "success": True,
                        "triggered": True,
                        "source": str(source or "unknown"),
                        "magnitude_bucket": round(magnitude),
                        "depth_bucket": int(depth // 10 * 10),
                    },
                )
                yield event.chain_result(
                    self.plugin._with_quote_reply(event, list(msg_chain.chain))
                )
                return

            await self._track_command_feature(
                "command_simulation_result",
                {
                    "success": True,
                    "triggered": False,
                    "source": str(source or "unknown"),
                    "magnitude_bucket": round(magnitude),
                    "depth_bucket": int(depth // 10 * 10),
                },
            )
            yield _quoted_plain_result("\n".join(simulation_result.report_lines))
        except Exception as e:
            logger.error(f"[灾害预警] 模拟预警失败: {e}\n{traceback.format_exc()}")
            yield _quoted_plain_result(f"❌ 模拟失败: {e}")

    async def handle_query_earthquake_warning_with_timeout(
        self, event, timeout: float = 15.0
    ):
        """带超时保护的地震预警查询。"""
        try:
            async for result in asyncio.wait_for(
                self.handle_query_earthquake_warning(event),
                timeout=timeout,
            ):
                yield result
        except TimeoutError:
            yield quoted_plain_result(self.plugin, event, "❌ 查询超时，请稍后重试")
