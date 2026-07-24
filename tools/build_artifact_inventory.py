#!/usr/bin/env python3
"""Build the Phase 0 repository artifact inventory."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "artifact-inventory.tsv"
EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
PHASE_ZERO_PATHS = {
    ".gitignore",
    "TODOS.md",
    "docs/artifact-review.md",
    "docs/phase-0-baseline.md",
    "tests/fixtures/command-audit-markers.txt",
    "tests/fixtures/self-test-markers.txt",
    "tests/legacy_support.py",
    "tests/test_legacy_characterization.py",
    "tests/test_legacy_cli.py",
    "tools/build_artifact_inventory.py",
}


def git_paths(*arguments: str) -> set[str]:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return set(completed.stdout.splitlines())


def purpose(path: str) -> str:
    name = Path(path).name
    suffix = Path(path).suffix.lower()
    if path.startswith("tests/"):
        return "regression test or fixture"
    if path.startswith("docs/") or name in {"PLAN.md", "TODOS.md", "AGENTS.md"}:
        return "project documentation"
    if name == "eric_motion_studio.py":
        return "authoritative legacy application"
    if name == "eric_motion_studio_viewer.py":
        return "legacy viewer application"
    if name.endswith(".backup"):
        return "legacy source backup"
    if "live_pose" in name:
        return "generated viewer runtime state"
    if "before-" in name:
        return "environment repair diagnostic inventory"
    if name in {"right_arm_test.py", "talking_test.py"}:
        return "ad hoc visual experiment"
    if path.startswith("codebase/ERIC-Gesture-Lab/command_audit_reports/"):
        return "generated command audit report"
    if suffix == ".png":
        return "image or UI capture"
    if suffix == ".json":
        return "motion, gesture, or runtime data"
    if suffix in {".stl", ".dae", ".obj"}:
        return "robot model mesh"
    if suffix == ".xml":
        return "MuJoCo model definition"
    if suffix == ".py":
        return "Python source"
    if suffix in {".md", ".txt"}:
        return "documentation or text record"
    return "project support artifact"


def decision(path: str, tracked: set[str]) -> str:
    name = Path(path).name
    if path.startswith("codebase/ERIC-Gesture-Lab/command_audit_reports/"):
        if path in tracked:
            return "keep as regression baseline"
        return "remove candidate; preserved pending owner approval"
    if "live_pose" in name:
        return "archive/remove candidate; preserved pending owner approval"
    if path in PHASE_ZERO_PATHS or path == "PLAN.md" or path in tracked:
        return "keep"
    return "archive candidate; preserved pending owner approval"


def main() -> None:
    tracked = git_paths("ls-files")
    modified = git_paths("diff", "--name-only") | git_paths(
        "diff",
        "--cached",
        "--name-only",
    )
    rows = []
    for artifact in sorted(ROOT.rglob("*")):
        if not artifact.is_file() or artifact == OUTPUT:
            continue
        relative = artifact.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        path = relative.as_posix()
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if path in PHASE_ZERO_PATHS:
            owner = "project (Phase 0)"
        elif path in modified or path not in tracked:
            owner = "user working tree"
        else:
            owner = "project (tracked)"
        rows.append(
            (
                path,
                digest,
                owner,
                purpose(path),
                decision(path, tracked),
            )
        )

    header = ("path", "sha256", "owner", "purpose", "decision")
    lines = ["\t".join(header), *("\t".join(row) for row in rows)]
    OUTPUT.write_text("\n".join(lines) + "\n")
    print(f"WROTE {OUTPUT.relative_to(ROOT)} ({len(rows)} artifacts)")


if __name__ == "__main__":
    main()
