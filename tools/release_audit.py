#!/usr/bin/env python3
"""Verify the active tree is ready for a relocatable initial release."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']$', re.MULTILINE)
FORBIDDEN_ACTIVE_NAMES = {"eric_motion_studio.py", "eric_motion_studio_viewer.py"}


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--", "."],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        line for line in result.stdout.splitlines() if line and not line.startswith("codebase/")
    ]


def _violations() -> list[str]:
    violations: list[str] = []
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    package_version = VERSION_PATTERN.search(
        (ROOT / "src/eric_motion_studio/__init__.py").read_text(encoding="utf-8")
    )
    if package_version is None or package_version.group(1) != project["version"]:
        violations.append("package and pyproject versions differ")
    scripts = project.get("scripts", {})
    if set(scripts) != {"eric-motion-studio", "eric-motion-studio-viewer"}:
        violations.append("exactly two supported console scripts must be declared")

    for path in _tracked_files():
        name = Path(path).name
        if name in FORBIDDEN_ACTIVE_NAMES:
            violations.append(f"legacy duplicate in active tree: {path}")
        if name.endswith((".pyc", ".pyo")) or "/__pycache__/" in path:
            violations.append(f"generated artifact is tracked: {path}")

    source_root = ROOT / "src/eric_motion_studio"
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and ("codebase/" in node.value or "ERIC-Gesture-Lab" in node.value)
            ):
                violations.append(f"active source references legacy tree: {path}")
    return violations


def main() -> int:
    violations = _violations()
    if violations:
        for violation in violations:
            print(f"RELEASE_AUDIT_FAILED: {violation}")
        return 1
    print("RELEASE_VERSION_AUDIT_OK")
    print("RELEASE_ENTRY_POINT_AUDIT_OK")
    print("RELEASE_ACTIVE_TREE_AUDIT_OK")
    print("RELEASE_AUDIT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
