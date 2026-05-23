"""
地震列表查询服务。
负责 Wolfx 地震列表缓存更新与卡片渲染所需的展示数据格式化。
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger


class EarthquakeListService:
    """地震列表查询与格式化服务。

    负责维护地震列表缓存，并把原始列表项整理为卡片可直接消费的展示结构。
    """

    def __init__(self, earthquake_lists: dict[str, dict[str, Any]] | None = None):
        """初始化地震列表缓存容器。"""
        # 初始化双区域缓存，分别为 CENC（中国地震台网）与 JMA（日本气象厅）地震列表
        self.earthquake_lists = earthquake_lists or {"cenc": {}, "jma": {}}

    def update_earthquake_list(self, list_type: str, data: dict[str, Any]):
        """更新内存中的地震列表。

        若目标列表仍为字典，则原地清空并覆写，尽量保持外部引用稳定。
        """
        if list_type in self.earthquake_lists:
            target = self.earthquake_lists.get(list_type)
            # 通过原地 clear 与 update，防止破坏原有的字典对象引用
            if isinstance(target, dict) and isinstance(data, dict):
                target.clear()
                target.update(data)
            else:
                self.earthquake_lists[list_type] = data
            logger.debug(f"[灾害预警] 已更新 {list_type} 地震列表缓存")

    def get_formatted_list_data(
        self, source_type: str, count: int
    ) -> list[dict[str, Any]]:
        """获取格式化后的地震列表数据（用于卡片渲染）。"""
        data = self.earthquake_lists.get(source_type, {})
        if not data:
            return []

        # Wolfx 列表以 No1/No2... 形式编号，这里按编号顺序取前 N 项用于展示。
        sorted_keys = sorted(
            [k for k in data.keys() if k.startswith("No")],
            key=lambda x: int(x[2:]) if x[2:].isdigit() else 999,
        )

        result: list[dict[str, Any]] = []
        for key in sorted_keys[:count]:
            item = data[key]
            formatted_item = self._format_list_item(source_type, item)
            if formatted_item:
                result.append(formatted_item)

        return result

    def _format_list_item(
        self, source_type: str, item: dict[str, Any]
    ) -> dict[str, Any] | None:
        """格式化单个列表项。

        同时兼容中国地震列表与日本地震情报在深度、震度字段上的差异。
        """
        try:
            location = item.get("location", "未知地点")
            time_str = item.get("time", "")
            magnitude = item.get("magnitude", "0.0")
            depth = item.get("depth", "0")

            depth_val = -1.0
            try:
                # 深度原始值可能混有字符串单位，这里先尽量规整成数值，便于统一做“极浅/ごく浅い”等展示判断。
                if isinstance(depth, (int, float)):
                    depth_val = float(depth)
                elif isinstance(depth, str):
                    clean_depth = depth.lower().replace("km", "").strip()
                    if clean_depth:
                        depth_val = float(clean_depth)
            except Exception:
                depth_val = -1.0

            depth_label = "深度"
            depth_value_str = str(depth).replace("km", "").strip()
            depth_unit = "km"

            if source_type == "jma":
                depth_label = "深さ"
                # 处理特殊深度为“极浅”
                if depth_val == 0.0:
                    depth_value_str = "ごく浅い"
                    depth_unit = ""
                    depth = "ごく浅い"
                else:
                    if depth_val >= 0:
                        formatted_val = (
                            f"{int(depth_val)}"
                            if depth_val.is_integer()
                            else f"{depth_val}"
                        )
                        depth = f"{formatted_val} km"
                        depth_value_str = formatted_val
                    else:
                        clean_d = str(depth).replace("km", "").strip()
                        depth = f"{clean_d} km"
            else:
                depth_label = "深度"
                # 处理特殊深度为“极浅”
                if depth_val == 0.0:
                    depth_value_str = "极浅"
                    depth_unit = ""
                    depth = "极浅"
                else:
                    if depth_val >= 0:
                        formatted_val = (
                            f"{int(depth_val)}"
                            if depth_val.is_integer()
                            else f"{depth_val}"
                        )
                        depth = f"{formatted_val} km"
                        depth_value_str = formatted_val
                    else:
                        clean_d = str(depth).replace("km", "").strip()
                        depth = f"{clean_d} km"

            # 不同来源使用不同的烈度或震度体系，这里先给出统一默认展示值。
            intensity_display = "-"
            intensity_class = "int-unknown"

            if source_type == "cenc":
                intensity = item.get("intensity")
                # 缺失烈度参数时，则根据震级粗略映射估算烈度级别
                if intensity is None or intensity == "":
                    try:
                        mag_val = float(magnitude)
                        if mag_val < 3:
                            intensity = "1"
                        elif mag_val < 5:
                            intensity = "3"
                        elif mag_val < 6:
                            intensity = "5"
                        elif mag_val < 7:
                            intensity = "7"
                        elif mag_val < 8:
                            intensity = "9"
                        else:
                            intensity = "11"
                    except Exception:
                        intensity = "0"

                intensity_display = str(intensity)

                try:
                    int_val = float(intensity)
                    # 划分烈度样式等级，用于卡片前端 HTML 的 CSS 上色渲染
                    if int_val < 3:
                        intensity_class = "int-1"
                    elif int_val < 5:
                        intensity_class = "int-2"
                    elif int_val < 6:
                        intensity_class = "int-3"
                    elif int_val < 7:
                        intensity_class = "int-4"
                    elif int_val < 8:
                        intensity_class = "int-5-weak"
                    elif int_val < 9:
                        intensity_class = "int-5-strong"
                    elif int_val < 10:
                        intensity_class = "int-6-weak"
                    elif int_val < 11:
                        intensity_class = "int-6-strong"
                    else:
                        intensity_class = "int-7"
                except Exception:
                    pass

            elif source_type == "jma":
                raw_shindo = item.get("shindo")
                shindo = str(raw_shindo or "").strip()
                normalized_shindo = shindo.lower()
                # 排除各种空值和带有未定义意义的非规整震度字符
                unknown_shindo_values = {
                    "",
                    "-",
                    "--",
                    "---",
                    "?",
                    "unknown",
                    "unk",
                    "none",
                    "null",
                    "nil",
                    "nan",
                    "n/a",
                    "na",
                    "0",
                    "0.0",
                    "不明",
                    "不详",
                    "不詳",
                    "调查中",
                }

                if normalized_shindo not in unknown_shindo_values:
                    intensity_display = shindo

                    # 映射日本气象厅最大震度分类到样式类名
                    if shindo == "1":
                        intensity_class = "int-1"
                    elif shindo == "2":
                        intensity_class = "int-2"
                    elif shindo == "3":
                        intensity_class = "int-3"
                    elif shindo == "4":
                        intensity_class = "int-4"
                    elif shindo in ["5-", "5弱"]:
                        intensity_class = "int-5-weak"
                    elif shindo in ["5+", "5強", "5强"]:
                        intensity_class = "int-5-strong"
                    elif shindo in ["6-", "6弱"]:
                        intensity_class = "int-6-weak"
                    elif shindo in ["6+", "6強", "6强"]:
                        intensity_class = "int-6-strong"
                    elif shindo == "7":
                        intensity_class = "int-7"
                    else:
                        intensity_display = "---"
                        intensity_class = "int-unknown"
                else:
                    intensity_display = "---"
                    intensity_class = "int-unknown"

            return {
                "location": location,
                "time": time_str,
                "magnitude": magnitude,
                "depth": depth,
                "depth_label": depth_label,
                "depth_value": depth_value_str,
                "depth_unit": depth_unit,
                "is_text_depth": (depth_val == 0.0),
                "intensity_display": intensity_display,
                "intensity_class": intensity_class,
                "raw": item,
            }

        except Exception as e:
            logger.error(f"[灾害预警] 格式化地震列表项失败: {e}")
            return None
