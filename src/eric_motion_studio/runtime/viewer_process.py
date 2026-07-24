"""External viewer supervision and playback output."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from eric_motion_studio.domain import JointValues, TrajectoryFrame
from eric_motion_studio.runtime.mujoco_adapter import SimulationMode
from eric_motion_studio.runtime.viewer_state import ViewerStateStore


class ProcessHandle(Protocol):
    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


ProcessLauncher = Callable[[Sequence[str]], ProcessHandle]


class ViewerProcessStatus(StrEnum):
    STOPPED = "stopped"
    RUNNING = "running"
    CRASHED = "crashed"


class ViewerProcessError(RuntimeError):
    pass


def _launch(command: Sequence[str]) -> ProcessHandle:
    return subprocess.Popen(list(command))


@dataclass(frozen=True, slots=True)
class ViewerLaunchSettings:
    model_path: Path
    state_path: Path
    python_executable: Path = Path(sys.executable)
    mode: SimulationMode = SimulationMode.AUTHORING_KINEMATIC

    def command(self) -> tuple[str, ...]:
        return (
            str(self.python_executable),
            "-m",
            "eric_motion_studio.viewer",
            "--model-path",
            str(self.model_path),
            "--state-file",
            str(self.state_path),
            "--simulation-mode",
            self.mode.value,
        )


class ViewerProcessManager:
    def __init__(
        self,
        settings: ViewerLaunchSettings,
        *,
        launcher: ProcessLauncher = _launch,
        shutdown_timeout: float = 2.0,
    ) -> None:
        self.settings = settings
        self.launcher = launcher
        self.shutdown_timeout = shutdown_timeout
        self._process: ProcessHandle | None = None
        self._last_exit_code: int | None = None

    @property
    def status(self) -> ViewerProcessStatus:
        if self._process is None:
            return ViewerProcessStatus.STOPPED
        exit_code = self._process.poll()
        if exit_code is None:
            return ViewerProcessStatus.RUNNING
        self._last_exit_code = exit_code
        return ViewerProcessStatus.CRASHED if exit_code != 0 else ViewerProcessStatus.STOPPED

    @property
    def last_exit_code(self) -> int | None:
        _ = self.status
        return self._last_exit_code

    def start(self) -> int:
        status = self.status
        if status is ViewerProcessStatus.RUNNING:
            assert self._process is not None
            return self._process.pid
        if status is ViewerProcessStatus.CRASHED:
            raise ViewerProcessError(f"Viewer exited unexpectedly with code {self._last_exit_code}")
        try:
            self._process = self.launcher(self.settings.command())
        except OSError as error:
            raise ViewerProcessError(f"Could not start viewer: {error}") from error
        if self._process.poll() is not None:
            self._last_exit_code = self._process.poll()
            raise ViewerProcessError(
                f"Viewer exited during startup with code {self._last_exit_code}"
            )
        return self._process.pid

    def assert_running(self) -> None:
        status = self.status
        if status is ViewerProcessStatus.CRASHED:
            raise ViewerProcessError(f"Viewer crashed with code {self._last_exit_code}")
        if status is not ViewerProcessStatus.RUNNING:
            raise ViewerProcessError("Viewer is not running")

    def stop(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        exit_code = process.poll()
        if exit_code is not None:
            self._last_exit_code = exit_code
            return
        process.terminate()
        try:
            self._last_exit_code = process.wait(timeout=self.shutdown_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            self._last_exit_code = process.wait(timeout=self.shutdown_timeout)


class ViewerPlaybackOutput:
    """Writes playback frames atomically and lazily starts the viewer."""

    def __init__(
        self,
        state_store: ViewerStateStore,
        process: ViewerProcessManager,
    ) -> None:
        self.state_store = state_store
        self.process = process

    def apply_frame(self, frame: TrajectoryFrame) -> None:
        if self.process.status is ViewerProcessStatus.STOPPED:
            self.state_store.write(frame.joints)
            self.process.start()
            return
        self.process.assert_running()
        self.state_store.write(frame.joints)

    def reset(self) -> None:
        neutral = JointValues.neutral(self.state_store.profile)
        self.state_store.write(neutral)

    def close(self) -> None:
        self.process.stop()
