"""Typed application settings and path resolution."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

APP_SLUG = "eric-motion-studio"
ENV_PREFIX = "ERIC_MOTION_STUDIO_"
PACKAGE_ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = PACKAGE_ROOT / "resources"


class PathOverrides(Protocol):
    model_path: Path | None
    data_dir: Path | None
    export_dir: Path | None
    log_path: Path | None
    runtime_state_path: Path | None


def _absolute(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _environment_path(
    environment: Mapping[str, str],
    name: str,
    default: Path,
) -> Path:
    value = environment.get(f"{ENV_PREFIX}{name}")
    return _absolute(value) if value else default


def _user_data_root(environment: Mapping[str, str]) -> Path:
    if value := environment.get("XDG_DATA_HOME"):
        return _absolute(value) / APP_SLUG
    home = _absolute(environment.get("HOME", Path.home()))
    return home / ".local" / "share" / APP_SLUG


def _user_state_root(environment: Mapping[str, str]) -> Path:
    if value := environment.get("XDG_STATE_HOME"):
        return _absolute(value) / APP_SLUG
    home = _absolute(environment.get("HOME", Path.home()))
    return home / ".local" / "state" / APP_SLUG


def _runtime_root(environment: Mapping[str, str], state_root: Path) -> Path:
    if value := environment.get("XDG_RUNTIME_DIR"):
        return _absolute(value) / APP_SLUG
    return state_root / "run"


@dataclass(frozen=True, slots=True)
class Settings:
    """Resolved paths for one application process."""

    model_path: Path
    data_dir: Path
    export_dir: Path
    log_path: Path
    runtime_state_path: Path
    resource_root: Path = RESOURCE_ROOT

    @classmethod
    def load(
        cls,
        overrides: PathOverrides | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> Settings:
        env = os.environ if environment is None else environment
        default_data = _user_data_root(env)
        default_state = _user_state_root(env)
        default_runtime = _runtime_root(env, default_state)

        model_path = _environment_path(
            env,
            "MODEL_PATH",
            RESOURCE_ROOT / "models" / "g1" / "scene_29dof.xml",
        )
        data_dir = _environment_path(env, "DATA_DIR", default_data)
        log_path = _environment_path(
            env,
            "LOG_PATH",
            default_state / "logs" / "motion-studio.jsonl",
        )
        runtime_state_path = _environment_path(
            env,
            "RUNTIME_STATE_PATH",
            default_runtime / "live-pose.json",
        )

        if overrides is not None:
            model_path = _absolute(overrides.model_path or model_path)
            data_dir = _absolute(overrides.data_dir or data_dir)
            log_path = _absolute(overrides.log_path or log_path)
            runtime_state_path = _absolute(overrides.runtime_state_path or runtime_state_path)

        export_dir = _environment_path(env, "EXPORT_DIR", data_dir / "exports")
        if overrides is not None:
            export_dir = _absolute(overrides.export_dir or export_dir)

        return cls(
            model_path=model_path,
            data_dir=data_dir,
            export_dir=export_dir,
            log_path=log_path,
            runtime_state_path=runtime_state_path,
        )

    def prepare_mutable_directories(self) -> None:
        """Create mutable directories only when application startup requests it."""

        for directory in {
            self.data_dir,
            self.export_dir,
            self.log_path.parent,
            self.runtime_state_path.parent,
        }:
            directory.mkdir(parents=True, exist_ok=True)

    def as_log_context(self) -> dict[str, str]:
        return {
            "model_path": str(self.model_path),
            "data_dir": str(self.data_dir),
            "export_dir": str(self.export_dir),
            "log_path": str(self.log_path),
            "runtime_state_path": str(self.runtime_state_path),
        }
