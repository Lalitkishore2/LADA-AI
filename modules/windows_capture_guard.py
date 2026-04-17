"""
Windows capture guard utilities.

Provides a thin wrapper around SetWindowDisplayAffinity so screenshot paths can
exclude sensitive foreground windows from capture when possible.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional


WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011


@dataclass
class CaptureGuardResult:
    success: bool
    message: str
    hwnd: Optional[int] = None
    affinity: Optional[int] = None


def _is_windows() -> bool:
    return os.name == "nt"


def apply_foreground_capture_guard(
    preferred_affinity: int = WDA_EXCLUDEFROMCAPTURE,
) -> CaptureGuardResult:
    """
    Attempt to mark the current foreground window as excluded from capture.
    Falls back from WDA_EXCLUDEFROMCAPTURE to WDA_MONITOR when needed.
    """
    if not _is_windows():
        return CaptureGuardResult(False, "Capture guard is Windows-only")

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return CaptureGuardResult(False, "No foreground window found")

    attempted = [preferred_affinity]
    if preferred_affinity != WDA_MONITOR:
        attempted.append(WDA_MONITOR)

    for affinity in attempted:
        ok = bool(user32.SetWindowDisplayAffinity(hwnd, affinity))
        if ok:
            mode = (
                "WDA_EXCLUDEFROMCAPTURE"
                if affinity == WDA_EXCLUDEFROMCAPTURE
                else "WDA_MONITOR"
            )
            return CaptureGuardResult(
                True,
                f"Applied capture guard ({mode})",
                hwnd=int(hwnd),
                affinity=affinity,
            )

    return CaptureGuardResult(
        False,
        "SetWindowDisplayAffinity failed for both exclusion modes",
        hwnd=int(hwnd),
    )
