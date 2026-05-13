"""
原始日志文件仓储。
负责日志文本落盘、文件大小检查与轮转，避免 MessageLogger 持有底层文件 IO 细节。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from astrbot.api import logger


class LogFileStore:
    """原始日志文件仓储。"""

    def __init__(
        self,
        log_file_path: Path,
        *,
        max_size_mb: int = 50,
        max_files: int = 5,
    ):
        # 存储器维护主日志路径、轮转上限和文件级写锁。
        self.log_file_path = Path(log_file_path)
        self.max_size_mb = max_size_mb
        self.max_files = max_files
        self._file_lock = threading.Lock()

    def write(self, content: str) -> bool:
        """写入日志内容，并在必要时触发轮转。"""
        # 文件级写锁保证多线程/多调用点场景下不会把多条日志交叉写坏。
        with self._file_lock:
            try:
                self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_file_path, "a", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()

                self._check_log_rotation()
                return True
            except OSError as io_err:
                logger.error(f"[灾害预警] 写入日志文件失败 (可能磁盘已满): {io_err}")
                return False

    def _check_log_rotation(self):
        """检查日志文件大小并进行轮转。"""
        try:
            if not self.log_file_path.exists():
                return

            file_size_mb = self.log_file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > self.max_size_mb:
                self.rotate()
        except Exception as e:
            logger.error(f"[灾害预警] 日志轮转检查失败: {e}")

    def rotate(self):
        """轮转日志文件，使用 lock 文件防止并发轮转。"""
        lock_file = self.log_file_path.with_suffix(".lock")
        if lock_file.exists():
            try:
                if time.time() - lock_file.stat().st_mtime > 10:
                    lock_file.unlink()
                else:
                    logger.debug("[灾害预警] 日志轮转正在进行中，跳过")
                    return
            except Exception:
                return

        try:
            lock_file.touch()

            for i in range(self.max_files - 1, 0, -1):
                old_file = self.log_file_path.with_suffix(f".log.{i}")
                new_file = self.log_file_path.with_suffix(f".log.{i + 1}")

                if old_file.exists():
                    if new_file.exists():
                        try:
                            new_file.unlink()
                        except OSError:
                            pass
                    try:
                        old_file.rename(new_file)
                    except OSError:
                        pass

            if self.log_file_path.exists():
                backup_file = self.log_file_path.with_suffix(".log.1")
                if backup_file.exists():
                    try:
                        backup_file.unlink()
                    except OSError:
                        pass
                try:
                    self.log_file_path.rename(backup_file)
                    logger.info(f"[灾害预警] 日志文件已轮转，备份文件: {backup_file}")
                    # 轮转完成后立即重建空主日志文件，避免摘要读取或下一次写入命中“主文件暂不存在”的窗口。
                    self.log_file_path.touch(exist_ok=True)
                except OSError as e:
                    logger.error(f"[灾害预警] 重命名主日志文件失败: {e}")

        except Exception as e:
            logger.error(f"[灾害预警] 日志轮转失败: {e}")
        finally:
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except Exception:
                    pass
