import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Union


class FlushStreamHandler(logging.StreamHandler):
    """强制 flush 的控制台 Handler，解决 PowerShell 输出缓冲问题。
    在 Windows GBK 控制台下，Unicode 字符可能无法编码，使用 replace 模式避免崩溃。"""

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                encoding = getattr(stream, "encoding", "utf-8") or "utf-8"
                safe = msg.encode(encoding, errors="replace").decode(
                    encoding, errors="replace"
                )
                stream.write(safe + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


class FsyncFileHandler(logging.FileHandler):
    """落盘到磁盘的 FileHandler——每条 record 之后 fsync，
    避免进程被外部 kill 时最后几行只停在 OS 缓冲区里丢失。"""

    def emit(self, record):
        super().emit(record)
        try:
            if self.stream is not None:
                self.stream.flush()
                os.fsync(self.stream.fileno())
        except (OSError, ValueError):
            # ValueError if stream已关闭；OSError 罕见但不应让日志拖垮主流程
            pass


class LogFormatter(logging.Formatter):
    """统一的日志格式化器"""

    def __init__(self, datefmt: str = "%Y-%m-%d %H:%M:%S"):
        # 父类需要 fmt 参数，但我们在 format() 中完全自定义，所以传个空的
        super().__init__(fmt="", datefmt=datefmt)

    def format(self, record):
        # 确保 message 是字符串
        record.message = (
            record.getMessage() if hasattr(record, "getMessage") else str(record.msg)
        )

        # 格式化时间
        record.asctime = self.formatTime(record, self.datefmt)

        # 组装最终输出 - 简洁格式：时间 [级别] 名称: 消息
        return (
            f"{record.asctime} [{record.levelname:>8}] {record.name}: {record.message}"
        )


def setup_logger(
    name: str = "hn_techpulse",
    log_file: Optional[str] = None,
    debug: bool = False,
    level: Optional[Union[str, int]] = None,
) -> logging.Logger:
    """
    配置并获取 logger 实例。

    Args:
        name: logger 名称，建议使用 __name__
        log_file: 日志文件路径（可选）
        debug: 是否启用 DEBUG 模式
        level: 日志级别（字符串或 logging 常量）

    Returns:
        配置好的 logger 实例
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 设置日志级别
    if level is None:
        level = logging.DEBUG if debug else logging.INFO
    elif isinstance(level, str):
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        level = level_map.get(level.upper(), logging.INFO)

    logger.setLevel(level)
    logger.propagate = False  # 不向上传播

    # 使用统一的 formatter
    formatter = LogFormatter("%Y-%m-%d %H:%M:%S")

    # 控制台输出
    console_handler = FlushStreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    # 文件输出（如果有指定）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = FsyncFileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)  # 文件总是记录 DEBUG
        logger.addHandler(file_handler)

    return logger


def get_log_file_path(date_str: Optional[str] = None) -> str:
    """获取日志文件路径"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    return f"logs/app_{date_str}.log"
