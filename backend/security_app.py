"""Production/development ASGI entrypoint with outer request-header bounds.

``server.app`` owns the FastAPI application and its existing middleware stack.
This wrapper is intentionally the Uvicorn entrypoint so header cardinality and
aggregate bytes are checked before any application middleware consumes request
metadata. Lifespan and non-HTTP scopes pass through unchanged.
"""

from __future__ import annotations

from middleware.header_bounds import HeaderBoundMiddleware
from server import app as _backend_app

# Construct after importing server so backend/.env has been loaded and explicit
# process-environment values retain their normal precedence.
app = HeaderBoundMiddleware(_backend_app)

__all__ = ["app"]
