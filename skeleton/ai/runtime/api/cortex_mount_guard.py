"""Runtime re-export of the canonical cortex mount guard.

The implementation lives in ``skeleton.api.cortex_mount_guard``. This module
re-exports it so the runtime tree cannot keep a second, older startup check.
"""

from skeleton.api.cortex_mount_guard import (
    iter_route_paths,
    reject_cortex_secret_routes,
)

__all__ = ("iter_route_paths", "reject_cortex_secret_routes")
