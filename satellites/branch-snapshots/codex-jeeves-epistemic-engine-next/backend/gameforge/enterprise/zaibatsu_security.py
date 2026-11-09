from __future__ import annotations
"""
App-wide Mishima Zaibatsu security.

Militarized corporate defensive posture across API, runtime, memory, and VOX:
  - Global freeze / Emperor unfreeze
  - Request inspection (injection, path abuse)
  - Rate / anomaly budgets
  - Integrity chain for sensitive writes
  - Tenant isolation assertions
  - Audit spine
  - Kill-switch report to boardroom hooks
"""

import hashlib
import re
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional, Set


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# Patterns treated as hostile against the Zaibatsu perimeter
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous",
    r"disregard\s+(your\s+)?(laws|instructions|rules)",
    r"you\s+are\s+now\s+",
    r"system\s+prompt",
    r"override\s+seal",
    r"emperor\s+seal\s+forged",
    r"<\s*script",
    r"union\s+select",
    r"\.\./\.\.",
    r"drop\s+table",
    r"__import__\s*\(",
    r"eval\s*\(\s*['\"]",
]

SENSITIVE_PATHS = {
    "/exocortex/zaibatsu",
    "/exocortex/pfc",
    "/exocortex/studio",
    "/exocortex/dna",
    "/math",
    "/scim",
    "/system",
}


@dataclass
class SecurityEvent:
    event_id: str
    category: str
    severity: str
    path: str = ""
    user_id: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)
    action: str = ""
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


