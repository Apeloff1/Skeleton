"""HTTP mount for Hive 1.0 (``skeleton.automation.hive``) behind the systems edge.

Hive has no HTTP surface of its own. This router exposes its read-only
contract and self-checks at ``/api/v1/hive``; every route is meant to sit
behind :class:`~skeleton.gate_plane.systems.edge.RecoveredSystemsMiddleware`
(``/capabilities`` is the only anonymous probe in the default catalog).

``POST /walk`` builds a fresh, request-scoped :class:`Hive` from a bounded
list of payloads and walks it, so no caller can grow shared state.
"""

# No ``from __future__ import annotations``: FastAPI resolves the locally imported
# ``Request`` annotation on the nested route handlers at definition time.

from typing import Any, Dict, List

MAX_WALK_PAYLOADS = 32
MAX_PAYLOAD_CHARS = 256


class HiveRequestError(ValueError):
    pass


def run_walk(payloads: Any) -> Dict[str, Any]:
    from skeleton.automation.hive.kernel import Hive

    if not isinstance(payloads, list) or not payloads:
        raise HiveRequestError("payloads must be a non-empty list")
    if len(payloads) > MAX_WALK_PAYLOADS:
        raise HiveRequestError(f"at most {MAX_WALK_PAYLOADS} payloads")
    clean: List[str] = []
    for p in payloads:
        if not isinstance(p, str) or not p or len(p) > MAX_PAYLOAD_CHARS:
            raise HiveRequestError(f"each payload must be a 1..{MAX_PAYLOAD_CHARS} char string")
        clean.append(p)
    h = Hive()
    root = h.mint(clean[0])["root"]
    node = root
    for p in clean[1:]:
        node = h.link(node, p)["child"]
    return h.walk(root)


def build_hive_router(*, prefix: str = "/api/v1/hive") -> Any:
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse

    from skeleton.automation.hive.capabilities import capabilities
    from skeleton.automation.hive.engine import HiveEngine
    from skeleton.automation.hive.verify import run_all

    router = APIRouter(prefix=prefix, tags=["hive-edge"])

    @router.get("/capabilities")
    def hive_capabilities() -> Dict[str, Any]:
        return capabilities()

    @router.get("/verify")
    def hive_verify() -> JSONResponse:
        report = run_all()
        return JSONResponse(report, status_code=200 if report.get("ok") == 1 else 503)

    @router.post("/snapshot")
    def hive_snapshot() -> Dict[str, Any]:
        return HiveEngine().snapshot()

    @router.post("/walk")
    async def hive_walk(request: Request) -> JSONResponse:
        import json

        try:
            data = json.loads((await request.body()).decode("utf-8") or "null")
        except (UnicodeDecodeError, ValueError):
            return JSONResponse({"error": "invalid_json"}, status_code=400)
        if not isinstance(data, dict):
            return JSONResponse({"error": "invalid_request", "reason": "body must be an object"}, status_code=400)
        try:
            return JSONResponse(run_walk(data.get("payloads")))
        except HiveRequestError as exc:
            return JSONResponse({"error": "invalid_request", "reason": str(exc)}, status_code=400)

    return router


__all__ = ["HiveRequestError", "MAX_PAYLOAD_CHARS", "MAX_WALK_PAYLOADS", "build_hive_router", "run_walk"]
