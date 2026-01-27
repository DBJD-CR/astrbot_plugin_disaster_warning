import os


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
                # 简单解析 YAML，避免引入 yaml 依赖
                for line in f:
                    if line.strip().startswith("version:"):
                        return line.split(":", 1)[1].strip()
    except Exception:
        pass

    return "unknown"
