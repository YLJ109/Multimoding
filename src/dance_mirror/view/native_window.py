"""Native Windows window chrome helpers for Fluent frameless windows."""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

from PyQt6.QtWidgets import QWidget

LOGGER = logging.getLogger(__name__)

_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_DONOTROUND = 1
_DWMWCP_ROUND = 2


def apply_native_window_corners(window: QWidget, *, rounded: bool) -> bool:
    """Apply a DWM corner preference without relying on a Qt stylesheet.

    FluentWindow deliberately uses a frameless native window. Disabling Mica
    removes its system backdrop, but Windows also needs an explicit corner
    preference for that custom frame. This helper keeps the native shadow and
    clips the complete window, including QWebEngineView content.
    """
    if sys.platform != "win32":
        return False
    try:
        if sys.getwindowsversion().build < 22000:
            return False
        hwnd = int(window.winId())
        preference = _DWMWCP_ROUND if rounded else _DWMWCP_DONOTROUND
        value = ctypes.c_int(preference)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(_DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        return int(result) == 0
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        LOGGER.debug("native window corner preference is unavailable", exc_info=True)
        return False
