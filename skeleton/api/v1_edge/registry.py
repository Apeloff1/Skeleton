"""Gateway route registry: /api/v1 routes bound to auth policy, quota class and schema."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

V1_PREFIX = "/api/v1"
_PARAM = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
AUTH_MODES = ("public", "api_key", "session", "any")


@dataclass(frozen=True)
class RouteSpec:
    method: str
    path: str  # relative to /api/v1, e.g. "/projects/{pid}"
    auth: str = "any"
    scopes: FrozenSet[str] = frozenset()
    quota_class: str = "default"
    idempotent_writes: bool = False
    schema: Optional[Dict[str, Any]] = None
    owner: str = "middleware"

    def __post_init__(self):
        if self.auth not in AUTH_MODES:
            raise ValueError(f"unknown auth mode {self.auth!r}")
        if not self.path.startswith("/"):
            raise ValueError("route path must start with '/'")
        object.__setattr__(self, "method", self.method.upper())
        object.__setattr__(self, "scopes", frozenset(self.scopes))

    @property
    def full_path(self) -> str:
        return V1_PREFIX + self.path


@dataclass
class _Compiled:
    spec: RouteSpec
    regex: "re.Pattern[str]"
    static_len: int


class RouteRegistry:
    """Ordered registry; most specific (longest static) match wins."""

    def __init__(self, default_auth: str = "any"):
        if default_auth not in AUTH_MODES:
            raise ValueError(default_auth)
        self.default_auth = default_auth
        self._routes: List[_Compiled] = []
        self._keys: set = set()

    def register(self, spec: RouteSpec) -> RouteSpec:
        key = (spec.method, spec.path)
        if key in self._keys:
            raise ValueError(f"duplicate route {spec.method} {spec.path}")
        pattern = "^" + _PARAM.sub(r"(?P<\1>[^/]+)", re.escape(spec.full_path).replace(r"\{", "{").replace(r"\}", "}")) + "$"
        static_len = len(_PARAM.sub("", spec.path))
        self._routes.append(_Compiled(spec, re.compile(pattern), static_len))
        self._routes.sort(key=lambda c: -c.static_len)
        self._keys.add(key)
        return spec

    def match(self, method: str, path: str) -> Tuple[Optional[RouteSpec], Dict[str, str], bool]:
        """Return (spec, params, path_known). path_known lets callers emit 405 vs 404."""
        method = method.upper()
        known = False
        for c in self._routes:
            m = c.regex.match(path)
            if not m:
                continue
            known = True
            if c.spec.method == method or (method == "HEAD" and c.spec.method == "GET"):
                return c.spec, m.groupdict(), True
        return None, {}, known

    def allowed_methods(self, path: str) -> List[str]:
        return sorted({c.spec.method for c in self._routes if c.regex.match(path)})

    def routes(self) -> List[RouteSpec]:
        return [c.spec for c in self._routes]

    def card(self) -> Dict[str, Any]:
        by_auth: Dict[str, int] = {}
        for c in self._routes:
            by_auth[c.spec.auth] = by_auth.get(c.spec.auth, 0) + 1
        return {"kind": "api-v1-route-registry", "routes": len(self._routes), "by_auth": by_auth}
