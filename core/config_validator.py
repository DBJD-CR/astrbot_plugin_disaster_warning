from typing import Any

from astrbot.api import logger


class ConfigValidator:
    """
    配置校验器
    负责对插件配置进行统一的合法性校验、范围修正和默认值填充。
    """

    @staticmethod
    def validate(config: dict[str, Any]) -> dict[str, Any]:
        """
        执行所有配置校验逻辑
        :param config: 原始配置字典
        :return: 校验并修正后的配置字典
        """
        logger.info("[灾害预警] 正在进行配置校验...")

        # 1. 本地监控配置校验
        if "local_monitoring" in config:
            config["local_monitoring"] = ConfigValidator._validate_local_monitoring(
                config["local_monitoring"]
            )

        # 2. WebSocket 配置校验
        if "websocket_config" in config:
            config["websocket_config"] = ConfigValidator._validate_websocket_config(
                config["websocket_config"]
            )

        # 3. Web 管理端配置校验
        if "web_admin" in config:
            config["web_admin"] = ConfigValidator._validate_web_admin(
                config["web_admin"]
            )

        # 4. 策略配置校验
        if "strategies" in config:
            config["strategies"] = ConfigValidator._validate_strategies(
                config["strategies"]
            )

        # 5. 过滤器配置校验
        if "earthquake_filters" in config:
            config["earthquake_filters"] = ConfigValidator._validate_earthquake_filters(
                config["earthquake_filters"]
            )

        # 6. 气象配置校验
        if "weather_config" in config:
            config["weather_config"] = ConfigValidator._validate_weather_config(
                config["weather_config"]
            )

        # 7. 调试配置校验
        if "debug_config" in config:
            config["debug_config"] = ConfigValidator._validate_debug_config(
                config["debug_config"]
            )

        # 8. 推送列表校验
        if "target_sessions" in config:
            config["target_sessions"] = ConfigValidator._validate_target_sessions(
                config["target_sessions"]
            )

        # 9. 管理员列表校验
        if "admin_users" in config:
            config["admin_users"] = ConfigValidator._validate_admin_users(
                config["admin_users"]
            )

        # 10. 消息格式配置校验
        if "message_format" in config:
            config["message_format"] = ConfigValidator._validate_message_format(
                config["message_format"]
            )

        # 11. 推送频率控制校验
        if "push_frequency_control" in config:
            config["push_frequency_control"] = ConfigValidator._validate_push_frequency(
                config["push_frequency_control"]
            )

        # 12. 时区配置校验
        if "display_timezone" in config:
            config["display_timezone"] = ConfigValidator._validate_timezone(
                config["display_timezone"]
            )

        # 13. 遥测配置校验
        if "telemetry_config" in config:
            config["telemetry_config"] = ConfigValidator._validate_telemetry(
                config["telemetry_config"]
            )

        # 14. 数据源配置结构校验
        if "data_sources" in config:
            config["data_sources"] = ConfigValidator._validate_data_sources(
                config["data_sources"]
            )

        # 15. 顶层开关校验
        if "enabled" in config and not isinstance(config["enabled"], bool):
            config["enabled"] = True

        logger.info("[灾害预警] 配置校验完成")
        return config

    @staticmethod
    def _ensure_bool(cfg: dict[str, Any], key: str, default: bool = False):
        """确保配置项为布尔值"""
        if key in cfg and not isinstance(cfg[key], bool):
            logger.warning(
                f"[灾害预警] 配置警告: '{key}' 类型错误 (应为 bool)，已重置为 {default}。"
            )
            cfg[key] = default

    @staticmethod
    def _validate_local_monitoring(cfg: dict[str, Any]) -> dict[str, Any]:
        """校验本地监控配置"""
        if not isinstance(cfg, dict):
            return cfg

        # 经纬度校验
        lat = cfg.get("latitude")
        if isinstance(lat, (int, float)):
            if lat < -90 or lat > 90:
                logger.warning(
                    f"[灾害预警] 配置警告: 纬度 {lat} 超出范围 (-90~90)，已自动修正。"
                )
                cfg["latitude"] = max(-90.0, min(90.0, float(lat)))

        lon = cfg.get("longitude")
        if isinstance(lon, (int, float)):
            if lon < -180 or lon > 180:
                logger.warning(
                    f"[灾害预警] 配置警告: 经度 {lon} 超出范围 (-180~180)，已自动修正。"
                )
                cfg["longitude"] = max(-180.0, min(180.0, float(lon)))

        # 阈值校验
        threshold = cfg.get("intensity_threshold")
        if isinstance(threshold, (int, float)):
            if threshold < 0 or threshold > 12:
                logger.warning(
                    f"[灾害预警] 配置警告: 烈度阈值 {threshold} 超出范围 (0~12)，已自动修正。"
                )
                cfg["intensity_threshold"] = max(0.0, min(12.0, float(threshold)))

        # 地名校验
        if "place_name" in cfg and not isinstance(cfg["place_name"], str):
            cfg["place_name"] = str(cfg["place_name"])

        # 布尔值校验
        ConfigValidator._ensure_bool(cfg, "enabled", False)
        ConfigValidator._ensure_bool(cfg, "strict_mode", False)

        return cfg

    @staticmethod
    def _validate_websocket_config(cfg: dict[str, Any]) -> dict[str, Any]:
        """校验 WebSocket 配置"""
        if not isinstance(cfg, dict):
            return cfg

        # 重连间隔
        interval = cfg.get("reconnect_interval")
        if isinstance(interval, (int, float)) and interval < 1:
            logger.warning(
                f"[灾害预警] 配置警告: 重连间隔 {interval} 过小，已修正为 1 秒。"
            )
            cfg["reconnect_interval"] = 1

        # 最大重连次数
        max_retries = cfg.get("max_reconnect_retries")
        if isinstance(max_retries, int):
            if max_retries < 1:
                cfg["max_reconnect_retries"] = 1
            elif max_retries > 10:
                cfg["max_reconnect_retries"] = 10

        # 超时时间
        timeout = cfg.get("connection_timeout")
        if isinstance(timeout, (int, float)) and timeout < 1:
            logger.warning(
                f"[灾害预警] 配置警告: 连接超时 {timeout} 过小，已修正为 5 秒。"
            )
            cfg["connection_timeout"] = 5

        # 心跳间隔
        heartbeat = cfg.get("heartbeat_interval")
        if isinstance(heartbeat, (int, float)):
            if heartbeat < 10:
                logger.warning(
                    f"[灾害预警] 配置警告: 心跳间隔 {heartbeat} 过小，已修正为 10 秒。"
                )
                cfg["heartbeat_interval"] = 10
            elif heartbeat > 600:
                logger.warning(
                    f"[灾害预警] 配置警告: 心跳间隔 {heartbeat} 过大，已修正为 600 秒。"
                )
                cfg["heartbeat_interval"] = 600

        # 兜底重试间隔
        fallback_interval = cfg.get("fallback_retry_interval")
        if isinstance(fallback_interval, int) and fallback_interval < 300:
            logger.warning(
                f"[灾害预警] 配置警告: 兜底重试间隔 {fallback_interval} 过小，已修正为 10 秒。"
            )
            cfg["fallback_retry_interval"] = 300

        # 兜底重试最大次数
        fallback_count = cfg.get("fallback_retry_max_count")
        if isinstance(fallback_count, int) and fallback_count < -1:
            logger.warning(
                f"[灾害预警] 配置警告: 兜底重试最大次数 {fallback_count} 无效，已修正为 -1 (无限)。"
            )
            cfg["fallback_retry_max_count"] = -1

        # 布尔值校验
        ConfigValidator._ensure_bool(cfg, "fallback_retry_enabled", True)

        return cfg

    @staticmethod
    def _validate_web_admin(cfg: dict[str, Any]) -> dict[str, Any]:
        """校验 Web 管理端配置"""
        if not isinstance(cfg, dict):
            return cfg

        # 端口校验
        port = cfg.get("port")
        if isinstance(port, int):
            if port < 1 or port > 65535:
                logger.warning(
                    f"[灾害预警] 配置警告: Web端口 {port} 无效，已重置为默认值 8089。"
                )
                cfg["port"] = 8089
            elif port < 1024:
                logger.warning(
                    f"[灾害预警] 配置提示: Web端口 {port} 为特权端口，请确保有足够权限。"
                )

        # Host 校验
        if "host" in cfg and not isinstance(cfg["host"], str):
            logger.warning(
                "[灾害预警] 配置警告: Web Host 类型错误，已重置为 '0.0.0.0'。"
            )
            cfg["host"] = "0.0.0.0"

        # 布尔值校验
        ConfigValidator._ensure_bool(cfg, "enabled", False)

        return cfg

    @staticmethod
    def _validate_strategies(cfg: dict[str, Any]) -> dict[str, Any]:
        """校验策略配置"""
        if not isinstance(cfg, dict):
            return cfg

        # CENC 融合策略超时
        cenc_fusion = cfg.get("cenc_fusion", {})
        if isinstance(cenc_fusion, dict):
            timeout = cenc_fusion.get("timeout")
            if isinstance(timeout, (int, float)):
                if timeout < 1:
                    logger.warning(
                        f"[灾害预警] 配置警告: 融合策略超时 {timeout} 过小，已修正为 1 秒。"
                    )
                    cenc_fusion["timeout"] = 1
                elif timeout > 120:
                    logger.warning(
                        f"[灾害预警] 配置警告: 融合策略超时 {timeout} 过大，已修正为 120 秒。"
                    )
                    cenc_fusion["timeout"] = 120

            ConfigValidator._ensure_bool(cenc_fusion, "enabled", True)
            cfg["cenc_fusion"] = cenc_fusion

        return cfg

    @staticmethod
    def _validate_earthquake_filters(cfg: dict[str, Any]) -> dict[str, Any]:
        """校验地震过滤器配置"""
        if not isinstance(cfg, dict):
            return cfg

        # 1. 关键词过滤器
        keyword_filter = cfg.get("keyword_filter", {})
        if isinstance(keyword_filter, dict):
            if not isinstance(keyword_filter.get("blacklist"), list):
                keyword_filter["blacklist"] = []
            if not isinstance(keyword_filter.get("whitelist"), list):
                keyword_filter["whitelist"] = []
            ConfigValidator._ensure_bool(keyword_filter, "enabled", False)
            cfg["keyword_filter"] = keyword_filter

        # 2. 烈度过滤器
        intensity_filter = cfg.get("intensity_filter", {})
        if isinstance(intensity_filter, dict):
            min_mag = intensity_filter.get("min_magnitude")
            if isinstance(min_mag, (int, float)) and (min_mag < -3 or min_mag > 10):
                logger.warning(
                    f"[灾害预警] 配置警告: 烈度过滤器最小震级 {min_mag} 超出常规范围，已修正。"
                )
                intensity_filter["min_magnitude"] = max(-3.0, min(10.0, float(min_mag)))

            min_int = intensity_filter.get("min_intensity")
            if isinstance(min_int, (int, float)) and (min_int < 0 or min_int > 12):
                logger.warning(
                    f"[灾害预警] 配置警告: 烈度过滤器最小烈度 {min_int} 超出范围，已修正。"
                )
                intensity_filter["min_intensity"] = max(0.0, min(12.0, float(min_int)))

            ConfigValidator._ensure_bool(intensity_filter, "enabled", True)
            cfg["intensity_filter"] = intensity_filter

        # 3. 震度过滤器 (Scale Filter)
        scale_filter = cfg.get("scale_filter", {})
        if isinstance(scale_filter, dict):
            min_mag = scale_filter.get("min_magnitude")
            if isinstance(min_mag, (int, float)) and (min_mag < -2 or min_mag > 12):
                logger.warning(
                    f"[灾害预警] 配置警告: 震度过滤器最小震级 {min_mag} 超出常规范围，已修正。"
                )
                scale_filter["min_magnitude"] = max(-2.0, min(12.0, float(min_mag)))

            min_scale = scale_filter.get("min_scale")
            if isinstance(min_scale, (int, float)) and (min_scale < 0 or min_scale > 7):
                logger.warning(
                    f"[灾害预警] 配置警告: 震度过滤器最小震度 {min_scale} 超出范围 (0-7)，已修正。"
                )
                scale_filter["min_scale"] = max(0.0, min(7.0, float(min_scale)))

            ConfigValidator._ensure_bool(scale_filter, "enabled", True)
            cfg["scale_filter"] = scale_filter

        # 4. 仅震级过滤器 (Magnitude Only Filter)
        mag_filter = cfg.get("magnitude_only_filter", {})
        if isinstance(mag_filter, dict):
            min_mag = mag_filter.get("min_magnitude")
            if isinstance(min_mag, (int, float)) and (min_mag < -2 or min_mag > 12):
                logger.warning(
                    f"[灾害预警] 配置警告: 仅震级过滤器最小震级 {min_mag} 超出常规范围，已修正。"
                )
                mag_filter["min_magnitude"] = max(-2.0, min(12.0, float(min_mag)))

            ConfigValidator._ensure_bool(mag_filter, "enabled", True)
            cfg["magnitude_only_filter"] = mag_filter

        # 5. Global Quake 过滤器
        gq_filter = cfg.get("global_quake_filter", {})
        if isinstance(gq_filter, dict):
            min_mag = gq_filter.get("min_magnitude")
            if isinstance(min_mag, (int, float)) and (min_mag < -2 or min_mag > 12):
                logger.warning(
                    f"[灾害预警] 配置警告: GQ过滤器最小震级 {min_mag} 超出常规范围，已修正。"
                )
                gq_filter["min_magnitude"] = max(-2.0, min(12.0, float(min_mag)))

            min_int = gq_filter.get("min_intensity")
            if isinstance(min_int, (int, float)) and (min_int < 0 or min_int > 12):
                logger.warning(
                    f"[灾害预警] 配置警告: GQ过滤器最小烈度 {min_int} 超出范围，已修正。"
                )
                gq_filter["min_intensity"] = max(0.0, min(12.0, float(min_int)))

            ConfigValidator._ensure_bool(gq_filter, "enabled", True)
            cfg["global_quake_filter"] = gq_filter

        return cfg

    @staticmethod
    def _validate_weather_config(cfg: dict[str, Any]) -> dict[str, Any]:
        """校验气象配置"""
        if not isinstance(cfg, dict):
            return cfg

        # 气象过滤器
        weather_filter = cfg.get("weather_filter", {})
        if isinstance(weather_filter, dict):
            if not isinstance(weather_filter.get("provinces"), list):
                weather_filter["provinces"] = []

            min_level = weather_filter.get("min_color_level")
            valid_levels = ["白色", "蓝色", "黄色", "橙色", "红色"]
            if min_level and min_level not in valid_levels:
                # 仅警告，不强制重置
                logger.warning(
                    f"[灾害预警] 配置警告: 气象预警级别 '{min_level}' 不在标准列表中。"
                )

            ConfigValidator._ensure_bool(weather_filter, "enabled", False)
            cfg["weather_filter"] = weather_filter

        max_len = cfg.get("max_description_length")
        if isinstance(max_len, int) and max_len < 0:
            logger.warning(
                f"[灾害预警] 配置警告: 气象描述长度限制 {max_len} 无效，已修正为 0 (不限制)。"
            )
            cfg["max_description_length"] = 0

        ConfigValidator._ensure_bool(cfg, "enable_weather_icon", True)

        return cfg

    @staticmethod
    def _validate_debug_config(cfg: dict[str, Any]) -> dict[str, Any]:
        """校验调试配置"""
        if not isinstance(cfg, dict):
            return cfg

        # 日志大小限制
        max_size = cfg.get("log_max_size_mb")
        if isinstance(max_size, (int, float)):
            if max_size < 1:
                logger.warning(
                    f"[灾害预警] 配置警告: 日志最大大小 {max_size}MB 过小，已修正为 1MB。"
                )
                cfg["log_max_size_mb"] = 1
            elif max_size > 1024:
                logger.warning(
                    f"[灾害预警] 配置警告: 日志最大大小 {max_size}MB 过大，已修正为 1024MB。"
                )
                cfg["log_max_size_mb"] = 1024

        # 保留文件数量
        max_files = cfg.get("log_max_files")
        if isinstance(max_files, int):
            if max_files < 1:
                logger.warning(
                    f"[灾害预警] 配置警告: 日志保留文件数 {max_files} 过小，已修正为 1。"
                )
                cfg["log_max_files"] = 1
            elif max_files > 64:
                logger.warning(
                    f"[灾害预警] 配置警告: 日志保留文件数 {max_files} 过大，已修正为 64。"
                )
                cfg["log_max_files"] = 64

        # Wolfx 列表日志最大条目
        wolfx_max = cfg.get("wolfx_list_log_max_items")
        if isinstance(wolfx_max, int):
            if wolfx_max < 1:
                logger.warning(
                    f"[灾害预警] 配置警告: Wolfx日志条目数 {wolfx_max} 过小，已修正为 1。"
                )
                cfg["wolfx_list_log_max_items"] = 1
            elif wolfx_max > 50:
                logger.warning(
                    f"[灾害预警] 配置警告: Wolfx日志条目数 {wolfx_max} 过大，已修正为 50。"
                )
                cfg["wolfx_list_log_max_items"] = 50

        # 启动静默期
        silence = cfg.get("startup_silence_duration")
        if isinstance(silence, int):
            if silence < 0:
                cfg["startup_silence_duration"] = 0
            elif silence > 3600:
                logger.warning(
                    f"[灾害预警] 配置警告: 启动静默期 {silence} 秒 过长，已修正为 3600 秒。"
                )
                cfg["startup_silence_duration"] = 3600

        # 过滤消息类型列表校验
        if "filtered_message_types" in cfg:
            if not isinstance(cfg["filtered_message_types"], list):
                cfg["filtered_message_types"] = ["heartbeat", "ping", "pong"]
            else:
                # 确保元素都是字符串
                cfg["filtered_message_types"] = [
                    str(x) for x in cfg["filtered_message_types"] if x
                ]

        # 布尔值校验
        ConfigValidator._ensure_bool(cfg, "enable_raw_message_logging", False)
        ConfigValidator._ensure_bool(cfg, "filter_heartbeat_messages", True)
        ConfigValidator._ensure_bool(cfg, "filter_p2p_areas_messages", True)
        ConfigValidator._ensure_bool(cfg, "filter_duplicate_events", True)
        ConfigValidator._ensure_bool(cfg, "filter_connection_status", True)

        return cfg

    @staticmethod
    def _validate_target_sessions(sessions: Any) -> list[str]:
        """校验推送会话列表"""
        if not isinstance(sessions, list):
            logger.warning(
                "[灾害预警] 配置警告: target_sessions 不是列表，已重置为空列表。"
            )
            return []

        # 过滤非字符串项
        valid_sessions = [s for s in sessions if isinstance(s, str) and s.strip()]
        if len(valid_sessions) != len(sessions):
            logger.warning(
                "[灾害预警] 配置警告: target_sessions 中包含无效项，已自动过滤。"
            )

        return valid_sessions

    @staticmethod
    def _validate_admin_users(users: Any) -> list[str]:
        """校验管理员列表"""
        if not isinstance(users, list):
            return []

        # 确保都是字符串或数字，并转为字符串
        valid_users = []
        for u in users:
            if isinstance(u, (str, int)) and str(u).strip():
                valid_users.append(str(u))

        return valid_users

    @staticmethod
    def _validate_message_format(cfg: dict[str, Any]) -> dict[str, Any]:
        """校验消息格式配置"""
        if not isinstance(cfg, dict):
            return cfg

        # 地图缩放级别
        zoom = cfg.get("map_zoom_level")
        if isinstance(zoom, int):
            if zoom < 0:
                logger.warning(
                    f"[灾害预警] 配置警告: 地图缩放级别 {zoom} 过小，已修正为 0。"
                )
                cfg["map_zoom_level"] = 0
            elif zoom > 18:
                logger.warning(
                    f"[灾害预警] 配置警告: 地图缩放级别 {zoom} 过大，已修正为 18。"
                )
                cfg["map_zoom_level"] = 18

        # 浏览器池大小
        pool_size = cfg.get("browser_pool_size")
        if isinstance(pool_size, int):
            if pool_size < 1:
                logger.warning(
                    f"[灾害预警] 配置警告: 浏览器池大小 {pool_size} 过小，已修正为 1。"
                )
                cfg["browser_pool_size"] = 1
            elif pool_size > 10:
                logger.warning("[灾害预警] 配置警告: 浏览器池大小过大，已限制为 10。")
                cfg["browser_pool_size"] = 10

        # 地图源校验
        map_source = cfg.get("map_source")
        valid_sources = [
            "petallight",
            "petaldark",
            "arcwi",
            "arcwob",
            "arcwh",
            "geovis",
        ]
        if map_source and map_source not in valid_sources:
            # 仅警告，不强制重置，以支持未来扩展或自定义源
            logger.warning(
                f"[灾害预警] 配置警告: 地图源 '{map_source}' 不在标准列表中，请确认是否为自定义源。"
            )

        # Global Quake 模板校验
        gq_template = cfg.get("global_quake_template")
        valid_templates = ["Aurora", "DarkNight"]
        if gq_template and gq_template not in valid_templates:
            # 仅警告，不强制重置
            logger.warning(
                f"[灾害预警] 配置警告: GQ模板 '{gq_template}' 不在标准列表中，请确认是否为自定义模板。"
            )

        # Playwright 模式校验
        pw_mode = cfg.get("playwright_mode")
        valid_modes = ["local", "remote"]
        if pw_mode and pw_mode not in valid_modes:
            logger.warning(
                f"[灾害预警] 配置警告: Playwright 模式 '{pw_mode}' 无效，已重置为 'local'。"
            )
            cfg["playwright_mode"] = "local"

        # 远程 Playwright 地址校验
        if cfg.get("playwright_mode") == "remote":
            server_url = cfg.get("playwright_server_url")
            if (
                not server_url
                or not isinstance(server_url, str)
                or not server_url.strip()
            ):
                logger.warning(
                    "[灾害预警] 配置警告: 远程 Playwright 模式已启用但未配置服务器地址，已自动切换回 'local' 模式。"
                )
                cfg["playwright_mode"] = "local"
            else:
                # 简单检查 URL 格式
                server_url = server_url.strip()
                if not (
                    server_url.startswith("ws://")
                    or server_url.startswith("wss://")
                    or server_url.startswith("http://")
                    or server_url.startswith("https://")
                ):
                    logger.warning(
                        f"[灾害预警] 配置警告: 远程 Playwright 地址 '{server_url}' 格式可能不正确 (应以 ws://, wss://, http:// 或 https:// 开头)。"
                    )

        # 布尔值校验
        ConfigValidator._ensure_bool(cfg, "include_map", False)
        ConfigValidator._ensure_bool(cfg, "detailed_jma_intensity", False)
        ConfigValidator._ensure_bool(cfg, "use_global_quake_card", False)

        return cfg

    @staticmethod
    def _validate_push_frequency(cfg: dict[str, Any]) -> dict[str, Any]:
        """校验推送频率控制"""
        if not isinstance(cfg, dict):
            return cfg

        # 报数限制校验
        for key, max_val in [
            ("cea_cwa_report_n", 10),
            ("jma_report_n", 20),
            ("gq_report_n", 20),
        ]:
            val = cfg.get(key)
            if isinstance(val, int):
                if val < 1:
                    logger.warning(
                        f"[灾害预警] 配置警告: 推送频率 {key}={val} 过小，已修正为 1。"
                    )
                    cfg[key] = 1
                elif val > max_val:
                    logger.warning(
                        f"[灾害预警] 配置警告: 推送频率 {key}={val} 过大，已修正为 {max_val}。"
                    )
                    cfg[key] = max_val

        # 布尔值校验
        ConfigValidator._ensure_bool(cfg, "final_report_always_push", True)
        ConfigValidator._ensure_bool(cfg, "ignore_non_final_reports", False)

        return cfg

    @staticmethod
    def _validate_timezone(tz: Any) -> str:
        """校验时区配置"""
        if not isinstance(tz, str) or not tz.strip():
            return "UTC+8"
        return tz

    @staticmethod
    def _validate_telemetry(cfg: dict[str, Any]) -> dict[str, Any]:
        """校验遥测配置"""
        if not isinstance(cfg, dict):
            return cfg

        # 确保 enabled 是布尔值
        if "enabled" in cfg and not isinstance(cfg["enabled"], bool):
            cfg["enabled"] = True

        return cfg

    @staticmethod
    def _validate_data_sources(cfg: dict[str, Any]) -> dict[str, Any]:
        """校验数据源配置结构"""
        if not isinstance(cfg, dict):
            return cfg

        # 确保主要分类存在且为字典
        for key in ["fan_studio", "p2p_earthquake", "wolfx", "global_quake"]:
            if key in cfg:
                if not isinstance(cfg[key], dict):
                    logger.warning(
                        f"[灾害预警] 配置警告: 数据源 {key} 格式错误，已重置。"
                    )
                    cfg[key] = {"enabled": True}
                else:
                    # 仅确保 enabled 为 bool，其他字段保持原样以支持扩展（如 API Key 等字符串配置）
                    ConfigValidator._ensure_bool(cfg[key], "enabled", True)

        return cfg
