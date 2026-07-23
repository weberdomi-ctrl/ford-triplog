"""
Ford Triplog

Thread-safe progress management for long-running tasks.

File: progress_manager.py
Version: 1.4.0
Date: 2026-07-23

Purpose:
- Track one long-running Ford Triplog task.
- Allow worker threads to publish progress safely.
- Allow Home Assistant flows and entities to read a serializable snapshot.
- Store successful completion and failure information.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from time import monotonic
from typing import Any


FILE_VERSION = "1.4.0"

STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_FINISHED = "finished"
STATE_FAILED = "failed"

_VALID_STATES = {
    STATE_IDLE,
    STATE_RUNNING,
    STATE_FINISHED,
    STATE_FAILED,
}


class ProgressManagerError(RuntimeError):
    """Raised when the progress manager receives invalid input."""


class ProgressManager:
    """Manage the state of one long-running Ford Triplog task."""

    def __init__(self) -> None:
        """Initialize an idle progress manager."""

        self._lock = RLock()
        self._started_monotonic: float | None = None
        self._finished_monotonic: float | None = None
        self._status = self._new_idle_status()

    @staticmethod
    def _utc_now() -> str:
        """Return the current UTC timestamp in ISO 8601 format."""

        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _new_idle_status() -> dict[str, Any]:
        """Return a fresh idle status dictionary."""

        return {
            "state": STATE_IDLE,
            "running": False,
            "finished": False,
            "success": None,
            "task": None,
            "title": None,
            "message": None,
            "step": 0,
            "total_steps": 0,
            "progress": 0,
            "started_utc": None,
            "finished_utc": None,
            "elapsed_seconds": 0.0,
            "result": None,
            "error": None,
        }

    @staticmethod
    def _validate_step_values(
        step: int,
        total_steps: int,
    ) -> None:
        """Validate step counters."""

        if total_steps < 1:
            raise ProgressManagerError(
                "total_steps must be at least 1."
            )

        if step < 0 or step > total_steps:
            raise ProgressManagerError(
                f"step must be between 0 and {total_steps}."
            )

    @staticmethod
    def _calculate_progress(
        step: int,
        total_steps: int,
        progress: int | float | None,
    ) -> int:
        """Return a validated integer progress percentage."""

        if progress is None:
            calculated = round((step / total_steps) * 100)
        else:
            calculated = round(float(progress))

        if calculated < 0 or calculated > 100:
            raise ProgressManagerError(
                "progress must be between 0 and 100."
            )

        return calculated

    def _update_elapsed_locked(self) -> None:
        """Refresh elapsed time while the manager lock is held."""

        if self._started_monotonic is None:
            self._status["elapsed_seconds"] = 0.0
            return

        end = (
            self._finished_monotonic
            if self._finished_monotonic is not None
            else monotonic()
        )
        self._status["elapsed_seconds"] = round(
            max(0.0, end - self._started_monotonic),
            1,
        )

    def start(
        self,
        *,
        task: str,
        title: str,
        total_steps: int,
        message: str | None = None,
    ) -> dict[str, Any]:
        """
        Start a new task and return its initial status.

        A running task cannot be silently replaced. The caller must finish,
        fail, or reset it first.
        """

        normalized_task = str(task).strip()
        normalized_title = str(title).strip()

        if not normalized_task:
            raise ProgressManagerError("task must not be empty.")

        if not normalized_title:
            raise ProgressManagerError("title must not be empty.")

        self._validate_step_values(0, total_steps)

        with self._lock:
            if self._status["state"] == STATE_RUNNING:
                raise ProgressManagerError(
                    f"Task '{self._status['task']}' is already running."
                )

            self._started_monotonic = monotonic()
            self._finished_monotonic = None
            self._status = {
                "state": STATE_RUNNING,
                "running": True,
                "finished": False,
                "success": None,
                "task": normalized_task,
                "title": normalized_title,
                "message": message,
                "step": 0,
                "total_steps": total_steps,
                "progress": 0,
                "started_utc": self._utc_now(),
                "finished_utc": None,
                "elapsed_seconds": 0.0,
                "result": None,
                "error": None,
            }
            return deepcopy(self._status)

    def update(
        self,
        *,
        step: int | None = None,
        total_steps: int | None = None,
        title: str | None = None,
        message: str | None = None,
        progress: int | float | None = None,
    ) -> dict[str, Any]:
        """Update the currently running task and return its status."""

        with self._lock:
            if self._status["state"] != STATE_RUNNING:
                raise ProgressManagerError(
                    "No task is currently running."
                )

            current_step = (
                self._status["step"]
                if step is None
                else int(step)
            )
            current_total = (
                self._status["total_steps"]
                if total_steps is None
                else int(total_steps)
            )

            self._validate_step_values(
                current_step,
                current_total,
            )

            if step is not None and current_step < self._status["step"]:
                raise ProgressManagerError(
                    "step must not move backwards."
                )

            if title is not None:
                normalized_title = str(title).strip()
                if not normalized_title:
                    raise ProgressManagerError(
                        "title must not be empty."
                    )
                self._status["title"] = normalized_title

            if message is not None:
                self._status["message"] = str(message)

            self._status["step"] = current_step
            self._status["total_steps"] = current_total
            self._status["progress"] = self._calculate_progress(
                current_step,
                current_total,
                progress,
            )
            self._update_elapsed_locked()

            return deepcopy(self._status)

    def finish(
        self,
        *,
        message: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Mark the current task as successfully finished."""

        with self._lock:
            if self._status["state"] != STATE_RUNNING:
                raise ProgressManagerError(
                    "No task is currently running."
                )

            self._finished_monotonic = monotonic()
            self._status.update(
                {
                    "state": STATE_FINISHED,
                    "running": False,
                    "finished": True,
                    "success": True,
                    "step": self._status["total_steps"],
                    "progress": 100,
                    "finished_utc": self._utc_now(),
                    "result": deepcopy(result),
                    "error": None,
                }
            )

            if message is not None:
                self._status["message"] = str(message)

            self._update_elapsed_locked()
            return deepcopy(self._status)

    def fail(
        self,
        error: Exception | str,
        *,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Mark the current task as failed."""

        with self._lock:
            if self._status["state"] != STATE_RUNNING:
                raise ProgressManagerError(
                    "No task is currently running."
                )

            self._finished_monotonic = monotonic()
            error_text = str(error).strip() or error.__class__.__name__

            self._status.update(
                {
                    "state": STATE_FAILED,
                    "running": False,
                    "finished": True,
                    "success": False,
                    "finished_utc": self._utc_now(),
                    "error": error_text,
                    "result": None,
                }
            )

            if message is not None:
                self._status["message"] = str(message)
            elif not self._status["message"]:
                self._status["message"] = error_text

            self._update_elapsed_locked()
            return deepcopy(self._status)

    def reset(self) -> dict[str, Any]:
        """Reset the manager to idle when no task is running."""

        with self._lock:
            if self._status["state"] == STATE_RUNNING:
                raise ProgressManagerError(
                    "A running task cannot be reset."
                )

            self._started_monotonic = None
            self._finished_monotonic = None
            self._status = self._new_idle_status()
            return deepcopy(self._status)

    def get_status(self) -> dict[str, Any]:
        """Return a thread-safe, serializable status snapshot."""

        with self._lock:
            self._update_elapsed_locked()
            return deepcopy(self._status)

    @property
    def is_running(self) -> bool:
        """Return True when a task is currently running."""

        with self._lock:
            return self._status["state"] == STATE_RUNNING
