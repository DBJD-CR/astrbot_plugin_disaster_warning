"""
会话差异配置管理器

实现 Default + Session Override 模式：
- 默认配置来源于插件全局配置
- 会话仅存储差异补丁 (override)
- 运行时按会话合并得到 effective 配置
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any

from astrbot.api import logger
from astrbot.api.star import StarTools


class SessionConfigManager:
    """会话差异配置管理器"""

    OVERRIDES_FILE = "session_overrides.json"
    LEGACY_FULL_CONFIGS_FILE = "session_configs.json"

    # 可覆写字段白名单（顶层键）
    ALLOWED_ROOT_KEYS = {
        "enabled",
        "display_timezone",
        "data_sources",
        "earthquake_filters",
        "local_monitoring",
        "message_format",
        "push_frequency_control",
        "strategies",
        "weather_config",
        "debug_config",
        # 会话级额外控制字段（插件自定义）
        "push_enabled",
    }

    def __init__(self, default_config_ref: dict[str, Any]):
        self.default_config_ref = default_config_ref
        self.storage_dir = StarTools.get_data_dir("astrbot_plugin_disaster_warning")
        self.overrides_file = os.path.join(self.storage_dir, self.OVERRIDES_FILE)
        self.legacy_full_configs_file = os.path.join(
            self.storage_dir, self.LEGACY_FULL_CONFIGS_FILE
        )

        self._overrides: dict[str, dict[str, Any]] = {}
        self._load()

    def _ensure_storage_dir(self) -> None:
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    def _load(self) -> None:
        """加载 override 文件，并执行一次兼容迁移。"""
        self._ensure_storage_dir()

        if os.path.exists(self.overrides_file):
            try:
                with open(self.overrides_file, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._overrides = {
                            str(k): v for k, v in data.items() if isinstance(v, dict)
                        }
                        return
            except Exception as e:
                logger.warning(f"[灾害预警] 读取会话差异配置失败，将使用空配置: {e}")

        self._overrides = {}

        # 兼容旧格式: session_configs.json (存的是完整配置)
        if os.path.exists(self.legacy_full_configs_file):
            try:
                with open(self.legacy_full_configs_file, encoding="utf-8") as f:
                    legacy_data = json.load(f)

                if isinstance(legacy_data, dict):
                    migrated = 0
                    for umo, full_conf in legacy_data.items():
                        if not isinstance(full_conf, dict):
                            continue
                        patch = self.compute_diff(
                            self._default_config_dict(), full_conf
                        )
                        patch = self._sanitize_patch(patch)
                        if patch:
                            self._overrides[str(umo)] = patch
                            migrated += 1

                    self._save()
                    logger.info(
                        f"[灾害预警] 已从旧会话配置迁移 {migrated} 条到差异配置存储"
                    )
            except Exception as e:
                logger.warning(f"[灾害预警] 迁移旧会话配置失败: {e}")

    def _save(self) -> None:
        self._ensure_storage_dir()
        temp_file = self.overrides_file + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._overrides, f, ensure_ascii=False, indent=2)
            if os.path.exists(self.overrides_file):
                os.replace(temp_file, self.overrides_file)
            else:
                os.rename(temp_file, self.overrides_file)
        except Exception as e:
            logger.error(f"[灾害预警] 保存会话差异配置失败: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    def _default_config_dict(self) -> dict[str, Any]:
        return copy.deepcopy(dict(self.default_config_ref))

    def list_target_sessions(self) -> list[str]:
        sessions = self.default_config_ref.get("target_sessions", [])
        if not isinstance(sessions, list):
            return []
        return [s for s in sessions if isinstance(s, str) and s]

    def list_all_known_sessions(self) -> list[str]:
        sessions = set(self.list_target_sessions())
        sessions.update(self._overrides.keys())
        return sorted(sessions)

    def get_override(self, umo: str) -> dict[str, Any]:
        override = self._overrides.get(umo, {})
        return copy.deepcopy(override)

    def set_override(self, umo: str, override_patch: dict[str, Any]) -> None:
        if not isinstance(override_patch, dict):
            raise ValueError("override_patch 必须是对象")

        patch = self._sanitize_patch(copy.deepcopy(override_patch))
        if patch:
            self._overrides[umo] = patch
        else:
            self._overrides.pop(umo, None)

        self._save()

    def delete_override(self, umo: str) -> None:
        self._overrides.pop(umo, None)
        self._save()

    def get_effective_config(self, umo: str) -> dict[str, Any]:
        default_conf = self._default_config_dict()
        override = self._overrides.get(umo, {})

        effective = self.deep_merge(default_conf, override)
        # 会话级推送总开关，默认继承为 True
        if "push_enabled" not in effective:
            effective["push_enabled"] = True
        return effective

    def update_session_from_effective(
        self, umo: str, effective_config: dict[str, Any]
    ) -> None:
        if not isinstance(effective_config, dict):
            raise ValueError("effective_config 必须是对象")

        default_conf = self._default_config_dict()
        patch = self.compute_diff(default_conf, effective_config)
        patch = self._sanitize_patch(patch)
        self.set_override(umo, patch)

    @classmethod
    def deep_merge(cls, base: Any, patch: Any) -> Any:
        """深合并：
        - dict: 递归合并
        - 其他类型(含 list): patch 全量覆盖 base
        """
        if isinstance(base, dict) and isinstance(patch, dict):
            merged = copy.deepcopy(base)
            for k, v in patch.items():
                if k in merged:
                    merged[k] = cls.deep_merge(merged[k], v)
                else:
                    merged[k] = copy.deepcopy(v)
            return merged

        return copy.deepcopy(patch)

    @classmethod
    def compute_diff(cls, default_obj: Any, target_obj: Any) -> Any:
        """计算 target 相对 default 的差异补丁。"""
        if isinstance(default_obj, dict) and isinstance(target_obj, dict):
            result: dict[str, Any] = {}
            for key, value in target_obj.items():
                if key not in default_obj:
                    result[key] = copy.deepcopy(value)
                    continue

                diff_val = cls.compute_diff(default_obj[key], value)
                if diff_val is not None:
                    result[key] = diff_val

            return result if result else None

        # list / scalar: 不相同则直接覆盖
        if default_obj != target_obj:
            return copy.deepcopy(target_obj)

        return None

    def _sanitize_patch(self, patch: Any, depth: int = 0) -> Any:
        """清洗 patch：
        - 顶层仅保留白名单键
        - 递归移除空 dict
        """
        if patch is None:
            return None

        if not isinstance(patch, dict):
            return patch

        sanitized: dict[str, Any] = {}
        for key, val in patch.items():
            if depth == 0 and key not in self.ALLOWED_ROOT_KEYS:
                continue
            child = self._sanitize_patch(val, depth + 1)
            if isinstance(child, dict) and not child:
                continue
            if child is not None:
                sanitized[key] = child

        return sanitized
