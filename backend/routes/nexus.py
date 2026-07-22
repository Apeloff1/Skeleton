"""
routes/nexus.py — Knowledge Nexus integration (vendored knowledge_nexus/).

The vendored package uses bare top-level imports (``from engines.X``) and ships
dirs (utils/, security/, testing/) that would SHADOW the backend's own modules
if placed on sys.path permanently. So every access runs inside an isolation
guard that snapshots ``sys.path`` + ``sys.modules``, adds the nexus root only for
the duration of the call, then restores state and evicts any nexus-loaded modules.
This lets us use the Nexus without ever corrupting the live backend imports.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/nexus", tags=["knowledge-nexus"])

_NX = str(Path(__file__).resolve().parent.parent / "knowledge_nexus")


def _isolated(fn):
    """Run ``fn`` with the nexus root on sys.path, then fully restore state."""
    saved_path = list(sys.path)
    saved_mods = set(sys.modules)
    sys.path.insert(0, _NX)
    try:
        return fn()
    finally:
        sys.path[:] = saved_path
        for name in list(sys.modules):
            if name in saved_mods:
                continue
            mod = sys.modules.get(name)
            f = getattr(mod, "__file__", "") or ""
            if f.startswith(_NX):
                del sys.modules[name]


def _capabilities() -> dict:
    root = Path(_NX)
    caps: dict[str, list[str]] = {}
    if root.exists():
        for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "__pycache__"):
            caps[d.name] = sorted(f.stem for f in d.glob("*.py"))
    return caps


@router.get("/status")
async def nexus_status():
    """Vendored Knowledge Nexus inventory — always safe (no live import)."""
    caps = _capabilities()
    return {"vendored": bool(caps), "domains": list(caps),
            "module_count": sum(len(v) for v in caps.values()), "capabilities": caps}


@router.get("/orchestrator")
async def nexus_orchestrator():
    """Instantiate the NexusOrchestrator inside the isolation guard and report readiness."""
    def _load():
        from orchestration.nexus_orchestration_layer import NexusOrchestrator
        o = NexusOrchestrator()
        return {"ok": True, "orchestrator": "NexusOrchestrator",
                "methods": [m for m in dir(o) if not m.startswith("_") and callable(getattr(o, m))]}
    try:
        return _isolated(_load)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}, status_code=207)


class NexusEvent(BaseModel):
    event: str
    source: str = "gameforge"


@router.post("/event")
async def nexus_event(body: NexusEvent):
    """Route an important event through the Nexus orchestrator (isolation-guarded)."""
    def _run():
        from orchestration.nexus_orchestration_layer import NexusOrchestrator
        return NexusOrchestrator().process_important_event(body.event, body.source)
    try:
        result = _isolated(_run)
        return {"ok": True, "result": result}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}, status_code=207)
