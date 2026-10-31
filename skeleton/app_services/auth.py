"""User + session service.

* Passwords: scrypt (n=2**14, r=8, p=1) with per-user salt, constant-time verify.
* Sessions: opaque 256-bit tokens returned once to the caller; only a SHA-256
  digest is persisted.  ``resolve_session`` implements the ``SessionResolver``
  port that Middleware's authN gate consumes; it never returns the token.
* This module mounts no HTTP routes (secrets stay off HTTP, #3637).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from skeleton.app_services.ports import SessionPrincipal, SessionRepository, User, UserRepository

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)
MIN_PASSWORD_LEN = 10


class AuthError(Exception):
    """Generic auth failure; message never reveals which factor failed."""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$%d$%d$%d$%s$%s" % (_SCRYPT["n"], _SCRYPT["r"], _SCRYPT["p"],
                                      base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = encoded.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64),
                            n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, expected)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class IssuedSession:
    """Returned exactly once at login.  ``token`` must go to the client only via
    the Middleware-gated transport (e.g. HttpOnly cookie), never logged."""

    token: str
    principal: SessionPrincipal

    def __repr__(self) -> str:  # keep tokens out of logs/tracebacks
        return f"IssuedSession(principal={self.principal!r}, token=<redacted>)"


class AuthService:
    def __init__(self, users: UserRepository, sessions: SessionRepository, *,
                 session_ttl_s: float = 7 * 24 * 3600, sliding: bool = True,
                 clock: Callable[[], float] = time.time) -> None:
        self.users, self.sessions = users, sessions
        self.ttl, self.sliding, self.clock = session_ttl_s, sliding, clock
        self._dummy_hash = hash_password(secrets.token_hex(8))

    def register(self, email: str, password: str, display_name: str = "") -> User:
        if not _EMAIL_RE.match(email or ""):
            raise ValueError("invalid email")
        if len(password or "") < MIN_PASSWORD_LEN:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
        if self.users.find_by_email(email):
            raise ValueError("email already registered")
        return self.users.create_user(email, display_name or email.split("@")[0], hash_password(password))

    def login(self, email: str, password: str, scopes: Sequence[str] = ()) -> IssuedSession:
        found = self.users.find_by_email(email or "")
        if not found:
            verify_password(password or "", self._dummy_hash)  # timing equalisation
            raise AuthError("invalid credentials")
        user, encoded = found
        if not verify_password(password or "", encoded) or user.disabled:
            raise AuthError("invalid credentials")
        return self._issue(user.user_id, scopes)

    def _issue(self, user_id: str, scopes: Sequence[str]) -> IssuedSession:
        token = secrets.token_urlsafe(32)
        now = self.clock()
        sid = f"ses_{uuid.uuid4().hex}"
        self.sessions.insert(sid, user_id, token_digest(token), tuple(scopes), now, now + self.ttl)
        return IssuedSession(token, SessionPrincipal(sid, user_id, tuple(scopes), now + self.ttl))

    def resolve_session(self, token: str) -> Optional[SessionPrincipal]:
        if not token:
            return None
        p = self.sessions.by_digest(token_digest(token))
        now = self.clock()
        if p is None or p.expires_at <= now:
            return None
        if self.sliding:
            self.sessions.touch(p.session_id, now + self.ttl)
            p = SessionPrincipal(p.session_id, p.user_id, p.scopes, now + self.ttl)
        return p

    def logout(self, token: str) -> bool:
        p = self.sessions.by_digest(token_digest(token or ""))
        return bool(p) and self.sessions.revoke(p.session_id)

    def change_password(self, user_id: str, old: str, new: str) -> None:
        user = self.users.get_user(user_id)
        found = self.users.find_by_email(user.email) if user else None
        if not found or not verify_password(old, found[1]):
            raise AuthError("invalid credentials")
        if len(new) < MIN_PASSWORD_LEN:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
        self.users.set_password_hash(user_id, hash_password(new))
        self.sessions.revoke_user(user_id)

    def disable_user(self, user_id: str) -> None:
        self.users.set_disabled(user_id, True)
        self.sessions.revoke_user(user_id)

    def sweep(self) -> int:
        return self.sessions.purge_expired(self.clock())
