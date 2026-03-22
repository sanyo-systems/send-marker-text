import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logger():
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    log_path = os.path.abspath("logs/recorder_log.txt")
    for existing_handler in logger.handlers:
        if (
            isinstance(existing_handler, RotatingFileHandler)
            and getattr(existing_handler, "baseFilename", None) == log_path
        ):
            return

    handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
