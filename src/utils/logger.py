"""日志工具模块。

提供分级日志、文件轮转（10MB×5）、控制台彩色输出。
日志位置：logs/aircoding.log
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


# ANSI 颜色码（控制台彩色输出）
class _ColorCodes:
    """ANSI 颜色码常量。"""
    DEBUG = "\033[36m"     # 青色
    INFO = "\033[32m"      # 绿色
    WARNING = "\033[33m"   # 黄色
    ERROR = "\033[31m"     # 红色
    CRITICAL = "\033[35m"  # 紫色
    RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    """带颜色输出的日志格式化器。"""

    _COLOR_MAP = {
        logging.DEBUG: _ColorCodes.DEBUG,
        logging.INFO: _ColorCodes.INFO,
        logging.WARNING: _ColorCodes.WARNING,
        logging.ERROR: _ColorCodes.ERROR,
        logging.CRITICAL: _ColorCodes.CRITICAL,
    }

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录，添加颜色前缀。"""
        color = self._COLOR_MAP.get(record.levelno, _ColorCodes.RESET)
        record.levelname = f"{color}{record.levelname:<7}{_ColorCodes.RESET}"
        return super().format(record)


def _resolve_log_dir() -> Path:
    """解析日志目录路径。"""
    # 尝试使用用户APPDATA目录，否则回退到项目目录
    appdata = os.environ.get("APPDATA")
    if appdata:
        log_dir = Path(appdata) / "AirCoding" / "logs"
    else:
        log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logger(
    name: str = "AirCoding",
    level: int = logging.DEBUG,
    console: bool = True,
) -> logging.Logger:
    """初始化并返回配置好的日志器。

    Args:
        name: 日志器名称。
        level: 日志级别（默认DEBUG）。
        console: 是否启用控制台输出（默认True）。

    Returns:
        配置好的 logging.Logger 实例。
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # 避免重复添加handler
    if logger.handlers:
        return logger

    log_format = "[%(asctime)s] [%(levelname)s] [%(threadName)s] [%(name)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(log_format, datefmt=date_format)

    # 文件handler（轮转：10MB×5）
    log_dir = _resolve_log_dir()
    log_file = log_dir / "aircoding.log"
    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 控制台handler（彩色输出）
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        color_formatter = _ColorFormatter(log_format, datefmt=date_format)
        console_handler.setFormatter(color_formatter)
        logger.addHandler(console_handler)

    return logger


def get_logger(module_name: str = "AirCoding") -> logging.Logger:
    """获取子模块日志器。

    Args:
        module_name: 模块名称，作为日志器子名称。

    Returns:
        logging.Logger 实例。
    """
    return logging.getLogger(f"AirCoding.{module_name}")


# 模块级默认日志器
logger = setup_logger()
