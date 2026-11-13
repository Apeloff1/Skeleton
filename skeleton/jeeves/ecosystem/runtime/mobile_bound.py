"""Runtime adapter: mobile_bound.
"""
from __future__ import annotations
from typing import Any

ADAPTER = "mobile_bound"

def boot(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or {}
    if cfg.get("disabled"):
        return {"ok": False, "reason": "disabled", "adapter": ADAPTER}
    return {"ok": True, "adapter": ADAPTER, "ready": True, "config_keys": sorted(cfg.keys())}

def tick(state: dict[str, Any], dt: float = 1.0 / 60.0) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {"ok": False, "reason": "bad_state"}
    state = dict(state)
    state["dt"] = dt
    state["adapter"] = ADAPTER
    state["ticked"] = True
    return state

def export_manifest(files: list[dict[str, str]]) -> dict[str, Any]:
    if not files:
        return {"ok": False, "reason": "no_files"}
    return {"ok": True, "adapter": ADAPTER, "count": len(files), "paths": [f.get("path", "") for f in files]}
