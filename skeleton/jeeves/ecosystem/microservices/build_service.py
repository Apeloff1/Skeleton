"""Microservice: build_service.
In-process facade. No network. Fail-closed on bad input.
"""
from __future__ import annotations
from typing import Any

SERVICE = "build_service"

def handle(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict) or not request.get("op"):
        return {"ok": False, "service": SERVICE, "reason": "bad_request"}
    op = str(request["op"])[:64]
    payload = request.get("payload") or {}
    if not isinstance(payload, dict):
        return {"ok": False, "service": SERVICE, "reason": "bad_payload"}
    return {"ok": True, "service": SERVICE, "op": op, "payload_keys": sorted(payload.keys())}

def health() -> dict[str, Any]:
    return {"ok": True, "service": SERVICE, "ready": True}
