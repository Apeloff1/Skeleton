"""Versioned /api/v1 edge: pure-ASGI layers composed around the existing app.

Extend-only: nothing here edits ``skeleton/api/server.py``. Callers wrap an
ASGI app with :func:`build_v1_edge` (see ``edge.py``).
"""
from .envelope import EdgeError, error_body
from .registry import RouteRegistry, RouteSpec
from .edge import EdgeConfig, build_v1_edge

__all__ = ["EdgeError", "error_body", "RouteRegistry", "RouteSpec", "EdgeConfig", "build_v1_edge"]
