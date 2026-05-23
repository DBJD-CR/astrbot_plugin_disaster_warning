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
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.star import StarTools


class SessionConfigManager:
    """会话差异配置管理器。

    负责维护“全局默认配置 + 会话覆写补丁”的存储模式，
    提供差异计算、白名单清洗、兼容迁移与生效配置合并能力。
    """

    OVERRIDES_FILE = "session_overrides.json"
    LEGACY_FULL_CONFIGS_FILE = "session_configs.json"

    # 可覆写字段白名单（顶层键）。
    # 这里只允许保留会话级局部配置，避免误把全局运行参数写入单个会话补丁。
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
        """初始化会话差异配置管理器并加载已保存的差异补丁。"""
        self.default_config_ref = default_config_ref
        self.storage_dir = StarTools.get_data_dir("astrbot_plugin_disaster_warning")
        self.overrides_file = os.path.join(self.storage_dir, self.OVERRIDES_FILE)
        self.legacy_full_configs_file = os.path.join(
            self.storage_dir, self.LEGACY_FULL_CONFIGS_FILE
        )
        self.schema = self._load_schema()

        self._overrides: dict[str, dict[str, Any]] = {}
        self._legacy_full_configs: dict[str, dict[str, Any]] = {}
        self._load()

    def _ensure_storage_dir(self) -> None:
        """确保会话配置存储目录存在。"""
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    def _load(self) -> None:
        """加载 override 文件，并执行一次兼容迁移。"""
        self._ensure_storage_dir()
        self._legacy_full_configs = self._load_legacy_full_configs()

        if os.path.exists(self.overrides_file):
            # 优先读取新的差异补丁文件；读取成功后仍继续尝试回填旧字段兼容数据。
            try:
                with open(self.overrides_file, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._overrides = {
                            str(k): v for k, v in data.items() if isinstance(v, dict)
                        }
                        self._restore_legacy_weather_fields_from_full_configs()
                        return
            except Exception as e:
                logger.warning(f"[灾害预警] 读取会话差异配置失败，将使用空配置: {e}")

        self._overrides = {}

        # 新格式不存在时，再尝试兼容旧版“按会话保存完整配置”的历史文件。
        # 迁移完成后会统一落为差异补丁，减少后续默认配置变化带来的冗余存储。
        if self._legacy_full_configs:
            try:
                migrated = 0
                for umo, full_conf in self._legacy_full_configs.items():
                    if not isinstance(full_conf, dict):
                        continue
                    patch = self.compute_diff(self._default_config_dict(), full_conf)
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
        """以临时文件替换方式保存差异补丁，尽量降低写入中断风险。"""
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

    def _load_legacy_full_configs(self) -> dict[str, dict[str, Any]]:
        """加载旧版全量配置字典。"""
        if not os.path.exists(self.legacy_full_configs_file):
            return {}
        try:
            with open(self.legacy_full_configs_file, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return {str(k): v for k, v in data.items() if isinstance(v, dict)}
        except Exception as e:
            logger.warning(f"[灾害预警] 读取旧会话完整配置失败: {e}")
            return {}

    def _default_config_dict(self) -> dict[str, Any]:
        """获取当前全局默认配置的深拷贝。"""
        return copy.deepcopy(dict(self.default_config_ref))

    def _extract_legacy_weather_filter_patch(
        self, full_conf: dict[str, Any]
    ) -> dict[str, Any] | None:
        """提取旧版气象过滤器省份补丁。"""
        weather_config = full_conf.get("weather_config")
        if not isinstance(weather_config, dict):
            return None
        weather_filter = weather_config.get("weather_filter")
        if not isinstance(weather_filter, dict):
            return None

        legacy_patch: dict[str, Any] = {}
        if isinstance(weather_filter.get("provinces"), list):
            legacy_patch["provinces"] = copy.deepcopy(weather_filter.get("provinces"))
        if isinstance(weather_filter.get("province"), str):
            legacy_patch["province"] = str(weather_filter.get("province"))

        if not legacy_patch:
            return None
        return {"weather_config": {"weather_filter": legacy_patch}}

    def _restore_legacy_weather_fields_from_full_configs(self) -> None:
        """从旧配置恢复气象预警过滤器省份兼容项。"""
        if not self._legacy_full_configs or not self._overrides:
            return

        changed = False
        for umo, override in list(self._overrides.items()):
            if not isinstance(override, dict):
                continue

            weather_config = override.get("weather_config")
            weather_filter = (
                weather_config.get("weather_filter")
                if isinstance(weather_config, dict)
                else None
            )
            has_legacy_weather = isinstance(weather_filter, dict) and (
                "provinces" in weather_filter or "province" in weather_filter
            )
            if has_legacy_weather:
                continue

            legacy_full_conf = self._legacy_full_configs.get(umo)
            if not isinstance(legacy_full_conf, dict):
                continue

            legacy_patch = self._extract_legacy_weather_filter_patch(legacy_full_conf)
            if not legacy_patch:
                continue

            self._overrides[umo] = self.deep_merge(override, legacy_patch)
            changed = True

        if changed:
            self._save()

    def _load_schema(self) -> dict[str, Any]:
        """加载当前插件配置 Schema，供会话 override 新写入裁剪使用。"""
        try:
            schema_path = Path(__file__).resolve().parents[2] / "_conf_schema.json"
            with open(schema_path, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(
                f"[灾害预警] 读取配置 Schema 失败，会话保存将退化为顶层白名单模式: {e}"
            )
            return {}

    @staticmethod
    def _is_legacy_weather_filter_key(key: str, value: Any) -> bool:
        """检查是否是遗留的气象过滤器字段。"""
        if key == "provinces" and isinstance(value, list):
            return True
        if key == "province" and isinstance(value, str):
            return True
        return False

    def _prune_to_schema(self, value: Any, schema_node: dict[str, Any] | None) -> Any:
        """按 schema 递归裁剪新提交的配置，仅阻止未来污染，不清理已存旧字段。"""
        if schema_node is None or not isinstance(schema_node, dict):
            return value

        field_type = schema_node.get("type")
        if field_type == "object":
            if not isinstance(value, dict):
                return None
            items = (
                schema_node.get("items")
                if isinstance(schema_node.get("items"), dict)
                else {}
            )
            result: dict[str, Any] = {}
            node_description = str(schema_node.get("description") or "")
            for key, child_value in value.items():
                child_schema = items.get(key)
                if not isinstance(child_schema, dict):
                    if (
                        node_description == "气象预警过滤器"
                        and self._is_legacy_weather_filter_key(key, child_value)
                    ):
                        result[key] = copy.deepcopy(child_value)
                    continue
                pruned = self._prune_to_schema(child_value, child_schema)
                if pruned is not None:
                    result[key] = pruned
            return result if result else None

        if isinstance(value, dict):
            return None
        return copy.deepcopy(value)

    def list_target_sessions(self) -> list[str]:
        """列出全局配置中声明的目标会话。"""
        sessions = self.default_config_ref.get("target_sessions", [])
        if not isinstance(sessions, list):
            return []
        return [s for s in sessions if isinstance(s, str) and s]

    def list_all_known_sessions(self) -> list[str]:
        """列出当前已知的全部会话标识。"""
        sessions = set(self.list_target_sessions())
        sessions.update(self._overrides.keys())
        return sorted(sessions)

    def get_override(self, umo: str) -> dict[str, Any]:
        """获取指定会话的差异补丁副本。"""
        override = self._overrides.get(umo, {})
        return copy.deepcopy(override)

    def set_override(self, umo: str, override_patch: dict[str, Any]) -> None:
        """设置指定会话的差异补丁。"""
        if not isinstance(override_patch, dict):
            raise ValueError("override_patch 必须是对象")

        current_override = self._overrides.get(umo, {})
        patch = self._sanitize_patch(
            copy.deepcopy(override_patch), preserve_legacy=current_override
        )
        if patch:
            self._overrides[umo] = patch
        else:
            self._overrides.pop(umo, None)

        self._save()

    def delete_override(self, umo: str) -> None:
        """删除指定会话的差异补丁。"""
        self._overrides.pop(umo, None)
        self._save()

    def get_effective_config(self, umo: str) -> dict[str, Any]:
        """获取指定会话最终生效的配置。"""
        default_conf = self._default_config_dict()
        override = self._overrides.get(umo, {})

        # 生效配置由“全局默认值 + 会话差异补丁”递归合并得到。
        effective = self.deep_merge(default_conf, override)
        # 会话级推送总开关，默认继承为 True
        if "push_enabled" not in effective:
            effective["push_enabled"] = True
        return effective

    def update_session_from_effective(
        self, umo: str, effective_config: dict[str, Any]
    ) -> None:
        """根据提交的生效配置反推并保存差异补丁。"""
        if not isinstance(effective_config, dict):
            raise ValueError("effective_config 必须是对象")

        default_conf = self._sanitize_patch(self._default_config_dict()) or {}
        session_effective = self._sanitize_patch(copy.deepcopy(effective_config)) or {}

        patch = self.compute_diff(default_conf, session_effective)
        patch = self._sanitize_patch(
            patch, preserve_legacy=self._overrides.get(umo, {})
        )
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
            # 仅保留与默认值不同的部分，得到最小差异补丁。
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

    def _sanitize_patch(
        self,
        patch: Any,
        depth: int = 0,
        preserve_legacy: Any = None,
    ) -> Any:
        """清洗 patch：
        - 顶层仅保留会话白名单键
        - 对 schema 内对象块递归裁剪新写入字段
        - 若旧 override 中已存在历史兼容字段，则原样保留，不做清空/重置
        - 递归移除空 dict
        """
        if patch is None:
            return None

        if not isinstance(patch, dict):
            return patch

        legacy_patch = preserve_legacy if isinstance(preserve_legacy, dict) else {}
        sanitized: dict[str, Any] = {}
        active_schema = self.schema if isinstance(self.schema, dict) else {}

        for key, val in patch.items():
            if depth == 0 and key not in self.ALLOWED_ROOT_KEYS:
                continue

            legacy_child = legacy_patch.get(key)
            schema_node = active_schema.get(key) if depth == 0 else None

            if (
                depth == 0
                and isinstance(schema_node, dict)
                and schema_node.get("type") == "object"
            ):
                child = self._prune_to_schema(val, schema_node)
                if isinstance(child, dict) and isinstance(legacy_child, dict):
                    merged_child = copy.deepcopy(legacy_child)
                    merged_child.update(child)
                    child = merged_child
            else:
                child = self._sanitize_patch(val, depth + 1, legacy_child)

            if isinstance(child, dict) and not child:
                if isinstance(legacy_child, dict) and legacy_child:
                    sanitized[key] = copy.deepcopy(legacy_child)
                continue
            if child is not None:
                sanitized[key] = child
            elif legacy_child is not None:
                sanitized[key] = copy.deepcopy(legacy_child)

        if depth == 0:
            for key, legacy_value in legacy_patch.items():
                if key in sanitized:
                    continue
                if key in self.ALLOWED_ROOT_KEYS:
                    sanitized[key] = copy.deepcopy(legacy_value)

        return sanitized
