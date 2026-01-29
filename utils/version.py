import os
import re
import tomllib
from pathlib import Path

import astrbot
from astrbot.api import logger


def get_plugin_version() -> str:
    """
    获取插件版本号

    通过读取插件根目录下的 metadata.yaml 文件获取版本信息。
    """
    try:
        # 获取当前文件 (utils/version.py) 所在目录的父目录作为插件根目录
        # 即: astrbot_plugin_disaster_warning/
        current_dir = os.path.dirname(os.path.abspath(__file__))
        plugin_root = os.path.dirname(current_dir)
        metadata_path = os.path.join(plugin_root, "metadata.yaml")

        if os.path.exists(metadata_path):
            with open(metadata_path, encoding="utf-8") as f:
                # 轻量级 YAML 解析，使用正则提取版本号并去除注释
                for line in f:
                    # 匹配 "version: <值>" 并去除行尾注释
                    match = re.match(r'^\s*version:\s*([^#\n]+)', line)
                    if match:
                        return match.group(1).strip()
    except Exception:
        pass

    return "unknown"


def get_astrbot_version() -> str:
    """
    从 pyproject.toml 获取 AstrBot 版本号
    
    Returns:
        str: AstrBot 版本号,获取失败则返回 "unknown"
    """
    try:
        # 从 astrbot 包路径定位 pyproject.toml
        astrbot_path = Path(astrbot.__file__).parent.parent
        pyproject_path = astrbot_path / 'pyproject.toml'
        
        if pyproject_path.exists():
            with open(pyproject_path, 'rb') as f:
                data = tomllib.load(f)
                version_str = data.get('project', {}).get('version', 'unknown')
                if version_str != 'unknown':
                    logger.debug(f"[灾害预警] ✅ 从 pyproject.toml 获取到 AstrBot 版本: {version_str}")
                    return version_str
        
        logger.debug(f"[灾害预警] ⚠️  无法读取 AstrBot 版本,pyproject.toml 不存在: {pyproject_path}")
        return "unknown"
        
    except Exception as e:
        logger.debug(f"[灾害预警] ❌ 获取 AstrBot 版本时出错: {e}")
        return "unknown"
