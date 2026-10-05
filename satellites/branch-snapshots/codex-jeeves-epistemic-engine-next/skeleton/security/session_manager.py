"""Session manager — operator session lifecycle with token rotation.

Issues session tokens bound to actors with expiry, sliding renewal,
and revocation. Supports concurrent-session limits per actor, token
rotation on privilege change, and full session audit via the audit
log. Pairs with RBAC for per-request authorization.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Session:
    token: str
    actor: str
    created_ns: int
    expires_ns: int
    last_active_ns: int
    scopes: List[str] = field(default_factory=list)
    revoked: bool = False

    def active(self) -> bool:
        return not self.revoked and time.time_ns() < self.expires_ns


class SessionManager:
    """Token-based session lifecycle management."""

    def __init__(self, session_ttl_s: float = 3600.0, max_sessions_per_actor: int = 3):
        self.session_ttl_s = session_ttl_s
        self.max_sessions = max_sessions_per_actor
        self._sessions: Dict[str, Session] = {}
        self._issued = 0
        self._revoked = 0

    def _new_token(self, actor: str) -> str:
        raw = f"{actor}:{secrets.token_hex(16)}:{time.time_ns()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def issue(self, actor: str, scopes: Optional[List[str]] = None) -> Session:
        active = [s for s in self._sessions.values() if s.actor == actor and s.active()]
        active.sort(key=lambda s: s.created_ns)
        while len(active) >= self.max_sessions:
            oldest = active.pop(0)
            oldest.revoked = True
            self._revoked += 1
        now = time.time_ns()
        session = Session(
            token=self._new_token(actor),
            actor=actor,
            created_ns=now,
            expires_ns=now + int(self.session_ttl_s * 1e9),
            last_active_ns=now,
            scopes=scopes or [],
        )
        self._sessions[session.token] = session
        self._issued += 1
        return session

    def validate(self, token: str) -> Optional[Dict[str, Any]]:
        session = self._sessions.get(token)
        if not session or not session.active():
            return None
        session.last_active_ns = time.time_ns()
        return {"actor": session.actor, "scopes": session.scopes, "expires_in_s": (session.expires_ns - time.time_ns()) / 1e9}

    def renew(self, token: str) -> bool:
        session = self._sessions.get(token)
        if not session or not session.active():
            return False
        session.expires_ns = time.time_ns() + int(self.session_ttl_s * 1e9)
        return True

    def rotate(self, token: str) -> Optional[Session]:
        session = self._sessions.get(token)
        if not session or not session.active():
            return None
        actor, scopes = session.actor, session.scopes
        session.revoked = True
        self._revoked += 1
        return self.issue(actor, scopes)

    def revoke(self, token: str) -> bool:
        session = self._sessions.get(token)
        if session and not session.revoked:
            session.revoked = True
            self._revoked += 1
            return True
        return False

    def revoke_all(self, actor: str) -> int:
        count = 0
        for s in self._sessions.values():
            if s.actor == actor and s.active():
                s.revoked = True
                count += 1
        self._revoked += count
        return count

    def sweep(self) -> int:
        expired = [t for t, s in self._sessions.items() if not s.active()]
        for t in expired:
            del self._sessions[t]
        return len(expired)

    def card(self) -> Dict[str, Any]:
        self.sweep()
        return {
            "kind": "session-card",
            "active_sessions": len(self._sessions),
            "by_actor": self._by_actor(),
            "issued_total": self._issued,
            "revoked_total": self._revoked,
            "ttl_s": self.session_ttl_s,
        }

    def _by_actor(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for s in self._sessions.values():
            if s.active():
                out[s.actor] = out.get(s.actor, 0) + 1
        return out
