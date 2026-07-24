from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "codebase" / "ERIC-Gesture-Lab"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_legacy():
    original_argv = sys.argv
    try:
        sys.argv = [sys.argv[0], "--self-test"]
        return load_module(
            "legacy_motion_studio",
            LAB / "eric_motion_studio.py",
        )
    finally:
        sys.argv = original_argv


def load_viewer():
    return load_module(
        "legacy_motion_studio_viewer",
        LAB / "eric_motion_studio_viewer.py",
    )
