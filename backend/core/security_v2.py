"""Core security primitives for the backend.

This module augments middleware/security.py with browser response hardening,
secret scrubbing, strict production CORS defaults, safe request correlation,
password hashing helpers, and strict validation helpers.
"""
from __future__ import annotations

import logging
import os
import re

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from ..middleware.client_identity import sanitize_request_id
except ImportError:
    from middleware.client_identity import sanitize_request_id

logger = logging.getLogger("SecurityV2")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Set defensive browser/security headers on every response."""

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
        headers.setdefault("Referrer-Policy", self.referrer_policy)
        headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=(), usb=()")
        headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")

        path = request.url.path
        embeddable = path.startswith("/api/playable/") and path.endswith("/raw")
        if embeddable:
            # Generated/playable HTML is intentionally frameable. CSP sandbox
            # keeps its script execution out of the application's same-origin
            # authority even if the generated content is attacker-influenced.
            headers.setdefault(
                "Content-Security-Policy",
                "sandbox allow-scripts; default-src 'self' data: blob:; "
                "img-src 'self' data: blob:; media-src 'self' data: blob:; "
                "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' blob:; "
                "connect-src 'self'",
            )
        else:
            headers.setdefault("X-Frame-Options", self.frame_options)
            if self.csp:
                headers.setdefault("Content-Security-Policy", self.csp)

        if self.hsts_max_age:
            headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={self.hsts_max_age}; includeSubDomains",
            )

        if path.startswith(("/api/auth", "/api/security", "/api/admin")):
            headers.setdefault("Cache-Control", "no-store, max-age=0")
            headers.setdefault("Pragma", "no-cache")
        return resp


_SCRUB_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "sk-***"),
    (re.compile(r"AIza[0-9A-Za-z_-]{30,}"), "AIza***"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"), "gh*_***"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{30,}"), "github_pat_***"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AKIA***"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.=+/]{12,}", re.IGNORECASE), "Bearer ***"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "<jwt-redacted>"),
    (re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"), "<email>"),
    (re.compile(r"mongodb(?:\+srv)?://[^\s'\"]+", re.IGNORECASE), "mongodb://***"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret)\b"
            r"\s*[:=]\s*([^\s,;]+)"
        ),
        r"\1=***",
    ),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "<private-key-redacted>"),
]


class SecretsScrubFilter(logging.Filter):
    """Logging filter that redacts common credentials and personal identifiers."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            for pattern, replacement in _SCRUB_PATTERNS:
                msg = pattern.sub(replacement, msg)
            record.msg = msg
            record.args = ()
        except Exception:
            # Scrubbing must never crash the application or logging pipeline.
            pass
        return True


def install_secrets_scrub() -> None:
    flt = SecretsScrubFilter()
    root = logging.getLogger()
    if not any(isinstance(existing, SecretsScrubFilter) for existing in root.filters):
        root.addFilter(flt)
    for name in ("CodeDock.Nexus", "Reliability", "Perf", "uvicorn", "uvicorn.error", "uvicorn.access"):
        target = logging.getLogger(name)
        if not any(isinstance(existing, SecretsScrubFilter) for existing in target.filters):
            target.addFilter(flt)


def cors_allowlist() -> list[str]:
    """Return an explicit CORS allowlist; production defaults closed."""
    raw = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    environment = os.environ.get("ENVIRONMENT", os.environ.get("ENV", "development")).lower()
    if environment in {"production", "prod"}:
        return []
    return [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:19006",
        "http://localhost:8000",
    ]


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign a bounded, printable request correlation identifier."""

    HEADER = "X-Request-Id"

    async def dispatch(self, request: Request, call_next):
        rid = sanitize_request_id(request.headers.get(self.HEADER))
        request.state.rid = rid
        resp = await call_next(request)
        resp.headers[self.HEADER] = rid
        return resp


def bcrypt_hash(password: str, *, rounds: int = 12) -> str:
    """Hash a password with bcrypt with a minimum cost of 12."""
    try:
        import bcrypt
    except ImportError as exc:
        raise RuntimeError("bcrypt not installed") from exc

    safe_rounds = min(max(int(rounds), 12), 16)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=safe_rounds)).decode("utf-8")


def bcrypt_verify(password: str, hashed: str) -> tuple[bool, bool]:
    """Verify a password and indicate whether the hash should be upgraded."""
    try:
        import bcrypt

        ok = bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        try:
            rounds = int(hashed.split("$")[2])
        except Exception:
            rounds = 0
        return ok, ok and rounds < 12
    except Exception:
        return False, False


def strict_validator(model_cls):
    """Revalidate a Pydantic request body in strict mode before a handler."""
    import functools

    def dec(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            body = kwargs.get("body") or next((a for a in args if isinstance(a, model_cls)), None)
            if body is not None:
                try:
                    body_dict = body.model_dump(exclude_unset=False)
                    model_cls.model_validate(body_dict, strict=True)
                except Exception as exc:
                    from fastapi import HTTPException

                    raise HTTPException(status_code=422, detail="strict validation failed") from exc
            return await fn(*args, **kwargs)

        return wrapper

    return dec


def install_security_headers(app, *, csp: str | None = None) -> None:
    """Install security middleware; startup fails if hardening cannot install."""
    app.add_middleware(SecurityHeadersMiddleware, csp=csp)
    app.add_middleware(RequestIdMiddleware)
    install_secrets_scrub()
    logger.info("[security_v2] headers + request-id + log scrubbing installed")


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
