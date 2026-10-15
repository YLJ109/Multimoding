"""Worker ownership and deterministic shutdown for the Qt application."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from dance_mirror.workers.base import WorkerThreadController


@dataclass(slots=True)
class WorkerRegistration:
    """One controller plus the metadata needed for safe shutdown."""

    name: str
    controller: WorkerThreadController
    timeout_ms: int = 3000
    callback: Callable[[], None] | None = None
    critical: bool = False


@dataclass(slots=True)
class WorkerRegistry:
    """Own all long-running controllers behind named registrations."""

    _registrations: dict[str, WorkerRegistration] = field(default_factory=dict)

    def register(
        self,
        name: str,
        controller: WorkerThreadController,
        *,
        timeout_ms: int = 3000,
        callback: Callable[[], None] | None = None,
        critical: bool = False,
    ) -> WorkerRegistration:
        if not name:
            raise ValueError("worker registration name is required")
        self.unregister(name)
        registration = WorkerRegistration(
            name=name,
            controller=controller,
            timeout_ms=max(0, int(timeout_ms)),
            callback=callback,
            critical=bool(critical),
        )
        self._registrations[name] = registration
        return registration

    def get(self, name: str) -> WorkerThreadController | None:
        registration = self._registrations.get(name)
        return registration.controller if registration is not None else None

    def unregister(self, name: str) -> WorkerThreadController | None:
        registration = self._registrations.pop(name, None)
        return registration.controller if registration is not None else None

    def names(self) -> tuple[str, ...]:
        return tuple(self._registrations)

    def pop(
        self,
        name: str,
        *,
        wait_ms: int = 0,
    ) -> WorkerThreadController | None:
        registration = self._registrations.pop(name, None)
        if registration is None:
            return None
        registration.controller.stop(wait_ms=wait_ms)
        if registration.callback is not None:
            registration.callback()
        return registration.controller

    def stop_all(self) -> tuple[str, ...]:
        """Stop critical workers first, then return names that missed a deadline."""
        registrations = tuple(self._registrations.values())
        ordered = sorted(
            registrations,
            key=lambda item: (not item.critical, -item.timeout_ms),
        )
        wait_failures: list[str] = []
        for registration in ordered:
            controller = registration.controller
            controller.stop(wait_ms=registration.timeout_ms)
            if controller.thread.isRunning():
                wait_failures.append(registration.name)
        self._registrations.clear()
        return tuple(wait_failures)

    def clear_callbacks(self) -> None:
        self._registrations.clear()
