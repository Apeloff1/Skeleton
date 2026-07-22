from __future__ import annotations
"""
Mishima Zaibatsu-style defensive & security measures.
Militarized corporate posture: detect, freeze, isolate, report to Emperor (user).
"""

import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ThreatEvent:
    threat_id: str
    category: str  # injection | quota_abuse | isolation_breach | anomaly | integrity
    severity: str  # low | medium | high | critical
    detail: Dict[str, Any]
    action_taken: str
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


try:
    from gameforge.enterprise.zaibatsu_security import SECURITY as APP_SECURITY
except Exception:
    APP_SECURITY = None


class ZaibatsuSecurity:
    """
    Defensive measures:
      - input anomaly flags
      - freeze mode under critical threat
      - integrity checksums for twin tails
      - isolation enforcement helper
      - kill-switch report to user
    """

    def __init__(self):
        self.threats: List[ThreatEvent] = []
        self.frozen: bool = False
        self.freeze_reason: Optional[str] = None
        self.integrity_chain: List[str] = []

    def _record(self, category: str, severity: str, detail: dict, action: str) -> ThreatEvent:
        t = ThreatEvent(
            threat_id=str(uuid.uuid4())[:10],
            category=category,
            severity=severity,
            detail=detail,
            action_taken=action,
        )
        self.threats.append(t)
        if len(self.threats) > 2000:
            self.threats = self.threats[-2000:]
        if severity == "critical":
            self.frozen = True
            self.freeze_reason = category
        return t

    def inspect_input(self, text: str) -> Dict[str, Any]:
        t = text or ""
        flags = []
        # crude injection / prompt-override patterns
        for pat in ("ignore previous", "disregard laws", "you are now", "system prompt", "override seal"):
            if pat in t.lower():
                flags.append(pat)
        if flags:
            ev = self._record("injection", "high", {"flags": flags, "sample": t[:160]}, "block_and_report")
            if APP_SECURITY is not None:
                APP_SECURITY.inspect_text(t)
            return {"ok": False, "blocked": True, "threat": ev.to_dict()}
        return {"ok": True, "blocked": False}

    def note_isolation_breach(self, reader: str, owner: str, surface: str) -> ThreatEvent:
        return self._record(
            "isolation_breach",
            "high",
            {"reader": reader, "owner": owner, "surface": surface},
            "deny_and_audit",
        )

    def note_quota_abuse(self, unit_id: str, metric: str) -> ThreatEvent:
        return self._record(
            "quota_abuse",
            "medium",
            {"unit_id": unit_id, "metric": metric},
            "soft_then_hard_block",
        )

    def push_integrity(self, payload: str) -> str:
        prev = self.integrity_chain[-1] if self.integrity_chain else "GENESIS"
        h = hashlib.sha256((prev + payload).encode()).hexdigest()[:32]
        self.integrity_chain.append(h)
        if len(self.integrity_chain) > 5000:
            self.integrity_chain = self.integrity_chain[-5000:]
        return h

    def unfreeze(self, emperor_seal: bool = False) -> Dict[str, Any]:
        if not emperor_seal:
            return {"ok": False, "error": "requires_emperor_seal"}
        self.frozen = False
        self.freeze_reason = None
        return {"ok": True, "frozen": False}

    def status(self) -> Dict[str, Any]:
        return {
            "frozen": self.frozen,
            "freeze_reason": self.freeze_reason,
            "threats": len(self.threats),
            "critical": sum(1 for t in self.threats if t.severity == "critical"),
            "integrity_height": len(self.integrity_chain),
            "tail": [t.to_dict() for t in self.threats[-5:]],
        }
