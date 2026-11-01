"""API-key and session edge auth with per-route policy binding."""
from __future__ import annotations

import hashlib
import hmac
import time
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

    def add(self, key_id: str, secret: str, *, subject: str, tenant: str,
            scopes=(), ttl_s: Optional[float] = None) -> str:
        if "." in key_id or not key_id:
            raise ValueError("invalid key id")
        exp = self._clock() + ttl_s if ttl_s else None
        self._keys[key_id] = _KeyRecord(_digest(secret), subject, tenant, frozenset(scopes), expires_at=exp)
        return f"skk_{key_id}.{secret}"

    def revoke(self, key_id: str) -> bool:
        rec = self._keys.get(key_id)
        if not rec:
            return False
        rec.revoked = True
        return True

    def verify(self, token: str) -> Optional[Principal]:
        if not token.startswith("skk_") or "." not in token:
            return None
        key_id, secret = token[4:].split(".", 1)
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
        if len(secret) < 16:
            raise ValueError("session secret too short")
        self._secret = secret
        self.cookie = cookie
        self._clock = clock

    def _sign(self, payload: str) -> str:
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()

    def issue(self, subject: str, tenant: str, scopes=(), ttl_s: float = 3600) -> str:
        for part in (subject, tenant, *scopes):
            if "|" in part or "," in part:
                raise ValueError("illegal character in session field")
        payload = f"{subject}|{tenant}|{','.join(sorted(scopes))}|{int(self._clock() + ttl_s)}"
        return f"{payload}|{self._sign(payload)}"

    def verify(self, value: str) -> Optional[Principal]:
        parts = value.split("|")
        if len(parts) != 5:
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
            # Caller-supplied tenant headers are never authentication authority.
            # Public traffic remains in a single anonymous tenant unless the
            # request carries a separately verified principal.
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
