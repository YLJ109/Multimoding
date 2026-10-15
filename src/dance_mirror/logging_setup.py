"""Central logging configuration."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def configure_logging(log_dir: Path, *, verbose: bool = False) -> None:
    """Configure console and rotating-file logging once."""
    log_dir.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        return

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(level)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "dance_mirror.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    root.addHandler(console)
    root.addHandler(file_handler)
