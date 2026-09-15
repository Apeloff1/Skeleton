"""
core/security_v2.py — Security hardening layer.

Augments middleware/security.py with response headers, log-secret scrubbing,
request correlation, password helpers, and strict body validation.
"""
from __future__ import annotations

import logging
import os
import re

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from middleware.request_id import normalize_request_id

logger = logging.getLogger("SecurityV2")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Set baseline browser security headers on every response."""

    def __init__(
        self,
        app,
        *,
        frame_options="DENY",
        hsts_max_age=31_536_000,
        csp: str | None = None,
        referrer_policy="no-referrer",
    ):
        super().__init__(app)
        self.frame_options = frame_options
        self.hsts_max_age = hsts_max_age
        self.csp = csp
        self.referrer_policy = referrer_policy

    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        headers = resp.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        path = request.url.path
        embeddable = path.startswith("/api/playable/") and path.endswith("/raw")
        if not embeddable:
            headers.setdefault("X-Frame-Options", self.frame_options)
        headers.setdefault("Referrer-Policy", self.referrer_policy)
        headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if self.hsts_max_age:
            headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={self.hsts_max_age}; includeSubDomains",
            )
        if not embeddable and self.csp and "content-security-policy" not in (
            key.lower() for key in headers.keys()
        ):
            headers["Content-Security-Policy"] = self.csp
        return resp


# Redact common provider credentials plus generic credential assignments. Keep
# patterns bounded so ordinary identifiers are not destroyed unnecessarily.
_SCRUB_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "sk-***"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), "AIza***"),
    (re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"), "ghp_***"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"), "github_pat_***"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"), "xox*-***"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AKIA***"),
    (re.compile(r"Bearer\s+[^\s,;]{12,}", re.IGNORECASE), "Bearer ***"),
    (re.compile(r"Basic\s+[A-Za-z0-9+/=]{12,}", re.IGNORECASE), "Basic ***"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)"
            r"(\s*[:=]\s*)([^\s,;]{6,})"
        ),
        r"\1\2***",
    ),
    (
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
        "<jwt-redacted>",
    ),
    (
        re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"),
        "<email>",
    ),
    (re.compile(r"mongodb(?:\+srv)?://[^\s'\"]+", re.IGNORECASE), "mongodb://***"),
]


class SecretsScrubFilter(logging.Filter):
    """Redact secrets before a log record reaches configured handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            for pattern, replacement in _SCRUB_PATTERNS:
                message = pattern.sub(replacement, message)
            record.msg = message
            record.args = ()
        except Exception:
            # Logging must not crash request handling; a filter failure is safer
            # than converting application availability into a logging dependency.
            pass
        return True


def _attach_scrub_filter(target, scrub_filter: SecretsScrubFilter) -> None:
    if not any(isinstance(item, SecretsScrubFilter) for item in target.filters):
        target.addFilter(scrub_filter)


def install_secrets_scrub():
    """Attach scrubbing where propagated child records are actually emitted.

    Logger filters on the root logger do not filter records created by child loggers
    before propagation. Root handlers therefore need the filter as well.
    """
    scrub_filter = SecretsScrubFilter()
    root = logging.getLogger()
    _attach_scrub_filter(root, scrub_filter)
    for handler in root.handlers:
        _attach_scrub_filter(handler, scrub_filter)
    for name in (
        "CodeDock.Nexus",
        "Reliability",
        "Perf",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
    ):
        target = logging.getLogger(name)
        _attach_scrub_filter(target, scrub_filter)
        for handler in target.handlers:
            _attach_scrub_filter(handler, scrub_filter)


def cors_allowlist() -> list[str]:
    raw = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return [
            "https://gemini-game-craft.preview.emergentagent.com",
            "http://localhost:3000",
            "http://localhost:19006",
        ]
    return [value.strip() for value in raw.split(",") if value.strip()]


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign a bounded, log-safe correlation ID and echo it back."""

    HEADER = "X-Request-Id"

    async def dispatch(self, request: Request, call_next):
        rid = normalize_request_id(request.headers.get(self.HEADER))
        request.state.rid = rid
        request.state.request_id = rid
        resp = await call_next(request)
        resp.headers[self.HEADER] = rid
        return resp


def bcrypt_hash(password: str, *, rounds: int = 12) -> str:
    try:
        import bcrypt

        return bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)
        ).decode("utf-8")
    except ImportError as exc:
        raise RuntimeError("bcrypt not installed") from exc


def bcrypt_verify(password: str, hashed: str) -> tuple[bool, bool]:
    try:
        import bcrypt

        ok = bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        try:
            rounds = int(hashed.split("$")[2])
        except (IndexError, ValueError):
            rounds = 0
        return ok, ok and rounds < 12
    except (ImportError, ValueError, TypeError):
        return False, False


def strict_validator(model_cls):
    """Re-validate an already parsed model with strict type semantics."""
    import functools

    def dec(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            body = kwargs.get("body") or next(
                (arg for arg in args if isinstance(arg, model_cls)), None
            )
            if body is not None:
                try:
                    body_dict = body.model_dump(exclude_unset=False)
                    model_cls.model_validate(body_dict, strict=True)
                except Exception as exc:
                    from fastapi import HTTPException

                    raise HTTPException(
                        status_code=422,
                        detail="strict validation failed",
                    ) from exc
            return await fn(*args, **kwargs)

        return wrapper

    return dec


def install_security_headers(app, *, csp: str | None = None):
    """Install browser hardening, request IDs, and log scrubbing once."""
    marker = "_skeleton_security_v2_installed"
    if getattr(app.state, marker, False):
        return
    try:
        app.add_middleware(SecurityHeadersMiddleware, csp=csp)
        app.add_middleware(RequestIdMiddleware)
        install_secrets_scrub()
        setattr(app.state, marker, True)
        logger.info("[security_v2] headers + request-id + log scrubbing installed")
    except Exception as exc:
        logger.warning("[security_v2] install failed: %s", type(exc).__name__)


__all__ = [
    "SecurityHeadersMiddleware",
    "SecretsScrubFilter",
    "install_secrets_scrub",
    "cors_allowlist",
    "RequestIdMiddleware",
    "bcrypt_hash",
    "bcrypt_verify",
    "strict_validator",
    "install_security_headers",
]
