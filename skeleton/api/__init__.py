"""REST API surface — FastAPI routers, server bootstrap, and middleware."""

from .routes import router
from .server import AppState, bootstrap, get_state, lifespan

__all__ = ["router", "AppState", "bootstrap", "get_state", "lifespan"]
