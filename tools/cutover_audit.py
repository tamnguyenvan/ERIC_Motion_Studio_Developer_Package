#!/usr/bin/env python3
"""Verify that the supported application tree is relocatable and self-contained."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src" / "eric_motion_studio"
LEGACY_MARKERS = ("codebase/", "ERIC-Gesture-Lab", "eric_motion_studio.py")
ABSOLUTE_PATH = re.compile(r"^(?:/[A-Za-z0-9_.-]|[A-Za-z]:[\\/])")


def _source_violations() -> list[str]:
    violations: list[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        for marker in LEGACY_MARKERS:
            if marker in source:
                violations.append(f"{relative}: legacy marker {marker!r}")
        tree = ast.parse(source, filename=str(relative))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and ABSOLUTE_PATH.match(node.value)
            ):
                violations.append(f"{relative}:{node.lineno}: absolute path {node.value!r}")
    return violations


def _resource_violations() -> list[str]:
    model_root = SOURCE_ROOT / "resources" / "models" / "g1"
    model_xml = model_root / "g1_29dof.xml"
    scene_xml = model_root / "scene_29dof.xml"
    violations: list[str] = []
    if not model_xml.is_file() or not scene_xml.is_file():
        return ["packaged G1 model XML is incomplete"]
    mesh_names = re.findall(
        r'<mesh\s+[^>]*file="([^"]+)"',
        model_xml.read_text(encoding="utf-8"),
    )
    missing_meshes = [name for name in mesh_names if not (model_root / "meshes" / name).is_file()]
    if missing_meshes:
        violations.append(f"missing model meshes: {','.join(missing_meshes)}")
    for relative in (
        "gesture_definitions/builtins.json",
        "gesture_lexicon/builtins.json",
        "gesture_stages/builtin_stages.json",
    ):
        if not (SOURCE_ROOT / "resources" / relative).is_file():
            violations.append(f"missing canonical motion source: {relative}")
    for resource_type in ("animations", "gestures"):
        count = len(tuple((SOURCE_ROOT / "resources" / resource_type).glob("*.json")))
        if count:
            violations.append(f"redundant packaged {resource_type} remain active: {count}")
    return violations


def _launcher_violations() -> list[str]:
    launcher = ROOT / "launchers" / "macos" / "ERIC Motion Studio.command"
    if not launcher.is_file():
        return ["supported macOS launcher is missing"]
    source = launcher.read_text(encoding="utf-8")
    violations = []
    if "eric-motion-studio" not in source:
        violations.append("macOS launcher does not invoke the package entry point")
    for marker in LEGACY_MARKERS:
        if marker in source:
            violations.append(f"macOS launcher contains legacy marker {marker!r}")
    if not launcher.stat().st_mode & 0o111:
        violations.append("macOS launcher is not executable")
    return violations


def main() -> int:
    violations = _source_violations() + _resource_violations() + _launcher_violations()
    if violations:
        for violation in violations:
            print(f"CUTOVER_AUDIT_FAILED: {violation}")
        return 1
    print("CUTOVER_RESOURCE_AUDIT_OK")
    print("CUTOVER_PATH_AUDIT_OK")
    print("CUTOVER_LAUNCHER_AUDIT_OK")
    print("CUTOVER_AUDIT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