class AppWideZaibatsuSecurity:
    """
    Singleton-style app security fabric (one instance per process).
    """

    def __init__(
        self,
        *,
        max_events: int = 5000,
        rate_limit_per_minute: int = 120,
        anomaly_burst: int = 30,
    ):
        self.frozen: bool = False
        self.freeze_reason: Optional[str] = None
        self.events: Deque[SecurityEvent] = deque(maxlen=max_events)
        self.integrity_chain: List[str] = ["GENESIS_ZAIBATSU"]
        self.rate_limit_per_minute = rate_limit_per_minute
        self.anomaly_burst = anomaly_burst
        # user_id -> timestamps of recent requests
        self._hits: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=500))
        self._blocked_users: Set[str] = set()
        self._path_denies: Dict[str, int] = defaultdict(int)
        self.injection_re = [re.compile(p, re.I) for p in INJECTION_PATTERNS]
        self.listeners: List[Callable[[SecurityEvent], None]] = []

    # ----- core state --------------------------------------------------------

    def _emit(self, category: str, severity: str, action: str, **kw) -> SecurityEvent:
        ev = SecurityEvent(
            event_id=str(uuid.uuid4())[:12],
            category=category,
            severity=severity,
            action=action,
            path=kw.pop("path", ""),
            user_id=kw.pop("user_id", ""),
            detail=kw,
        )
        self.events.append(ev)
        if severity == "critical":
            self.frozen = True
            self.freeze_reason = category
        for fn in self.listeners:
            try:
                fn(ev)
            except Exception:
                pass
        return ev

    def on_event(self, fn: Callable[[SecurityEvent], None]):
        self.listeners.append(fn)

    # ----- freeze ------------------------------------------------------------

    def freeze(self, reason: str, *, critical: bool = True) -> Dict[str, Any]:
        self.frozen = True
        self.freeze_reason = reason
        sev = "critical" if critical else "high"
        ev = self._emit("freeze", sev, "global_freeze", reason=reason)
        return {"frozen": True, "reason": reason, "event": ev.to_dict()}

    def unfreeze(self, *, emperor_seal: bool = False, actor: str = "") -> Dict[str, Any]:
        if not emperor_seal:
            self._emit("unfreeze_denied", "high", "require_emperor_seal", actor=actor)
            return {"ok": False, "error": "requires_emperor_seal"}
        self.frozen = False
        self.freeze_reason = None
        ev = self._emit("unfreeze", "medium", "emperor_unfreeze", actor=actor)
        return {"ok": True, "frozen": False, "event": ev.to_dict()}

    # ----- integrity ---------------------------------------------------------

    def push_integrity(self, payload: str) -> str:
        prev = self.integrity_chain[-1]
        h = hashlib.sha256((prev + "|" + payload).encode()).hexdigest()[:40]
        self.integrity_chain.append(h)
        if len(self.integrity_chain) > 10000:
            self.integrity_chain = self.integrity_chain[-10000:]
        return h

    def verify_integrity_tail(self, n: int = 5) -> Dict[str, Any]:
        return {
            "height": len(self.integrity_chain),
            "tail": self.integrity_chain[-n:],
        }

    # ----- inspection --------------------------------------------------------

    def inspect_text(self, text: str, *, user_id: str = "", path: str = "") -> Dict[str, Any]:
        if self.frozen:
            return {
                "ok": False,
                "blocked": True,
                "reason": "global_freeze",
                "freeze_reason": self.freeze_reason,
            }
        if user_id and user_id in self._blocked_users:
            return {"ok": False, "blocked": True, "reason": "user_blocked"}

        flags = []
        t = text or ""
        for cre in self.injection_re:
            if cre.search(t):
                flags.append(cre.pattern)
        if flags:
            ev = self._emit(
                "injection",
                "high",
                "block_request",
                path=path,
                user_id=user_id,
                flags=flags,
                sample=t[:200],
            )
            return {"ok": False, "blocked": True, "reason": "injection", "event": ev.to_dict()}
        return {"ok": True, "blocked": False}

    def inspect_path(self, path: str, *, user_id: str = "", method: str = "GET") -> Dict[str, Any]:
        if self.frozen and not path.endswith("/zaibatsu/status") and "/unfreeze" not in path:
            return {
                "ok": False,
                "blocked": True,
                "reason": "global_freeze",
                "freeze_reason": self.freeze_reason,
            }
        # path traversal
        if ".." in path or "%2e%2e" in path.lower():
            ev = self._emit("path_abuse", "high", "deny", path=path, user_id=user_id)
            self._path_denies[path] += 1
            return {"ok": False, "blocked": True, "reason": "path_abuse", "event": ev.to_dict()}
        return {"ok": True, "blocked": False, "sensitive": any(path.startswith(s) for s in SENSITIVE_PATHS)}

    # ----- rate / anomaly ----------------------------------------------------

    def check_rate(self, user_id: str, *, path: str = "") -> Dict[str, Any]:
        now = time.time()
        q = self._hits[user_id or "anon"]
        q.append(now)
        # count last 60s
        recent = [t for t in q if now - t <= 60.0]
        if len(recent) > self.rate_limit_per_minute:
            ev = self._emit(
                "rate_limit",
                "medium",
                "throttle",
                user_id=user_id,
                path=path,
                count=len(recent),
            )
            return {"ok": False, "blocked": True, "reason": "rate_limit", "event": ev.to_dict()}
        if len(recent) > self.anomaly_burst and len([t for t in q if now - t <= 5.0]) > self.anomaly_burst:
            ev = self._emit(
                "anomaly_burst",
                "high",
                "temp_block",
                user_id=user_id,
                path=path,
            )
            self._blocked_users.add(user_id)
            return {"ok": False, "blocked": True, "reason": "anomaly_burst", "event": ev.to_dict()}
        return {"ok": True, "blocked": False, "rpm": len(recent)}

    def unblock_user(self, user_id: str, *, emperor_seal: bool = False) -> Dict[str, Any]:
        if not emperor_seal:
            return {"ok": False, "error": "requires_emperor_seal"}
        self._blocked_users.discard(user_id)
        self._emit("unblock_user", "medium", "emperor_unblock", user_id=user_id)
        return {"ok": True, "user_id": user_id}

    # ----- isolation ---------------------------------------------------------

    def assert_isolation(
        self,
        reader_unit: str,
        owner_unit: str,
        surface: str,
        *,
        can_access_fn: Optional[Callable[[str, str, str], bool]] = None,
    ) -> Dict[str, Any]:
        if reader_unit == owner_unit:
            return {"ok": True}
        allowed = False
        if can_access_fn:
            try:
                allowed = bool(can_access_fn(reader_unit, owner_unit, surface))
            except Exception as e:
                self._emit("isolation_error", "medium", "deny", error=str(e))
                return {"ok": False, "blocked": True, "reason": "isolation_error"}
        if not allowed:
            ev = self._emit(
                "isolation_breach",
                "high",
                "deny_and_audit",
                reader=reader_unit,
                owner=owner_unit,
                surface=surface,
            )
            return {"ok": False, "blocked": True, "reason": "isolation_breach", "event": ev.to_dict()}
        return {"ok": True}

    # ----- gate used by middleware -------------------------------------------

    def gate_request(
        self,
        *,
        path: str,
        method: str = "GET",
        user_id: str = "",
        body_text: str = "",
    ) -> Dict[str, Any]:
        """
        Single entry for FastAPI middleware / routers.
        """
        p = self.inspect_path(path, user_id=user_id, method=method)
        if p.get("blocked"):
            return p
        r = self.check_rate(user_id, path=path)
        if r.get("blocked"):
            return r
        if body_text:
            t = self.inspect_text(body_text, user_id=user_id, path=path)
            if t.get("blocked"):
                return t
        # integrity tick for sensitive writes
        if method.upper() in ("POST", "PUT", "PATCH", "DELETE") and p.get("sensitive"):
            digest = self.push_integrity(f"{method}:{path}:{user_id}:{body_text[:200]}")
            return {"ok": True, "blocked": False, "integrity": digest, "sensitive": True}
        return {"ok": True, "blocked": False, "sensitive": p.get("sensitive", False)}

    def status(self) -> Dict[str, Any]:
        by_cat: Dict[str, int] = defaultdict(int)
        by_sev: Dict[str, int] = defaultdict(int)
        for e in self.events:
            by_cat[e.category] += 1
            by_sev[e.severity] += 1
        return {
            "frozen": self.frozen,
            "freeze_reason": self.freeze_reason,
            "events": len(self.events),
            "by_category": dict(by_cat),
            "by_severity": dict(by_sev),
            "blocked_users": sorted(self._blocked_users),
            "integrity_height": len(self.integrity_chain),
            "integrity_tail": self.integrity_chain[-3:],
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "recent_events": [e.to_dict() for e in list(self.events)[-8:]],
        }


# Process-wide fabric
SECURITY = AppWideZaibatsuSecurity()
