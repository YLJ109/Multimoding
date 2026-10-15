"""Tests for deterministic worker registration and shutdown."""

from __future__ import annotations

from dataclasses import dataclass

from dance_mirror.workers.registry import WorkerRegistry


@dataclass
class _FakeThread:
    running: bool = False

    def isRunning(self) -> bool:  # noqa: N802 - Qt API shape
        return self.running


@dataclass
class _FakeController:
    thread: _FakeThread
    stops: list[int]

    def stop(self, wait_ms: int = 3000) -> None:
        self.stops.append(wait_ms)
        self.thread.running = False


def test_registry_stops_critical_worker_first() -> None:
    registry = WorkerRegistry()
    background = _FakeController(_FakeThread(), [])
    camera = _FakeController(_FakeThread(), [])
    registry.register("background", background, timeout_ms=1000)  # type: ignore[arg-type]
    registry.register(  # type: ignore[arg-type]
        "camera",
        camera,
        timeout_ms=5000,
        critical=True,
    )
    assert registry.stop_all() == ()
    assert camera.stops == [5000]
    assert background.stops == [1000]


def test_registry_reports_worker_that_does_not_stop() -> None:
    registry = WorkerRegistry()
    controller = _FakeController(_FakeThread(running=True), [])

    def stop(wait_ms: int = 3000) -> None:
        controller.stops.append(wait_ms)

    controller.stop = stop  # type: ignore[method-assign]
    registry.register("stuck", controller, timeout_ms=1)  # type: ignore[arg-type]
    assert registry.stop_all() == ("stuck",)
