"""Deep consumer surfaces readiness."""
from __future__ import annotations
from typing import Dict, Any

def surfaces_deep(cli_ok: bool, session_ok: bool, config_ok: bool) -> Dict[str, Any]:
    if not (cli_ok and session_ok and config_ok):
        return {"ok": False, "ready": False, "reason": "surfaces_failed"}
    return {"ok": True, "ready": True, "reason": "ok"}
