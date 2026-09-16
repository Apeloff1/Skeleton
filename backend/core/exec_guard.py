"""Shared fail-closed guards for execution and production CORS policy.

User-supplied code is never allowed to execute on a detected production
application host. CORS is likewise fail-closed in deployed environments:
unset, blank, or wildcard configuration cannot silently enable cross-origin
access. Local development uses explicit localhost origins unless a developer
opts into a wildcard.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_DEPLOYED_ENVIRONMENTS = frozenset({"prod", "production", "staging"})
_PRODUCTION_MARKERS = (
    "K_SERVICE",  # Cloud Run
    "KUBERNETES_SERVICE_HOST",  # Kubernetes
    "WEBSITE_INSTANCE_ID",  # Azure App Service
    "DYNO",  # Heroku
)
_CORS_DISABLED_ORIGIN = "https://cors-disabled.invalid"
_LOCAL_CORS_ORIGINS = ("http://localhost", "http://127.0.0.1")


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE_VALUES


def production_runtime_detected() -> bool:
    """Return True when the process appears to be running on a deployed host."""
    if _truthy("EMERGENT_DEPLOY"):
        return True
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    if environment in _DEPLOYED_ENVIRONMENTS:
        return True
    return any(bool(os.environ.get(marker)) for marker in _PRODUCTION_MARKERS)


def _valid_cors_origin(value: str) -> bool:
    """Accept only absolute HTTP(S) origins without paths or credentials."""
    parsed = urlsplit(value)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


def normalize_cors_origins(raw: str | None, *, production: bool) -> tuple[str, ...]:
    """Normalize and validate CORS origins, failing closed when unsafe."""
    values = tuple(part.strip().rstrip("/") for part in (raw or "").split(",") if part.strip())
    if not values:
        return (_CORS_DISABLED_ORIGIN,) if production else _LOCAL_CORS_ORIGINS

    if "*" in values:
        if production or not _truthy("ALLOW_DEV_CORS_WILDCARD") or len(values) != 1:
            return (_CORS_DISABLED_ORIGIN,) if production else _LOCAL_CORS_ORIGINS
        return ("*",)

    valid = tuple(dict.fromkeys(value for value in values if _valid_cors_origin(value)))
    # A partially invalid list is not accepted: silently dropping an invalid
    # origin can hide a deployment/configuration error and create an unintended
    # allowlist. Treat any invalid entry as a fail-closed configuration.
    if len(valid) != len(values):
        return (_CORS_DISABLED_ORIGIN,) if production else _LOCAL_CORS_ORIGINS
    if not valid:
        return (_CORS_DISABLED_ORIGIN,) if production else _LOCAL_CORS_ORIGINS
    return valid


def configure_cors_environment() -> tuple[str, ...]:
    """Set the normalized CORS environment before the application builds middleware."""
    # ``backend.server`` imports this guard before its own ``load_dotenv`` call.
    # Load the same backend-local .env first so an explicit development origin
    # is not replaced by the localhost fallback before the server sees it.
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    origins = normalize_cors_origins(
        os.environ.get("CORS_ORIGINS"), production=production_runtime_detected()
    )
    os.environ["CORS_ORIGINS"] = ",".join(origins)
    return origins


# Normalize after loading the intended configuration source, even though the
# server imports this module before its own explicit load_dotenv() call.
configure_cors_environment()


def code_execution_enabled() -> bool:
    """Return whether user-controlled host execution is explicitly permitted.

    Host execution is fail-closed in every detected deployed runtime. No
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
