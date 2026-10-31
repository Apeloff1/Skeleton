"""Full-stack ecosystem orchestrator.

Ties IntegratedStudio, security helpers, rate windows, and audit trail into a
single session-scoped surface that the API and CLI can call.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

from backend.core.security_augmentation import bound_text, is_safe_identifier, redact_error
from backend.core.massive_upgrades import RateWindow, AuditTrail, health_probe

try:
    from skeleton.jeeves.studio.integrated_studio import IntegratedStudio
except Exception:  # pragma: no cover - import path differs by cwd
    from jeeves.studio.integrated_studio import IntegratedStudio  # type: ignore[no-redef]


@dataclass
class EcosystemSession:
    session_id: str
    brief: str
    era: str = "ash"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "created"
    result: dict[str, Any] | None = None
    godot_files: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None


class EcosystemOrchestrator:
    """Session-scoped conductor for the full studio pipeline."""

    def __init__(self) -> None:
        self.rate = RateWindow(limit=30, window_sec=60.0)
        self.audit = AuditTrail(max_entries=5000)
        self.sessions: dict[str, EcosystemSession] = {}
        self.studio = IntegratedStudio()

    def create_session(self, brief: str, era: str = "ash", actor: str = "api") -> dict[str, Any]:
        brief = bound_text(brief, max_len=8000)
        if len(brief) < 4:
            return {"ok": False, "reason": "brief_too_short"}
        if era and not is_safe_identifier(era):
            return {"ok": False, "reason": "invalid_era"}
        if not self.rate.allow(actor):
            return {"ok": False, "reason": "rate_limited"}

        session_id = uuid.uuid4().hex[:16]
        session = EcosystemSession(session_id=session_id, brief=brief, era=era or "ash")
        self.sessions[session_id] = session
        self.audit.record(actor, "session.create", session_id)
        return {"ok": True, "session_id": session_id, "era": session.era}

    def run(self, session_id: str, actor: str = "api") -> dict[str, Any]:
        if not is_safe_identifier(session_id):
            return {"ok": False, "reason": "invalid_session"}
        session = self.sessions.get(session_id)
        if session is None:
            return {"ok": False, "reason": "session_not_found"}
        if not self.rate.allow(actor):
            return {"ok": False, "reason": "rate_limited"}

        try:
            self.studio.set_era(session.era)
            result = self.studio.run_pipeline(session.brief)
            session.result = result
            session.godot_files = list(result.get("godot_files") or [])
            session.status = "sealed" if result.get("sealed") else "incomplete"
            session.error = None if result.get("ok") else result.get("reason")
            self.audit.record(actor, "session.run", f"{session_id}:{session.status}")
            return {
                "ok": bool(result.get("ok")),
                "session_id": session_id,
                "status": session.status,
                "sealed": result.get("sealed"),
                "era": result.get("era"),
                "mode": result.get("mode"),
                "rooms": result.get("rooms"),
                "tier": result.get("tier"),
                "godot_count": len(session.godot_files),
                "reason": result.get("reason"),
            }
        except Exception as exc:  # noqa: BLE001
            session.status = "failed"
            session.error = redact_error(exc)
            self.audit.record(actor, "session.fail", session_id)
            return {"ok": False, "session_id": session_id, "reason": "internal_error"}

    def status(self, session_id: str) -> dict[str, Any]:
        if not is_safe_identifier(session_id):
            return {"ok": False, "reason": "invalid_session"}
        session = self.sessions.get(session_id)
        if session is None:
            return {"ok": False, "reason": "session_not_found"}
        return {
            "ok": True,
            "session_id": session.session_id,
            "status": session.status,
            "era": session.era,
            "brief": session.brief[:240],
            "godot_count": len(session.godot_files),
            "created_at": session.created_at,
            "error": session.error,
        }

    def export_godot(self, session_id: str) -> dict[str, Any]:
        if not is_safe_identifier(session_id):
            return {"ok": False, "reason": "invalid_session"}
        session = self.sessions.get(session_id)
        if session is None:
            return {"ok": False, "reason": "session_not_found"}
        if not session.godot_files:
            return {"ok": False, "reason": "no_export"}
        return {"ok": True, "session_id": session_id, "files": session.godot_files}

    def list_sessions(self, limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(100, int(limit)))
        rows = list(self.sessions.values())[-limit:]
        return {
            "ok": True,
            "count": len(rows),
            "sessions": [
                {"session_id": s.session_id, "status": s.status, "era": s.era, "created_at": s.created_at}
                for s in rows
            ],
        }

    def health(self) -> dict[str, Any]:
        base = health_probe()
        base["sessions"] = len(self.sessions)
        base["studio"] = self.studio.status()
        return base


_ORCH: EcosystemOrchestrator | None = None


def get_orchestrator() -> EcosystemOrchestrator:
    global _ORCH
    if _ORCH is None:
        _ORCH = EcosystemOrchestrator()
    return _ORCH
