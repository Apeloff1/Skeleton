"""Fail-closed configuration helpers for the existing GameForge JWT/RBAC surface.

The HTTP auth implementation predates the consolidation work and historically
embedded development credentials and a public fallback JWT secret. This module
moves security-sensitive configuration into a framework-free contract that can
be tested without FastAPI, MongoDB, bcrypt, or PyJWT.
"""

from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

_MIN_JWT_SECRET_CHARS = 32
_MIN_SEED_PASSWORD_CHARS = 16
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_PRODUCTION_ENVS = frozenset({"prod", "production"})
_DEFAULT_SESSION_API = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
_DEV_EPHEMERAL_JWT_SECRET = secrets.token_urlsafe(48)
_MAX_SECRET_FILE_BYTES = 64 * 1024


class AuthConfigurationError(RuntimeError):
    """Raised when auth configuration would weaken the trust boundary."""


@dataclass(frozen=True, slots=True)
class SeedAdminCredentials:
    email: str
    password: str = field(repr=False)


def _env(source: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if source is None else source


def read_secret(name: str, source: Mapping[str, str] | None = None) -> str:
    """Read ``name`` from the environment or from a mounted ``<name>_FILE``.

    Supports the Docker/Kubernetes secrets convention: ``<name>_FILE`` holds an
    absolute path to a regular file whose contents are the secret (one trailing
    newline is stripped). Setting both forms is ambiguous and rejected, as are
    relative paths, non-regular files, oversized files and non-UTF-8 content.
    Error messages name the variable but never echo a secret or its contents.
    Returns ``""`` when neither form is set.
    """

    environ = _env(source)
    direct = environ.get(name, "")
    file_var = f"{name}_FILE"
    path_value = environ.get(file_var, "").strip()
    if not path_value:
        return direct
    if direct:
        raise AuthConfigurationError(f"set only one of {name} or {file_var}")
    if not os.path.isabs(path_value):
        raise AuthConfigurationError(f"{file_var} must be an absolute path")
    try:
        # Symlinks are followed on purpose: Kubernetes projects secret volumes
        # through ``..data`` symlinks. fstat below checks the resolved target.
        fd = os.open(path_value, os.O_RDONLY)
    except OSError as exc:
        raise AuthConfigurationError(f"{file_var} is not readable") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise AuthConfigurationError(f"{file_var} must point to a regular file")
        if info.st_size > _MAX_SECRET_FILE_BYTES:
            raise AuthConfigurationError(f"{file_var} is larger than {_MAX_SECRET_FILE_BYTES} bytes")
        raw = os.read(fd, _MAX_SECRET_FILE_BYTES + 1)
    finally:
        os.close(fd)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthConfigurationError(f"{file_var} must contain UTF-8 text") from exc
    if text.endswith("\r\n"):
        return text[:-2]
    if text.endswith("\n"):
        return text[:-1]
    return text


def auth_enforced(source: Mapping[str, str] | None = None) -> bool:
    """Resolve auth enforcement with production-safe defaulting.

    An explicit ``GAMEFORGE_AUTH_ENFORCE`` wins. If absent, production-like
    ``APP_ENV``/``ENVIRONMENT`` values enforce authentication automatically,
    while local development remains compatible with the existing open workflow.
    """

    environ = _env(source)
    raw = environ.get("GAMEFORGE_AUTH_ENFORCE")
    if raw is not None:
        normalized = raw.strip().lower()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
        raise AuthConfigurationError("GAMEFORGE_AUTH_ENFORCE must be a boolean flag")
    environment = (
        environ.get("APP_ENV") or environ.get("ENVIRONMENT") or "development"
    ).strip().lower()
    return environment in _PRODUCTION_ENVS


def resolve_jwt_secret(
    source: Mapping[str, str] | None = None,
    *,
    development_secret: str | None = None,
) -> str:
    """Return a strong JWT secret without ever using a public fixed fallback."""

    environ = _env(source)
    configured = read_secret("GAMEFORGE_JWT_SECRET", environ).strip()
    if configured:
        if len(configured) < _MIN_JWT_SECRET_CHARS:
            raise AuthConfigurationError(
                f"GAMEFORGE_JWT_SECRET must be at least {_MIN_JWT_SECRET_CHARS} characters"
            )
        return configured
    if auth_enforced(environ):
        raise AuthConfigurationError(
            "GAMEFORGE_JWT_SECRET is required when authentication is enforced"
        )
    ephemeral = _DEV_EPHEMERAL_JWT_SECRET if development_secret is None else development_secret
    if len(ephemeral) < _MIN_JWT_SECRET_CHARS:
        raise AuthConfigurationError("development JWT secret is unexpectedly weak")
    return ephemeral


def resolve_seed_admin(source: Mapping[str, str] | None = None) -> SeedAdminCredentials | None:
    """Return optional bootstrap admin credentials only when explicitly paired."""

    environ = _env(source)
    email = environ.get("GAMEFORGE_SEED_ADMIN_EMAIL", "").strip().lower()
    password = read_secret("GAMEFORGE_SEED_ADMIN_PASSWORD", environ)
    if not email and not password:
        return None
    if not email or not password:
        raise AuthConfigurationError(
            "GAMEFORGE_SEED_ADMIN_EMAIL and GAMEFORGE_SEED_ADMIN_PASSWORD must be set together"
        )
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise AuthConfigurationError("GAMEFORGE_SEED_ADMIN_EMAIL is not a valid bootstrap email")
    if len(password) < _MIN_SEED_PASSWORD_CHARS:
        raise AuthConfigurationError(
            f"GAMEFORGE_SEED_ADMIN_PASSWORD must be at least {_MIN_SEED_PASSWORD_CHARS} characters"
        )
    return SeedAdminCredentials(email=email, password=password)


def resolve_session_api(source: Mapping[str, str] | None = None) -> str:
    """Resolve the external OAuth session exchange endpoint safely."""

    environ = _env(source)
    value = environ.get("EMERGENT_SESSION_API", _DEFAULT_SESSION_API).strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AuthConfigurationError("EMERGENT_SESSION_API must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise AuthConfigurationError("EMERGENT_SESSION_API must not embed credentials")
    if auth_enforced(environ) and parsed.scheme != "https":
        raise AuthConfigurationError("EMERGENT_SESSION_API must use HTTPS when auth is enforced")
    return value


def security_summary(source: Mapping[str, str] | None = None) -> dict[str, object]:
    """Expose non-secret configuration state for diagnostics."""

    environ = _env(source)
    configured_secret = bool(read_secret("GAMEFORGE_JWT_SECRET", environ).strip())
    seed = resolve_seed_admin(environ)
    return {
        "enforced": auth_enforced(environ),
        "jwt_secret_configured": configured_secret,
        "development_secret_ephemeral": not configured_secret and not auth_enforced(environ),
        "seed_admin_configured": seed is not None,
        "session_api_scheme": urlsplit(resolve_session_api(environ)).scheme,
    }
