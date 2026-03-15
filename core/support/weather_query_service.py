import re
from datetime import datetime, timedelta, timezone
from typing import Any

from ...utils.formatters.weather import COLOR_LEVEL_EMOJI, SORTED_WEATHER_TYPES
from ...utils.time_converter import TimeConverter


def normalize_weather_color(color_token: str | None) -> str | None:
    """规范化预警颜色关键词。"""
    if not color_token:
        return None

    token = color_token.strip()
    if not token:
        return None

    color_map = {
        "红": "红色",
        "橙": "橙色",
        "黄": "黄色",
        "蓝": "蓝色",
        "白": "白色",
        "红色": "红色",
        "橙色": "橙色",
        "黄色": "黄色",
        "蓝色": "蓝色",
        "白色": "白色",
    }
    return color_map.get(token)


def parse_weather_query_filters(
    token_a: str | None,
    token_b: str | None,
) -> tuple[str | None, str | None]:
    """解析可选参数中的预警类型与预警颜色（顺序无关）。"""
    weather_type = None
    weather_color = None

    for token in (token_a, token_b):
        if not token:
            continue

        normalized_color = normalize_weather_color(token)
        if normalized_color:
            weather_color = normalized_color
            continue

        if weather_type is None:
            weather_type = token.strip()

    return weather_type, weather_color


def parse_event_time_to_utc(time_value: Any) -> datetime | None:
    """将事件时间解析并转换为 UTC（naive 视为 UTC+8）。"""
    parsed = TimeConverter.parse_datetime(time_value)
    if parsed is None:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TimeConverter._get_timezone("UTC+8"))

    return parsed.astimezone(timezone.utc)


def format_cn_time(dt_utc: datetime | None) -> str:
    """将 UTC 时间格式化为北京时间中文样式。"""
    if dt_utc is None:
        return "未知时间"

    cn_dt = dt_utc.astimezone(TimeConverter._get_timezone("UTC+8"))
    return TimeConverter._safe_strftime(cn_dt, "%Y年%m月%d日 %H时%M分%S秒")


def extract_weather_org(title_text: str, headline_text: str) -> str:
    """提取发布机构。"""
    candidate = (headline_text or title_text or "").strip()
    if not candidate:
        return "未知发布机构"

    match = re.search(r"^(.+?)发布", candidate)
    if match:
        return match.group(1)

    return candidate


def detect_weather_type(title_text: str, weather_type_code: str | None) -> str:
    """识别预警类型。"""
    text = title_text or ""
    for weather_type in SORTED_WEATHER_TYPES:
        if weather_type in text:
            return weather_type

    code_text = (weather_type_code or "").strip()
    for weather_type in SORTED_WEATHER_TYPES:
        if weather_type in code_text:
            return weather_type

    return "未知类型"


def detect_weather_color(level_text: str, title_text: str) -> str:
    """识别预警颜色。"""
    candidate = f"{level_text or ''} {title_text or ''}"
    for color in COLOR_LEVEL_EMOJI:
        if color in candidate:
            return color
    return "未知颜色"


def extract_weather_warning_core(title_text: str) -> str | None:
    """从完整标题中提取“XX(颜色)预警(信号)”核心短语。"""
    text = (title_text or "").strip()
    if not text:
        return None

    tail_match = re.search(
        r"([\u4e00-\u9fffA-Za-z0-9]{1,12}(?:红色|橙色|黄色|蓝色|白色)?预警(?:信号)?)$",
        text,
    )
    if tail_match:
        return tail_match.group(1)

    publish_match = re.search(
        r"发布([\u4e00-\u9fffA-Za-z0-9]{1,12}(?:红色|橙色|黄色|蓝色|白色)?预警(?:信号)?)",
        text,
    )
    if publish_match:
        return publish_match.group(1)

    return None


def build_weather_type_line(
    weather_type: str,
    weather_color: str,
    title_text: str,
) -> str:
    """构建“预警类型”展示文案（仅保留类型信息，不含地区前缀）。"""
    color_emoji = COLOR_LEVEL_EMOJI.get(weather_color, "")

    if weather_type != "未知类型":
        if weather_color != "未知颜色":
            return f"{weather_type}{weather_color}预警{color_emoji}"

        short_title = extract_weather_warning_core(title_text)
        if short_title:
            return f"{short_title}{color_emoji}"

        return f"{weather_type}预警{color_emoji}"

    short_title = extract_weather_warning_core(title_text)
    if short_title:
        return f"{short_title}{color_emoji}"

    return f"未知类型预警{color_emoji}"


