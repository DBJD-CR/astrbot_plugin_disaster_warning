"""
气象预警消息格式化器
"""

from ...models.models import WeatherAlarmData
from .base import BaseMessageFormatter

# 预警类型到Emoji的映射
WEATHER_EMOJI_MAP = {
    # 一、国家级标准预警（14类）
    "台风": "🌀",
    "暴雨": "⛈️",
    "强对流": "⛈️⚡",
    "暴雪": "❄️",
    "寒潮": "🥶",
    "大风": "🍃",
    "沙尘暴": "🏜️🌪️",
    "低温": "🌡️📉",
    "高温": "🌡️🔥",
    "干旱": "☀️🌵",
    "霜冻": "❄️🌡️",
    "冰冻": "🧊",
    "大雾": "🌫️",
    "霾": "🌫️😷",
    # 二、地方特色及专项预警
    # 海洋气象预警
    "海上大风": "🌊💨",
    "海上台风": "🌊🌀",
    "海上大雾": "🌊🌫️",
    "海上雷雨大风": "🌊⛈️💨",
    "海上雷电": "🌊⚡",
    "风暴潮": "🌊⬆️",
    "海浪": "🌊",
    "海啸": "🌊⚠️",
    "强季风": "🌬️🍃",
    # 地域性天气预警
    "道路冰雪": "🛣️🧊",
    "雪灾": "❄️⚠️",
    "大雪": "🌨️",
    "持续低温": "🌡️📉⏳",
    "严寒": "🥶",
    "低温冻害": "🥶🌱",
    "低温雨雪冰冻": "🌨️🧊",
    # 环境与火险预警
    "森林（草原）火险": "🌲🔥",
    "森林火险": "🌲🔥",
    "草原火险": "🌱🔥",
    "空气重污染": "🏭😷",
    "臭氧": "🧪",
    "浓浮尘": "🏜️🌫️",
    "沙尘": "🏜️💨",
    "重污染天气": "🌫️😷",
    # 强对流细分预警
    "雷电": "⚡",
    "雷暴大风": "⛈️💨",
    "短时强降水": "🌧️🚤",
    "龙卷风": "🌪️",
    "冰雹": "🌨️🧊",
    # 能见度类细分预警
    "轻雾": "🌫️",
    "重雾": "🌫️🌫️",
    "浓雾": "🌫️🌫️🌫️",
    "特强浓雾": "🌫️🌫️⚠️",
    # 温度类补充预警
    "寒冷": "🧥",
    "低温冷害": "🌡️📉🍂",
    "高温中暑": "☀️🤢",
    "干热风": "🔥🍃",
    "强降温": "📉🥶",
    # 城市与环境专项
    "灰霾": "🌫️",
    "臭氧污染": "🧪⚠️",
    "光化学烟雾": "🌫️🧪",
    # 农业气象预警
    "农业干旱": "🚜🌵",
    "农田渍涝": "🚜🌊",
    "作物霜冻": "🌱❄️",
    "倒春寒": "🌱🥶",
    "寒露风": "🍂🍃",
    # 水文与地质灾害预警
    "中小河流洪水": "🌊🏘️",
    "山洪灾害": "⛰️🌊",
    "地质灾害": "⛰️⚠️",
    # 交通气象预警
    "道路结冰": "🛣️🧊",
    "道路积雪": "🛣️❄️",
    "路面高温": "🛣️🔥",
    "航道结冰": "🚢🧊",
    # 特殊天气预警
    "飑线": "🌩️💨",
    "尘卷风": "🌪️",
    # 城市定制预警
    "城市内涝": "🏙️🌊",
    "建筑工地": "🏗️⚠️",
    "旅游景区": "🏕️⚠️",
    # 科研与作业预警
    "人工影响天气": "🚀☁️",
    "飞机积冰": "✈️🧊",
}

# 按长度排序，优先匹配长词
SORTED_WEATHER_TYPES = sorted(WEATHER_EMOJI_MAP.keys(), key=len, reverse=True)

# 预警级别颜色映射
COLOR_LEVEL_EMOJI = {
    "红色": "🔴",
    "橙色": "🟠",
    "黄色": "🟡",
    "蓝色": "🔵",
    "白色": "⚪",
}

# 默认正文描述最大长度
DEFAULT_MAX_DESCRIPTION_LENGTH = 384


class WeatherFormatter(BaseMessageFormatter):
    """气象预警格式化器"""

    @staticmethod
    def format_message(weather: WeatherAlarmData, options: dict = None) -> str:
        """格式化气象预警消息"""
        if options is None:
            options = {}

        # 提取预警类型（优先使用 title，兼容 headline）
        title = weather.title or ""
        headline = weather.headline or ""
        match_text = title or headline
        emoji = "⛈️"

        for name in SORTED_WEATHER_TYPES:
            if name in match_text:
                emoji = WEATHER_EMOJI_MAP[name]
                break

        # 提取预警颜色
        color_emoji = ""
        for color, icon in COLOR_LEVEL_EMOJI.items():
            if color in match_text:
                color_emoji = icon
                break

        lines = [f"{emoji}[气象预警]"]

        # 标题（优先 title）
        if title:
            lines.append(f"📋{title}{color_emoji}")
        elif headline:
            lines.append(f"📋{headline}{color_emoji}")

        # 副标题（headline）
        if headline and headline != title:
            lines.append(f"🏷️副标题：{headline}")

        # 描述
        if weather.description:
            desc = weather.description
            max_len = options.get(
                "max_description_length", DEFAULT_MAX_DESCRIPTION_LENGTH
            )
            if max_len > 0 and len(desc) > max_len:
                desc = desc[: max_len - 3] + "..."
            lines.append(f"📝{desc}")

        # 发布时间
        if weather.issue_time:
            timezone = options.get("timezone", "UTC+8")
            lines.append(
                f"⏰生效时间：{WeatherFormatter.format_time(weather.issue_time, timezone)}"
            )

        return "\n".join(lines)
