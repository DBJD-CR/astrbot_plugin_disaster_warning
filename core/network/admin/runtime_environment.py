"""
Web 管理端运行环境探测工具。
负责提供与宿主运行环境相关的纯函数，避免 admin 路由与 WebServer 宿主之间形成循环导入。
"""

from __future__ import annotations

import os


def is_running_in_docker() -> bool:
    """
    检测是否在 Docker 容器中运行。
    使用多种方法进行检测以提高准确性。
    """
    # 最常见的 Docker 标记文件，命中即可快速返回。
    if os.path.exists("/.dockerenv"):
        return True

    try:
        # 兼容 Linux 容器 / Kubernetes 场景，通过 cgroup 进一步识别容器化运行环境。
        with open("/proc/self/cgroup") as f:
            content = f.read()
            if "/docker/" in content or "/kubepods/" in content:
                return True
    except (FileNotFoundError, PermissionError):
        pass

    if os.environ.get("DOCKER_CONTAINER") == "true":
        return True

    return False