async def query_weather_alarm_data(
    db,
    keyword: str,
    optional_a: str | None = None,
    optional_b: str | None = None,
) -> dict[str, Any]:
    """查询气象预警（供命令与 Web API 复用）。"""
    normalized_keyword = (keyword or "").strip()
    if not normalized_keyword:
        return {
            "success": False,
            "error": "参数不足",
            "usage": [
                "/气象预警查询 <省份/地名> <预警类型> <预警颜色>",
                "/气象预警查询 <预警ID>",
            ],
        }

    id_query = bool(re.match(r"^\d+_\d{12,14}$", normalized_keyword))
    if id_query:
        target_id = normalized_keyword
        matched = await db.find_weather_event_by_alarm_id(target_id)
        if not matched:
            return {
                "success": False,
                "query_mode": "id",
                "error": f"未找到预警ID为 {target_id} 的气象预警记录。请通过其他官方渠道进行查询",
            }

        title_text = str(matched.get("description") or "").strip()
        headline_text = str(matched.get("subtitle") or "").strip()
        body_text = str(
            matched.get("weather_detail") or matched.get("description") or ""
        ).strip()
        level_text = str(matched.get("level") or "").strip()
        weather_type_code = str(matched.get("weather_type_code") or "").strip()

        detected_type = detect_weather_type(title_text, weather_type_code)
        detected_color = detect_weather_color(level_text, title_text)
        color_emoji = COLOR_LEVEL_EMOJI.get(detected_color, "")

        guideline_text = None
        if "防御指南" in body_text:
            guideline_idx = body_text.find("防御指南")
            guideline_text = body_text[guideline_idx:].strip()

        return {
            "success": True,
            "query_mode": "id",
            "data": {
                "alarm_id": target_id,
                "title_text": title_text,
                "headline_text": headline_text,
                "body_text": body_text,
                "level_text": level_text,
                "weather_type_code": weather_type_code,
                "detected_type": detected_type,
                "detected_color": detected_color,
                "color_emoji": color_emoji,
                "guideline_text": guideline_text,
                "icon_url": (
                    f"https://image.nmc.cn/assets/img/alarm/{weather_type_code}.png"
                    if weather_type_code
                    else None
                ),
            },
        }

    weather_events = await db.get_recent_weather_events(limit=5000)
    if not weather_events:
        return {
            "success": False,
            "query_mode": "search",
            "error": "暂无可查询的气象预警历史数据，请稍后重试。",
        }

    location_keyword = normalized_keyword
    query_type, query_color = parse_weather_query_filters(optional_a, optional_b)

    now_utc = datetime.now(timezone.utc)
    threshold_utc = now_utc - timedelta(hours=72)

    matched_items = []
    for item in weather_events:
        event_time_utc = parse_event_time_to_utc(item.get("time"))
        if event_time_utc is None or event_time_utc < threshold_utc:
            continue

        title_text = str(item.get("description") or "").strip()
        headline_text = str(item.get("subtitle") or "").strip()
        level_text = str(item.get("level") or "").strip()
        weather_type_code = str(item.get("weather_type_code") or "").strip()
        haystack = f"{title_text} {headline_text}"

        if location_keyword not in haystack:
            continue

        detected_type = detect_weather_type(title_text, weather_type_code)
        detected_color = detect_weather_color(level_text, title_text)

        if query_type and query_type not in haystack and query_type != detected_type:
            continue

        if (
            query_color
            and query_color != detected_color
            and query_color not in haystack
        ):
            continue

        matched_items.append(
            {
                "raw": item,
                "event_time_utc": event_time_utc,
                "title_text": title_text,
                "headline_text": headline_text,
                "weather_type": detected_type,
                "weather_color": detected_color,
            }
        )

    matched_items.sort(key=lambda entry: entry["event_time_utc"], reverse=True)

    if not matched_items:
        return {
            "success": False,
            "query_mode": "search",
            "error": "未查询到符合条件的气象预警（仅检索近72小时内数据）。",
            "filters": {
                "location": location_keyword,
                "type": query_type,
                "color": query_color,
            },
        }

    items: list[dict[str, Any]] = []
    for entry in matched_items:
        item = entry["raw"]
        title_text = entry["title_text"]
        headline_text = entry["headline_text"]
        weather_type = entry["weather_type"]
        weather_color = entry["weather_color"]
        weather_type_code = str(item.get("weather_type_code") or "").strip()

        items.append(
            {
                "issue_time": format_cn_time(entry["event_time_utc"]),
                "alarm_id": item.get("unique_id")
                or item.get("real_event_id")
                or "未知ID",
                "publish_org": extract_weather_org(title_text, headline_text),
                "weather_type_line": build_weather_type_line(
                    weather_type,
                    weather_color,
                    title_text,
                ),
                "weather_type": weather_type,
                "weather_color": weather_color,
                "title_text": title_text,
                "headline_text": headline_text,
                "weather_type_code": weather_type_code,
                "icon_url": (
                    f"https://image.nmc.cn/assets/img/alarm/{weather_type_code}.png"
                    if weather_type_code
                    else None
                ),
            }
        )

    return {
        "success": True,
        "query_mode": "search",
        "filters": {
            "location": location_keyword,
            "type": query_type,
            "color": query_color,
            "time_window_hours": 72,
        },
        "items": items,
    }
