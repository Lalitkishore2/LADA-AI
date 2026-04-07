"""Console stream encoding helpers for cross-platform startup safety."""

from __future__ import annotations

import sys
from typing import Any


def _try_reconfigure_stream(stream: Any) -> bool:
    """Attempt to set UTF-8 encoding on a text stream.

    Returns True when reconfiguration succeeds.
    """
    if stream is None:
        return False

    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return False

    try:
        reconfigure(encoding="utf-8", errors="replace")
        return True
    except Exception:
        return False


def configure_console_utf8(stdout: Any | None = None, stderr: Any | None = None) -> int:
    """Best-effort UTF-8 setup for console streams.

    Returns the number of streams successfully reconfigured.
    """
    out_stream = sys.stdout if stdout is None else stdout
    err_stream = sys.stderr if stderr is None else stderr

    changed = 0
    for stream in (out_stream, err_stream):
        if _try_reconfigure_stream(stream):
            changed += 1
    return changed
