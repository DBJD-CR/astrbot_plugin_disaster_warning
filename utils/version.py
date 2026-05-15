"""
版本信息辅助工具。
负责读取插件版本与 AstrBot 版本，供状态展示、遥测上报等场景复用。
"""

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata as importlib_metadata
from pathlib import Path

# 优先使用标准库 tomllib；若运行环境较旧，则回退到 tomli。
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

import astrbot
from astrbot.api import logger


@dataclass(frozen=True)
class AstrBotVersionInfo:
    """AstrBot 版本探测结果。"""

    version: str
    source: str
    error: str | None = None


def get_plugin_version() -> str:
    """
    获取插件版本号

    通过读取插件根目录下的 metadata.yaml 文件获取版本信息。
    """
    try:
        # 获取当前文件所在目录的父目录作为插件根目录。
        current_dir = os.path.dirname(os.path.abspath(__file__))
        plugin_root = os.path.dirname(current_dir)
        metadata_path = os.path.join(plugin_root, "metadata.yaml")

        if os.path.exists(metadata_path):
            # metadata.yaml 中仅需读取版本字段，因此按行扫描即可满足需求。
            with open(metadata_path, encoding="utf-8") as f:
                # 这里使用轻量方式提取版本号，避免为了单个字段引入额外解析依赖。
                for line in f:
                    # 匹配 version 字段，并去除行尾注释。
                    match = re.match(r"^\s*version:\s*([^#\n]+)", line)
                    if match:
                        return match.group(1).strip()
        else:
            logger.debug(f"[灾害预警] metadata.yaml 未找到: {metadata_path}")
    except Exception as e:
        logger.error(f"[灾害预警] 获取插件版本失败: {e}")

    return "unknown"


def _build_unknown_version_info(
    default: str = "unknown", error: str = "all_methods_failed"
) -> AstrBotVersionInfo:
    """构造未知版本探测结果。"""
    return AstrBotVersionInfo(version=default, source="unknown", error=error)


def _get_astrbot_version_from_core_config() -> AstrBotVersionInfo | None:
    """优先从 AstrBot 运行时核心配置模块读取版本。"""
    module_candidates = (
        "astrbot.core.config",
        "astrbot.core.config.default",
    )

    for module_name in module_candidates:
        try:
            module = __import__(module_name, fromlist=["VERSION"])
            version = str(getattr(module, "VERSION", "")).strip()
            if version:
                return AstrBotVersionInfo(version=version, source="core_config")
        except Exception as exc:
            logger.debug(
                "[灾害预警] 从 %s 读取 AstrBot VERSION 失败: %s",
                module_name,
                exc,
            )

    return None


def _get_astrbot_version_from_distribution() -> AstrBotVersionInfo | None:
    """从 AstrBot 安装分发元数据读取版本。"""
    for dist_name in ("AstrBot", "astrbot"):
        try:
            version = str(importlib_metadata.version(dist_name)).strip()
            if version:
                return AstrBotVersionInfo(version=version, source="distribution")
        except importlib_metadata.PackageNotFoundError:
            logger.debug("[灾害预警] 未找到 AstrBot 分发元数据: %s", dist_name)
        except Exception as exc:
            logger.debug(
                "[灾害预警] 读取 AstrBot 分发元数据失败 (%s): %s",
                dist_name,
                exc,
            )

    return None


def _get_astrbot_version_from_cli_module() -> AstrBotVersionInfo | None:
    """从 AstrBot CLI 模块常量读取版本。"""
    try:
        from astrbot.cli import __version__ as cli_version

        version = str(cli_version).strip()
        if version:
            return AstrBotVersionInfo(version=version, source="cli_module")
        logger.debug("[灾害预警] astrbot.cli.__version__ 为空")
    except Exception as exc:
        logger.debug(f"[灾害预警] 导入 astrbot.cli.__version__ 失败: {exc}")

    return None


def _get_astrbot_version_from_pyproject(default: str = "unknown") -> AstrBotVersionInfo:
    """从 AstrBot 安装目录附近的 pyproject.toml 中兜底读取版本。"""
    try:
        # 从 astrbot 包路径定位 pyproject.toml。
        astrbot_path = Path(astrbot.__file__).resolve().parent.parent
        pyproject_path = astrbot_path / "pyproject.toml"

        if not pyproject_path.exists():
            logger.debug(
                f"[灾害预警] 无法读取 AstrBot 版本，pyproject.toml 不存在: {pyproject_path}"
            )
            return _build_unknown_version_info(default, "pyproject_missing")

        if tomllib is None:
            logger.warning(
                "[灾害预警] 未找到 tomllib 或 tomli 模块，无法解析 AstrBot 版本"
            )
            return _build_unknown_version_info(default, "tomllib_unavailable")

        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)

        project_version = str(data.get("project", {}).get("version", "")).strip()
        if project_version:
            return AstrBotVersionInfo(version=project_version, source="pyproject")

        poetry_version = str(
            data.get("tool", {}).get("poetry", {}).get("version", "")
        ).strip()
        if poetry_version:
            return AstrBotVersionInfo(version=poetry_version, source="pyproject")

        logger.debug(
            f"[灾害预警] pyproject.toml 中未找到可用的 AstrBot 版本字段: {pyproject_path}"
        )
        return _build_unknown_version_info(default, "pyproject_version_missing")

    except Exception as e:
        logger.debug(f"[灾害预警] 获取 AstrBot 版本时出错: {e}")
        return _build_unknown_version_info(default, "pyproject_parse_failed")


@lru_cache(maxsize=8)
def get_astrbot_version_info(default: str = "unknown") -> AstrBotVersionInfo:
    """获取带来源与错误码的 AstrBot 版本探测结果。"""
    for resolver in (
        _get_astrbot_version_from_core_config,
        _get_astrbot_version_from_distribution,
        _get_astrbot_version_from_cli_module,
    ):
        version_info = resolver()
        if version_info is not None:
            return version_info

    return _get_astrbot_version_from_pyproject(default)


def get_astrbot_version(default: str = "unknown") -> str:
    """获取 AstrBot 版本号字符串。"""
    return get_astrbot_version_info(default).version
