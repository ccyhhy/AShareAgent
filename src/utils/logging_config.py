"""
日志配置模块

提供统一的日志记录配置和管理功能
"""
import logging
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

def setup_logger(name: str, log_dir: Optional[str] = None) -> logging.Logger:
    """配置共享的日志记录器，包含控制台和文件处理器。"""
    logging.getLogger().setLevel(logging.DEBUG)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)

    # 修复：将参数名称统一，正确引用传入的参数
    log_directory = log_dir
    if log_directory is None:
        log_directory = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "logs",
        )

    os.makedirs(log_directory, exist_ok=True)
    log_file = os.path.join(log_directory, f"{name}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# ASCII-safe markers避免Windows GBK终端上的UnicodeEncodeError。
SUCCESS_ICON = "[OK]"
ERROR_ICON = "[ERR]"
WAIT_ICON = "[WAIT]"