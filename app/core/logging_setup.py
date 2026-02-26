# ============================================================
# 文件说明: logging_setup.py - 应用日志配置
# ============================================================

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from config import get_settings


# ------------------------------------------------------------
# 1. setup_logging() - 初始化日志配置
# ------------------------------------------------------------
def setup_logging() -> str:
    """初始化控制台日志与 error 文件日志

    Returns:
        str: error 日志文件路径
    """
    settings = get_settings()

    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / settings.log_file_name

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    console_handler.setFormatter(formatter)

    error_file_handler = TimedRotatingFileHandler(
        filename=str(log_file),
        when="midnight",
        interval=1,
        backupCount=settings.log_retention_days,
        encoding="utf-8",
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(error_file_handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        logger.propagate = True

    return str(log_file)
