"""Command-line interface for ERIC Motion Studio."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from eric_motion_studio import __version__
from eric_motion_studio.application import run_application
from eric_motion_studio.config import Settings
from eric_motion_studio.diagnostics import (
    audit_all_commands,
    audit_command,
    run_self_test,
)
from eric_motion_studio.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eric-motion-studio",
        description="ERIC Motion Studio (simulation only)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--headless",
        action="store_true",
        help="validate startup without importing or opening the GUI",
    )
    modes.add_argument(
        "--self-test",
        action="store_true",
        help="run the active-package cutover regression suite",
    )
    modes.add_argument(
        "--audit-commands",
        action="store_true",
        help="compile and validate every supported gesture command",
    )
    modes.add_argument(
        "--audit-command",
        metavar="PROMPT",
        help="compile and validate one gesture command",
    )
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--export-dir", type=Path)
    parser.add_argument("--log-path", type=Path)
    parser.add_argument("--runtime-state-path", type=Path)
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="INFO",
    )
    parser.add_argument(
        "--no-console-log",
        action="store_true",
        help="write structured logs only to the rotating log file",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    settings = Settings.load(args)
    if args.audit_command is not None:
        return 0 if audit_command(args.audit_command, stream=sys.stdout) else 1
    if args.audit_commands:
        return 0 if audit_all_commands(stream=sys.stdout) else 1
    if args.self_test:
        return 0 if run_self_test(settings, stream=sys.stdout) else 1

    settings.prepare_mutable_directories()
    logger = configure_logging(
        settings.log_path,
        args.log_level,
        console=not args.no_console_log,
    )
    logger.info("startup", extra={"context": settings.as_log_context()})
    return run_application(settings, headless=args.headless)
