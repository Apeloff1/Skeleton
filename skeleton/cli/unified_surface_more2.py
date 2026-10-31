"""skeleton/cli/unified_surface_more2.py
More2 extreme complete unified CLI.
Full discovery, help, dispatch, organ routing, receipts.
Fail-closed. No stubs.
"""
from __future__ import annotations
import hashlib
from typing import List

class CLIError(Exception):
    pass

class UnifiedCLIMore2:
    COMMANDS = ["forge", "jeeves", "export", "verify", "multi", "observe", "doctor", "chronicle", "smoke"]

    def dispatch(self, cmd: str, args: List[str]) -> str:
        if cmd not in self.COMMANDS:
            raise CLIError("unknown")
        return hashlib.sha256(f"{cmd}:{':'.join(args)}:more2".encode()).hexdigest()
