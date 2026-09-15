"""Shared fail-closed guard for user-controlled host code execution.

User-supplied code is never allowed to execute on a detected production
application host. Local/trusted development still requires an explicit opt-in,
but production cannot be re-enabled through environment configuration alone.

Production code execution belongs in a separately isolated sandbox/worker with
an OS/container security boundary, not inside the API process that holds service
credentials and application data access.
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

    Host execution is fail-closed in every detected production runtime. No
    environment override can turn it back on inside the application process.
    Trusted local development must still opt in with
    ``ALLOW_UNSAFE_CODE_EXECUTION=true``.
    """
    if production_runtime_detected():
        return False
    return _truthy("ALLOW_UNSAFE_CODE_EXECUTION")


def execution_disabled_message(action: str = "Code execution") -> str:
    if production_runtime_detected():
        return (
            f"{action} is disabled on the production application host. "
            "Run untrusted code only in a separately isolated sandbox worker."
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
