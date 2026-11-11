"""Full-stack ecosystem orchestrator.

Ties IntegratedStudio, security helpers, rate windows, and audit trail into a
single session-scoped surface that the API and CLI can call.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid
from threading import Lock

# Production imports core.* directly; checkout tools import backend.core.*.
# Fail closed on unexpected package layouts and missing dependencies.
if __package__ == "core":
    from core.security_augmentation import bound_text, is_safe_identifier, redact_error
    from core.massive_upgrades import RateWindow, AuditTrail, health_probe
elif __package__ == "backend.core":
    from backend.core.security_augmentation import bound_text, is_safe_identifier, redact_error
    from backend.core.massive_upgrades import RateWindow, AuditTrail, health_probe
else:
    raise ImportError("unsupported ecosystem orchestrator package layout")

# Both the checkout and production Docker image vendor skeleton/.
# Import errors in the studio must propagate, never trigger a silent fallback.
from skeleton.jeeves.studio.integrated_studio import IntegratedStudio

MAX_SESSIONS = 256
_TERMINAL_STATUSES = frozenset({"sealed", "incomplete", "failed"})


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
        self._sessions_lock = Lock()
        self.studio = IntegratedStudio()
        # The studio mutates its era and pipeline state; admit one run at a time.
        self._run_lock = Lock()

    def create_session(self, brief: str, era: str = "ash", actor: str = "api") -> dict[str, Any]:
        brief = bound_text(brief, max_len=8000)
        if len(brief) < 4:
            return {"ok": False, "reason": "brief_too_short"}
        if era and not is_safe_identifier(era):
            return {"ok": False, "reason": "invalid_era"}
        with self._sessions_lock:
            if not self.rate.allow(actor):
                return {"ok": False, "reason": "rate_limited"}
            # Bound in-memory session/export custody. Evict completed work only,
            # oldest first; never discard a created or running session.
            if len(self.sessions) >= MAX_SESSIONS:
                for old_id, old_session in tuple(self.sessions.items()):
                    if old_session.status in _TERMINAL_STATUSES:
                        del self.sessions[old_id]
                        if len(self.sessions) < MAX_SESSIONS:
                            break
                if len(self.sessions) >= MAX_SESSIONS:
                    return {"ok": False, "reason": "session_capacity"}
            session_id = uuid.uuid4().hex[:16]
            if session_id in self.sessions:
                return {"ok": False, "reason": "session_id_collision"}
            session = EcosystemSession(session_id=session_id, brief=brief, era=era or "ash")
            self.sessions[session_id] = session
            self.audit.record(actor, "session.create", session_id)
            return {"ok": True, "session_id": session_id, "era": session.era}

    def run(self, session_id: str, actor: str = "api") -> dict[str, Any]:
        if not is_safe_identifier(session_id):
            return {"ok": False, "reason": "invalid_session"}
        with self._sessions_lock:
            session = self.sessions.get(session_id)
            if session is None:
                return {"ok": False, "reason": "session_not_found"}
            if not self.rate.allow(actor):
                return {"ok": False, "reason": "rate_limited"}

        if not self._run_lock.acquire(blocking=False):
            return {"ok": False, "session_id": session_id, "reason": "studio_busy"}
        try:
            with self._sessions_lock:
                if session.status != "created":
                    return {"ok": False, "session_id": session_id, "reason": "session_already_run"}
                session.status = "running"
            self.studio.set_era(session.era)
            result = self.studio.run_pipeline(session.brief)
            with self._sessions_lock:
                session.result = result
                session.godot_files = list(result.get("godot_files") or [])
                session.status = "sealed" if result.get("ok") and result.get("sealed") else "incomplete"
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
            with self._sessions_lock:
                session.status = "failed"
                session.error = redact_error(exc)
                self.audit.record(actor, "session.fail", session_id)
            return {"ok": False, "session_id": session_id, "reason": "internal_error"}
        finally:
            self._run_lock.release()

    def status(self, session_id: str) -> dict[str, Any]:
        if not is_safe_identifier(session_id):
            return {"ok": False, "reason": "invalid_session"}
        with self._sessions_lock:
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
        with self._sessions_lock:
            session = self.sessions.get(session_id)
            if session is None:
                return {"ok": False, "reason": "session_not_found"}
            if not session.godot_files:
                return {"ok": False, "reason": "no_export"}
            return {"ok": True, "session_id": session_id, "files": [dict(item) for item in session.godot_files]}

    def list_sessions(self, limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(100, int(limit)))
        with self._sessions_lock:
            rows = list(self.sessions.values())[-limit:]
        return {
            "ok": True,
            "count": len(rows),
            "sessions": [
                {"session_id": s.session_id, "status": s.status, "era": s.era, "created_at": s.created_at}
                for s in rows
            ],
        }

    def session_count(self) -> int:
        with self._sessions_lock:
            return len(self.sessions)

    def health(self) -> dict[str, Any]:
        base = health_probe()
        base["sessions"] = self.session_count()
        base["studio"] = self.studio.status()
        return base


_ORCH: EcosystemOrchestrator | None = None
_ORCH_LOCK = Lock()


def get_orchestrator() -> EcosystemOrchestrator:
    global _ORCH
    with _ORCH_LOCK:
        if _ORCH is None:
            _ORCH = EcosystemOrchestrator()
        return _ORCH
