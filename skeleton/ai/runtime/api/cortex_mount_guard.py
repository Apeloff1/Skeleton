"""Staged mirror of the canonical cortex secrets mount guard.

The implementation lives in ``skeleton.api.cortex_mount_guard``. This module
re-exports it so the runtime tree cannot keep a second, older startup check.
"""
from skeleton.api.cortex_mount_guard import reject_cortex_secret_routes

__all__ = ["reject_cortex_secret_routes"]
