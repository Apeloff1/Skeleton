"""API versioning — version negotiation and deprecation lifecycle.

Serves multiple API versions side by side with request negotiation
(header or path based), sunset dates, deprecation warnings injected
into responses, and usage tracking per version so retirement
decisions are data-driven. Blocks requests to versions past sunset.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


DAY_NS = 86_400_000_000_000


@dataclass
class APIVersion:
    version: str
    handler: Callable[[Dict[str, Any]], Any]
    deprecated: bool = False
    sunset_ns: Optional[int] = None
    calls: int = 0
    introduced_ns: int = 0


class APIVersioning:
    """Version negotiation with sunset enforcement."""

    def __init__(self):
        self._versions: Dict[str, Dict[str, APIVersion]] = {}

    def register(self, route: str, version: str,
                 handler: Callable[[Dict[str, Any]], Any]) -> APIVersion:
        v = APIVersion(version=version, handler=handler, introduced_ns=time.time_ns())
        self._versions.setdefault(route, {})[version] = v
        return v

    def deprecate(self, route: str, version: str, sunset_days: float = 90.0) -> bool:
        v = self._versions.get(route, {}).get(version)
        if not v:
            return False
        v.deprecated = True
        v.sunset_ns = time.time_ns() + int(sunset_days * DAY_NS)
        return True

    def negotiate(self, route: str, requested: Optional[str] = None) -> Optional[APIVersion]:
        versions = self._versions.get(route, {})
        if not versions:
            return None
        if requested and requested in versions:
            return versions[requested]
        candidates = sorted(versions.keys())
        return versions[candidates[-1]] if candidates else None

    def serve(self, route: str, payload: Dict[str, Any],
              requested: Optional[str] = None) -> Dict[str, Any]:
        v = self.negotiate(route, requested)
        if not v:
            return {"status": 404, "error": f"no handler for {route}"}
        if v.sunset_ns and time.time_ns() > v.sunset_ns:
            return {"status": 410, "error": f"version {v.version} sunset", "sunset": True}
        v.calls += 1
        try:
            body = v.handler(payload)
            status = 200
        except Exception as exc:  # noqa: BLE001
            return {"status": 500, "error": str(exc), "version": v.version}
        response: Dict[str, Any] = {"status": status, "body": body, "version": v.version}
        if v.deprecated:
            days_left = (v.sunset_ns - time.time_ns()) / DAY_NS if v.sunset_ns else None
            response["warning"] = f"version {v.version} deprecated" + (f", sunsets in {int(days_left)}d" if days_left is not None else "")
        return response

    def usage(self, route: Optional[str] = None) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for r, versions in self._versions.items():
            if route and r != route:
                continue
            out[r] = {v.version: {"calls": v.calls, "deprecated": v.deprecated,
                                  "sunset_ns": v.sunset_ns} for v in versions.values()}
        return out

    def retirement_candidates(self, min_share: float = 0.05) -> List[str]:
        candidates = []
        for r, versions in self._versions.items():
            total = sum(v.calls for v in versions.values())
            if total == 0:
                continue
            for v in versions.values():
                if v.deprecated and v.calls / total < min_share:
                    candidates.append(f"{r}@{v.version}")
        return candidates

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "api-versioning-card",
            "routes": len(self._versions),
            "versions": sum(len(v) for v in self._versions.values()),
            "deprecated": sum(1 for vs in self._versions.values() for v in vs.values() if v.deprecated),
            "retirement_candidates": self.retirement_candidates(),
        }
