"""Bounded structured logging for ERIC Motion Studio."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


DEFAULT_MAX_LOG_BYTES = 1_000_000
DEFAULT_BACKUP_COUNT = 3


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload["context"] = context
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True)


def configure_logging(
    log_path: Path,
    level: str = "INFO",
    *,
    console: bool = True,
) -> logging.Logger:
    """Configure isolated, rotating application logs."""

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger("eric_motion_studio")
    logger.setLevel(numeric_level)
    logger.propagate = False

    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()

    formatter = JsonFormatter()
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=DEFAULT_MAX_LOG_BYTES,
        backupCount=DEFAULT_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
