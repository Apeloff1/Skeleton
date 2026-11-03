"""Launch scale Game 0481.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

ID = "game_launch_scale_0481"

def describe() -> Dict[str, Any]:
    return {"id": ID, "kind": "game", "launch": True, "scattered": True}

def reason(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx = context or {}
    threat = float(ctx.get("threat", 0.4))
    health = float(ctx.get("health", 1.0))
    action = "retreat" if health < 0.25 else ("engage" if threat > 0.65 else "observe")
    return {"ok": True, "id": ID, "action": action, "confidence": 0.78 + (481 % 12) * 0.01}

def operate(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"ok": True, "id": ID, "result": "launch_op", "size": len(payload or {})}
