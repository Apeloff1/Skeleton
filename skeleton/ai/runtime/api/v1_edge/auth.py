"""API-key and session edge auth with per-route policy binding."""
from __future__ import annotations

import hashlib
import hmac
import time
import math
import re
import threading
from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, Optional

from .envelope import EdgeError, header
from .registry import RouteSpec


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant: str
    method: str  # "api_key" | "session" | "anonymous"
    scopes: FrozenSet[str] = frozenset()


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


@dataclass
class _KeyRecord:
    digest: str
    subject: str
    tenant: str
    scopes: FrozenSet[str]
    revoked: bool = False
    expires_at: Optional[float] = None


class ApiKeyStore:
    """Stores only SHA-256 digests; lookup by key id prefix (``skk_<id>.<secret>``)."""

    def __init__(self, clock: Callable[[], float] = time.time):
        self._keys: Dict[str, _KeyRecord] = {}
        self._clock = clock
        self._lock = threading.RLock()

    def add(self, key_id: str, secret: str, *, subject: str, tenant: str,
            scopes=(), ttl_s: Optional[float] = None) -> str:
        if type(key_id) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key_id) is None:
            raise ValueError("invalid bounded key id")
        if type(secret) is not str or not 16 <= len(secret) <= 256:
            raise ValueError("api key secret must be 16..256 characters")
        if any(type(v) is not str or not 1 <= len(v) <= 128 for v in (subject, tenant)):
            raise ValueError("invalid bounded principal identity")
        scopes = tuple(scopes)
        if len(scopes) > 64 or any(type(s) is not str or not 1 <= len(s) <= 128 for s in scopes):
            raise ValueError("invalid bounded scopes")
        if ttl_s is not None and (type(ttl_s) not in (int, float)
                or not math.isfinite(ttl_s) or not 1 <= ttl_s <= 365 * 86400):
            raise ValueError("invalid bounded api key lifetime")
        exp = self._clock() + ttl_s if ttl_s is not None else None
        with self._lock:
            if key_id in self._keys:
                raise ValueError("cannot overwrite existing API key identity")
            self._keys[key_id] = _KeyRecord(_digest(secret), subject, tenant, frozenset(scopes), expires_at=exp)
        return f"skk_{key_id}.{secret}"

    def revoke(self, key_id: str) -> bool:
        with self._lock:
            rec = self._keys.get(key_id)
            if not rec:
                return False
            rec.revoked = True
            return True

    def verify(self, token: str) -> Optional[Principal]:
        if type(token) is not str or len(token) > 328 or not token.startswith("skk_") or "." not in token:
            return None
        key_id, secret = token[4:].split(".", 1)
        with self._lock:
            rec = self._keys.get(key_id)
        if rec is None:
            hmac.compare_digest(_digest(secret), "0" * 64)  # constant-ish timing
            return None
        if not hmac.compare_digest(rec.digest, _digest(secret)):
            return None
        if rec.revoked or (rec.expires_at is not None and self._clock() >= rec.expires_at):
            return None
        return Principal(rec.subject, rec.tenant, "api_key", rec.scopes)


class SessionVerifier:
    """HMAC-signed session cookie: ``subject|tenant|scopes|exp|sig``."""

    def __init__(self, secret: bytes, cookie: str = "skl_session",
                 clock: Callable[[], float] = time.time):
        if type(secret) is not bytes or len(secret) < 16:
            raise ValueError("session secret too short")
        self._secret = secret
        self.cookie = cookie
        self._clock = clock

    def _sign(self, payload: str) -> str:
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()

    def issue(self, subject: str, tenant: str, scopes=(), ttl_s: float = 3600) -> str:
        scopes = tuple(scopes)
        if (len(scopes) > 64 or type(ttl_s) not in (int, float)
                or not math.isfinite(ttl_s) or not 1 <= ttl_s <= 86400):
            raise ValueError("invalid session lifetime or scope count")
        for part in (subject, tenant, *scopes):
            if (type(part) is not str or not 1 <= len(part) <= 128
                    or any(ch in part for ch in ("|", ",", "\r", "\n"))):
                raise ValueError("illegal or unbounded character in session field")
        payload = f"{subject}|{tenant}|{','.join(sorted(scopes))}|{int(self._clock() + ttl_s)}"
        value = f"{payload}|{self._sign(payload)}"
        # Do not issue a token that verify() will reject as oversized.
        if len(value) > 8192:
            raise ValueError("session cookie exceeds verifier capacity")
        return value

    def verify(self, value: str) -> Optional[Principal]:
        if type(value) is not str or len(value) > 8192:
            return None
        parts = value.split("|")
        if len(parts) != 5 or not parts[0] or not parts[1] or len(parts[4]) != 64:
            return None
        payload, sig = "|".join(parts[:4]), parts[4]
        if not hmac.compare_digest(self._sign(payload), sig):
            return None
        try:
            exp = int(parts[3])
        except ValueError:
            return None
        if self._clock() >= exp:
            return None
        scopes = frozenset(s for s in parts[2].split(",") if s)
        return Principal(parts[0], parts[1], "session", scopes)


def _cookie(scope, name: str) -> Optional[str]:
    raw = header(scope, "cookie")
    if not raw:
        return None
    for item in raw.split(";"):
        k, _, v = item.strip().partition("=")
        if k == name:
            return v
    return None


class EdgeAuthenticator:
    def __init__(self, keys: Optional[ApiKeyStore] = None, sessions: Optional[SessionVerifier] = None):
        self.keys = keys
        self.sessions = sessions

    def resolve(self, scope) -> Optional[Principal]:
        if self.keys is not None:
            tok = header(scope, "x-api-key")
            auth = header(scope, "authorization")
            if not tok and auth and auth.lower().startswith("bearer skk_"):
                tok = auth[7:].strip()
            if tok:
                p = self.keys.verify(tok)
                if p is None:
                    raise EdgeError(401, "EDGE.AUTH.INVALID_KEY", "invalid api key",
                                    headers={"www-authenticate": 'Bearer realm="api"'})
                return p
        if self.sessions is not None:
            val = _cookie(scope, self.sessions.cookie)
            if val:
                p = self.sessions.verify(val)
                if p is None:
                    raise EdgeError(401, "EDGE.AUTH.INVALID_SESSION", "invalid or expired session")
                return p
        return None

    def enforce(self, spec: RouteSpec, scope) -> Principal:
        if spec.auth == "public":
            p = None
            try:
                p = self.resolve(scope)
            except EdgeError:
                p = None
            # Public callers cannot claim another tenant's quota partition.
            return p or Principal("anonymous", "public", "anonymous")
        p = self.resolve(scope)
        if p is None:
            raise EdgeError(401, "EDGE.AUTH.REQUIRED", "authentication required",
                            headers={"www-authenticate": 'Bearer realm="api"'})
        if spec.auth != "any" and p.method != spec.auth:
            raise EdgeError(403, "EDGE.AUTH.METHOD", f"route requires {spec.auth} auth")
        missing = sorted(spec.scopes - p.scopes)
        if missing:
            raise EdgeError(403, "EDGE.AUTH.SCOPE", "missing scopes", {"missing": missing})
        return p
