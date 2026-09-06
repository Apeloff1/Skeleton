"""
Skeleton API Package

Exports:
- create_app: FastAPI application factory
- get_state: Server state accessor
- ServerState: Shared runtime state
- run_server: Uvicorn runner
"""

from skeleton.api.server import (
    ServerState,
    create_app,
    get_state,
    run_server,
)

__all__ = [
    "create_app",
    "get_state",
    "ServerState",
    "run_server",
]
