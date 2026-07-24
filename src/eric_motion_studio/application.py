"""Application composition root."""

from __future__ import annotations

import logging

from eric_motion_studio.config import Settings


def run_application(settings: Settings, *, headless: bool = False) -> int:
    logger = logging.getLogger("eric_motion_studio")
    if headless:
        logger.info("headless_startup_ok", extra={"context": settings.as_log_context()})
        return 0

    from eric_motion_studio.ui import run_gui

    return run_gui(settings)
