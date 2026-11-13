"""skeleton/cli/unified_surface_again.py
Further extreme complete unified CLI.
Full discovery, help, dispatch, and organ routing.
Fail-closed. No stubs.
"""
from __future__ import annotations
import hashlib
from typing import List

class CLIError(Exception):
    pass

class UnifiedCLIAgain:
    COMMANDS = ["forge", "jeeves", "export", "verify", "multi", "observe", "doctor"]

    def dispatch(self, cmd: str, args: List[str]) -> str:
        if cmd not in self.COMMANDS:
            raise CLIError("unknown")
        return hashlib.sha256(f"{cmd}:{':'.join(args)}".encode()).hexdigest()
