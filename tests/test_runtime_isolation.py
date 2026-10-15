"""Runtime isolation contracts for optional MediaPipe imports."""

from __future__ import annotations

import site
import sys
from pathlib import Path

from pytest import MonkeyPatch

from dance_mirror.runtime import isolate_mediapipe_runtime


def test_mediapipe_runtime_removes_user_site_path(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    user_site = tmp_path / "user-site"
    user_site.mkdir()
    monkeypatch.setattr(site, "getusersitepackages", lambda: str(user_site))
    original_path = list(sys.path)
    sys.path.insert(0, str(user_site))
    try:
        removed = isolate_mediapipe_runtime()
        assert str(user_site) in removed
        assert str(user_site) not in sys.path
        assert any(Path(entry).resolve() == Path(sys.prefix).resolve() for entry in sys.path)
    finally:
        sys.path[:] = original_path
