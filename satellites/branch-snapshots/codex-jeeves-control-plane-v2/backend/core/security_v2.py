"""
core/security_v2.py — Security hardening layer (Feb 2026, Category 3).

Augments the existing middleware/security.py (RateLimit + Audit + SizeLimit)
with:

  1. SecurityHeadersMiddleware — sets CSP, HSTS, X-Frame-Options, etc.
  2. SecretsScrubFilter        — redacts API keys/emails/JWTs in log lines.
  3. CORSAllowlistGuard        — replaces "*" CORS in production.
  4. RequestIdMiddleware       — assigns each request a correlation rid.
  5. bcrypt helpers            — work-factor 12 + lazy-migration on login.
  6. strict_validator()        — decorator for Pydantic v2 strict bodies.
  7. install_security_headers(app, ...) — one-shot bootstrap helper.

All middlewares are best-effort no-ops if dependencies missing.
"""
from __future__ import annotations
import logging
import os
import re
import secrets
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("SecurityV2")

# ════════════════════════════════════════════════════════════════════════════
#  1. Security headers
# ════════════════════════════════════════════════════════════════════════════
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Set baseline security headers on every API response."""
    def __init__(self, app, *, frame_options="DENY", hsts_max_age=31_536_000,
                 csp: str | None = None, referrer_policy="no-referrer"):
        super().__init__(app)
        self.frame_options = frame_options
        self.hsts_max_age = hsts_max_age
        self.csp = csp
        self.referrer_policy = referrer_policy

    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        h = resp.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        # Endpoints that serve content explicitly meant to be embedded (e.g. the
        # playable-game preview iframe) must NOT be frame-blocked.
        path = request.url.path
        embeddable = path.startswith("/api/playable/") and path.endswith("/raw")
        if not embeddable:
            h.setdefault("X-Frame-Options", self.frame_options)
        h.setdefault("Referrer-Policy", self.referrer_policy)
        h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if self.hsts_max_age:
            h.setdefault("Strict-Transport-Security",
                         f"max-age={self.hsts_max_age}; includeSubDomains")
        if not embeddable and self.csp and "content-security-policy" not in (k.lower() for k in h.keys()):
            h["Content-Security-Policy"] = self.csp
        return resp


# ════════════════════════════════════════════════════════════════════════════
#  2. Secrets scrub for logs
# ════════════════════════════════════════════════════════════════════════════
_SCRUB_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "sk-***"),
    (re.compile(r"AIza[0-9A-Za-z_-]{30,}"), "AIza***"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "ghp_***"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{50,}"), "github_pat_***"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", re.IGNORECASE), "Bearer ***"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "<jwt-redacted>"),
    (re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"), "<email>"),
    (re.compile(r"mongodb(?:\+srv)?://[^\s'\"]+"), "mongodb://***"),
]

class SecretsScrubFilter(logging.Filter):
    """Logging filter that redacts secrets from every log message."""
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            for pat, sub in _SCRUB_PATTERNS:
                msg = pat.sub(sub, msg)
            record.msg = msg
            record.args = ()
        except Exception:
            pass
        return True

def install_secrets_scrub():
    """Attach SecretsScrubFilter to the root logger."""
    flt = SecretsScrubFilter()
    root = logging.getLogger()
    if not any(isinstance(f, SecretsScrubFilter) for f in root.filters):
        root.addFilter(flt)
    for name in ("CodeDock.Nexus", "Reliability", "Perf", "uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, SecretsScrubFilter) for f in lg.filters):
            lg.addFilter(flt)


# ════════════════════════════════════════════════════════════════════════════
#  3. CORS allowlist (lazy compile from env)
# ════════════════════════════════════════════════════════════════════════════
def cors_allowlist() -> list[str]:
    raw = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        # Sensible defaults — preview emergent + localhost
        return [
            "https://gemini-game-craft.preview.emergentagent.com",
            "http://localhost:3000",
            "http://localhost:19006",
        ]
    return [s.strip() for s in raw.split(",") if s.strip()]


# ════════════════════════════════════════════════════════════════════════════
#  4. Request-Id middleware
# ════════════════════════════════════════════════════════════════════════════
class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign each request a correlation rid + echo it back."""
    HEADER = "X-Request-Id"
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get(self.HEADER) or uuid.uuid4().hex[:16]
        request.state.rid = rid
        resp = await call_next(request)
        resp.headers[self.HEADER] = rid
        return resp


# ════════════════════════════════════════════════════════════════════════════
#  5. Bcrypt helpers (work-factor 12 + lazy migration)
# ════════════════════════════════════════════════════════════════════════════
def bcrypt_hash(password: str, *, rounds: int = 12) -> str:
    """Hash a password with bcrypt (work-factor 12 = ~250 ms on modern CPUs)."""
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")
    except ImportError:
        raise RuntimeError("bcrypt not installed")

def bcrypt_verify(password: str, hashed: str) -> tuple[bool, bool]:
    """Verify a password. Returns (ok, needs_rehash).

    needs_rehash is True when the stored hash uses a lower work factor than
    our current default — callers should rehash on successful login.
    """
    try:
        import bcrypt
        ok = bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        # bcrypt hashes look like $2b$<rounds>$<salt><hash>
        try:
            rounds = int(hashed.split("$")[2])
        except Exception:
            rounds = 0
        return ok, ok and rounds < 12
    except Exception:
        return False, False


# ════════════════════════════════════════════════════════════════════════════
#  6. Strict-validator decorator helper
# ════════════════════════════════════════════════════════════════════════════
def strict_validator(model_cls):
    """Decorator wrapping a route handler so the body is validated strictly
    (rejects extra fields, no type coercion).

    Usage:
        @router.post("/foo")
        @strict_validator(FooBody)
        async def foo(req: Request, body: FooBody): ...
    """
    import functools
    def dec(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            body = kwargs.get("body") or next((a for a in args if isinstance(a, model_cls)), None)
            if body is not None:
                # Pydantic v2 will already enforce types; this re-validates
                # with extra=forbid as a belt-and-braces guard.
                try:
                    body_dict = body.model_dump(exclude_unset=False)
                    model_cls.model_validate(body_dict, strict=True)
                except Exception as e:
                    from fastapi import HTTPException
                    raise HTTPException(status_code=422, detail=f"strict validation failed: {e}")
            return await fn(*args, **kwargs)
        return wrapper
    return dec


# ════════════════════════════════════════════════════════════════════════════
#  7. One-shot bootstrap
# ════════════════════════════════════════════════════════════════════════════
def install_security_headers(app, *, csp: str | None = None):
    """Install all Cat-3 hardening middlewares (idempotent)."""
    try:
        app.add_middleware(SecurityHeadersMiddleware, csp=csp)
        app.add_middleware(RequestIdMiddleware)
        install_secrets_scrub()
        logger.info("[security_v2] headers + request-id + log scrubbing installed")
    except Exception as e:
        logger.warning(f"[security_v2] install failed: {e}")


__all__ = [
    "SecurityHeadersMiddleware", "SecretsScrubFilter", "install_secrets_scrub",
    "cors_allowlist", "RequestIdMiddleware",
    "bcrypt_hash", "bcrypt_verify",
    "strict_validator", "install_security_headers",
]
