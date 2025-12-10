import logging
import logging.handlers
from datetime import datetime
from pathlib import Path

from core.utils.config import config


def get_logger(logger_name: str = 'app', file_name: str = None):
    LOG_DIR = Path("logs")
    LOG_DIR.mkdir(exist_ok=True)
    FILE_NAME_LOG_DIR = Path(f'logs/{file_name}')
    FILE_NAME_LOG_DIR.mkdir(exist_ok=True)

    start_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if not file_name:
        LOG_FILE = LOG_DIR / f"run_{start_time}.log"
    else:
        LOG_FILE = LOG_DIR / file_name / f"{file_name}_run_{start_time}.log"

    FILE_FORMAT = logging.Formatter(
        fmt=(
            "%(asctime)s | "
            "%(levelname)-8s | "
            "%(process)-6d | "
            "%(threadName)-8s | "
            "%(name)-30s | "
            "%(funcName)-25s | "
            "%(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    CONSOLE_FORMAT = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)

    logger.handlers.clear()

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(FILE_FORMAT)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(CONSOLE_FORMAT)
    logger.addHandler(console_handler)

    return logging.getLogger(logger_name)