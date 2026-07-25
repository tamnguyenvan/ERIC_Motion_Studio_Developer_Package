"""Non-destructive migration of legacy flat user-data files."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from eric_motion_studio.infrastructure.formats import (
    ANIMATION_SCHEMA,
    GESTURE_SCHEMA_VERSION,
    POSE_SCHEMA,
)


@dataclass(frozen=True, slots=True)
class MigratedUserFile:
    source: Path
    destination: Path


def migrate_legacy_user_files(
    data_dir: Path,
    motions_dir: Path,
    poses_dir: Path,
    compiled_dir: Path,
) -> tuple[MigratedUserFile, ...]:
    """Copy recognized flat JSON files into typed folders without deleting originals."""
    migrated: list[MigratedUserFile] = []
    for source in sorted(Path(data_dir).glob("*.json")):
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("schema") == ANIMATION_SCHEMA:
            destination = Path(motions_dir) / source.name
        elif payload.get("schema") == POSE_SCHEMA:
            destination = Path(poses_dir) / source.name
        elif payload.get("schema_version") == GESTURE_SCHEMA_VERSION and payload.get("gesture_id"):
            destination = Path(compiled_dir) / source.name
        else:
            continue
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        migrated.append(MigratedUserFile(source, destination))
    return tuple(migrated)
