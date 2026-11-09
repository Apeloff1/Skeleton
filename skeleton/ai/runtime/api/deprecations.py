"""API deprecation registry — retiring endpoints without breaking clients.

Routes can be flagged deprecated with a sunset date; the registry returns
the header values the route appends so adopters see the warning and a
target migration date.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from skeleton.kernel.errors import KernelError


class DeprecationError(KernelError):
    code = "API.DEPRECATION"


@dataclass(frozen=True)
class Deprecation:
    method: str
    path: str
    sunset: str  # ISO date, e.g. "2026-12-31"
    replacement: Optional[str] = None


class DeprecationRegistry:
    """Static register consulted by routers/app."""

    def __init__(self) -> None:
        self._entries: Dict[Tuple[str, str], Deprecation] = {}

    def register(
        self, method: str, path: str, *, sunset: str, replacement: Optional[str] = None
    ) -> Deprecation:
        dep = Deprecation(
            method=method.upper(), path=path, sunset=sunset, replacement=replacement
        )
        self._entries[(dep.method, dep.path)] = dep
        return dep

    def lookup(self, method: str, path: str) -> Optional[Deprecation]:
        return self._entries.get((method.upper(), path))

    def headers(self, method: str, path: str) -> Dict[str, str]:
        dep = self.lookup(method, path)
        if dep is None:
            return {}
        headers = {"Sunset": dep.sunset, "Deprecation": "true"}
        if dep.replacement:
            headers["Link"] = f'<{dep.replacement}>; rel="successor-version"'
        return headers

    def all(self) -> Tuple[Deprecation, ...]:
        return tuple(self._entries.values())
