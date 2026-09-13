"""Shared fail-closed guard for user-controlled host code execution.

This module deliberately separates a developer opt-in from a production override.
User supplied code must never execute on an application host merely because a
single permissive environment variable leaked into a deployment.
"""

from __future__ import annotations

import os

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_PRODUCTION_MARKERS = (
    "K_SERVICE",  # Cloud Run
    "KUBERNETES_SERVICE_HOST",  # Kubernetes
    "WEBSITE_INSTANCE_ID",  # Azure App Service
    "DYNO",  # Heroku
)


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE_VALUES


def production_runtime_detected() -> bool:
    """Return True when the process appears to be running on a deployed host."""
    if _truthy("EMERGENT_DEPLOY"):
        return True
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    if environment in {"prod", "production"}:
        return True
    return any(bool(os.environ.get(marker)) for marker in _PRODUCTION_MARKERS)


def code_execution_enabled() -> bool:
    """Return whether user-controlled host execution is explicitly permitted.

    Local/trusted development requires ``ALLOW_UNSAFE_CODE_EXECUTION=true``.
    Production additionally requires ``ALLOW_PRODUCTION_HOST_CODE_EXECUTION=true``.
    The second gate prevents accidental enablement through copied development
    configuration and keeps the production default fail-closed.
    """
    if not _truthy("ALLOW_UNSAFE_CODE_EXECUTION"):
        return False
    if production_runtime_detected():
        return _truthy("ALLOW_PRODUCTION_HOST_CODE_EXECUTION")
    return True


def execution_disabled_message(action: str = "Code execution") -> str:
    if production_runtime_detected():
        return (
            f"{action} is disabled on the application host. "
            "Use an isolated sandbox, or explicitly set both execution overrides "
            "only for a deliberately isolated production worker."
        )
    return (
        f"{action} is disabled by default. "
        "Set ALLOW_UNSAFE_CODE_EXECUTION=true only in a trusted isolated environment."
    )


def execution_disabled_response(action: str = "Code execution") -> dict:
    return {
        "ok": False,
        "disabled": True,
        "error": execution_disabled_message(action),
    }


def require_execution_allowed(action: str = "Code execution") -> bool:
    """Compatibility predicate used by execution routes."""
    return code_execution_enabled()
