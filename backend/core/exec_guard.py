"""Shared fail-closed guards for host execution and CORS policy.

User-supplied code is never allowed to execute on a detected production
application host. CORS also fails closed in deployed environments: an unset,
blank, malformed, or wildcard configuration cannot silently enable
cross-origin access.

``backend.server`` imports this module before it calls ``load_dotenv``. CORS
bootstrap therefore reads ``backend/.env`` only as a fallback when a process
environment value is absent, preserving normal environment precedence while
making the policy effective before Starlette middleware is constructed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from dotenv import dotenv_values

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
_DEFAULT_DOTENV = Path(__file__).resolve().parents[1] / ".env"


def _truthy_value(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower() in _TRUE_VALUES


def _effective_value(name: str, fallback: Mapping[str, object] | None = None) -> object:
    if name in os.environ:
        return os.environ.get(name)
    if fallback is not None:
        return fallback.get(name)
    return None


def _truthy(name: str) -> bool:
    return _truthy_value(os.environ.get(name))


def production_runtime_detected(fallback: Mapping[str, object] | None = None) -> bool:
    """Return True when process or fallback config identifies a deployed host."""
    if _truthy_value(_effective_value("EMERGENT_DEPLOY", fallback)):
        return True
    environment = _effective_value("ENVIRONMENT", fallback)
    if isinstance(environment, str) and environment.strip().lower() in _DEPLOYED_ENVIRONMENTS:
        return True
    return any(bool(_effective_value(marker, fallback)) for marker in _PRODUCTION_MARKERS)


def _valid_cors_origin(value: str) -> bool:
    """Accept only absolute HTTP(S) origins without credentials or URL suffixes."""
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
        and (port is None or 1 <= port <= 65535)
    )


def normalize_cors_origins(
    raw: str | None,
    *,
    production: bool,
    allow_dev_wildcard: bool = False,
) -> tuple[str, ...]:
    """Normalize a CORS allowlist and fail closed on partial/unsafe input."""
    values = tuple(part.strip().rstrip("/") for part in (raw or "").split(",") if part.strip())
    fallback = (_CORS_DISABLED_ORIGIN,) if production else _LOCAL_CORS_ORIGINS
    if not values:
        return fallback

    if "*" in values:
        if production or not allow_dev_wildcard or len(values) != 1:
            return fallback
        return ("*",)

    valid: list[str] = []
    for value in values:
        if not _valid_cors_origin(value):
            return fallback
        if value not in valid:
            valid.append(value)
    return tuple(valid) if valid else fallback


def _dotenv_fallback(path: Path | None = None) -> dict[str, object]:
    """Read dotenv values without mutating the process environment."""
    target = path or _DEFAULT_DOTENV
    try:
        values = dotenv_values(target)
    except (OSError, ValueError):
        return {}
    return dict(values) if isinstance(values, Mapping) else {}


def configure_cors_environment(dotenv_path: Path | None = None) -> tuple[str, ...]:
    """Publish normalized CORS config before ``backend.server`` builds middleware.

    Process environment values always win. ``backend/.env`` is consulted only
    for names that are absent from the process environment, matching
    ``load_dotenv(..., override=False)`` precedence instead of pre-empting it.
    """
    fallback = _dotenv_fallback(dotenv_path)
    raw = _effective_value("CORS_ORIGINS", fallback)
    raw_text = raw if isinstance(raw, str) else None
    allow_wildcard = _truthy_value(_effective_value("ALLOW_DEV_CORS_WILDCARD", fallback))
    origins = normalize_cors_origins(
        raw_text,
        production=production_runtime_detected(fallback),
        allow_dev_wildcard=allow_wildcard,
    )
    os.environ["CORS_ORIGINS"] = ",".join(origins)
    return origins


# server.py imports this module before calling load_dotenv. Resolve the same
# dotenv file as a fallback now so explicit local config is not overwritten by
# a synthetic default, while process environment continues to take precedence.
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
