"""
LADA Sandbox Executor — OS-aware execution isolation diagnostics.

Provides read-only diagnostics and policy guidance for sandbox posture:
- Windows: subprocess isolation (restricted shell policy)
- macOS: Seatbelt readiness probe
- Linux/WSL: bubblewrap readiness probe
"""

from __future__ import annotations

import os
import shutil
from typing import Tuple

from core.executors import BaseExecutor


class SandboxExecutor(BaseExecutor):
    """Handles sandbox posture and isolation diagnostics commands."""

    def try_handle(self, cmd: str) -> Tuple[bool, str]:
        if not any(x in cmd for x in ["sandbox", "isolation", "seatbelt", "bubblewrap", "bwrap"]):
            return False, ""

        if any(x in cmd for x in ["status", "check", "diagnostic", "policy"]):
            return True, self._sandbox_status()

        return False, ""

    def _sandbox_status(self) -> str:
        if os.name == "nt":
            return (
                "Sandbox status (Windows): using subprocess isolation via CodeSandbox. "
                "OS-native Seatbelt/bubblewrap are not applicable on Windows hosts."
            )

        if os.uname().sysname == "Darwin":  # type: ignore[attr-defined]
            seatbelt_ok = shutil.which("sandbox-exec") is not None
            return (
                "Sandbox status (macOS): "
                + ("seatbelt available." if seatbelt_ok else "seatbelt tool not found.")
            )

        bwrap_ok = shutil.which("bwrap") is not None
        return (
            "Sandbox status (Linux/WSL): "
            + ("bubblewrap available." if bwrap_ok else "bubblewrap not found.")
        )
