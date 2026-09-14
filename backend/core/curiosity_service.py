"""Operational service boundary for the Curiosity subsystem."""
from __future__ import annotations

import os
from pathlib import Path
import threading
from typing import Any

from core.curiosity_engine import Researcher
from core.curiosity_research_pipeline import default_ensemble_researcher
from core.idle_curiosity_runtime import IdleCuriosityRuntime
from core.verified_curiosity import VerifiedCuriosityEngine


class CuriosityService:
    def __init__(self, root: str | Path, *, researcher: Researcher | None = None) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.engine = VerifiedCuriosityEngine(self.root)
        self.researcher = researcher or default_ensemble_researcher()
        self.runtime = IdleCuriosityRuntime(
            self.engine, self.researcher,
            idle_threshold_seconds=float(os.environ.get("CURIOSITY_IDLE_SECONDS", "90")),
            poll_seconds=float(os.environ.get("CURIOSITY_POLL_SECONDS", "5")),
            cycle_cooldown_seconds=float(os.environ.get("CURIOSITY_CYCLE_COOLDOWN_SECONDS", "30")),
            max_cycles_per_idle_window=int(os.environ.get("CURIOSITY_MAX_CYCLES_PER_IDLE", "4")),
            minimum_score=float(os.environ.get("CURIOSITY_MIN_SCORE", "0.18")),
        )

    @property
    def enabled(self) -> bool:
        return os.environ.get("CURIOSITY_IDLE_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}

    def start(self) -> bool: return self.runtime.start() if self.enabled else False
    def stop(self) -> bool: return self.runtime.stop()

    def observe(self, prompt: str, *, user_scope: str = "default", signal_key: str | None = None) -> dict[str, Any]:
        signal = self.engine.observe_prompt(prompt, user_scope=user_scope, signal_key=signal_key)
        self.runtime.mark_activity()
        return {"signal_id": signal.id, "subject": signal.subject, "keywords": list(signal.keywords), "observed_at": signal.observed_at}

    def frontier(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return [{"subject": t.subject, "keywords": t.keywords, "prompt_count": t.prompt_count,
                 "research_count": t.research_count, "unresolved_count": t.unresolved_count,
                 "last_prompt_at": t.last_prompt_at, "last_researched_at": t.last_researched_at,
                 "last_record_id": t.last_record_id, "score": score, "reason": reason}
                for t, score, reason in self.engine.frontier(limit=limit)]

    def search(self, query: str, *, limit: int = 8) -> dict[str, Any]:
        records = self.engine.fabric.search(query, limit=limit)
        return {"query": query, "count": len(records),
                "records": [{"id": r.id, "subject": r.subject, "title": r.title, "summary": r.summary,
                              "claims": list(r.claims), "questions": list(r.questions), "contradictions": list(r.contradictions),
                              "evidence": [{"source": e.source, "locator": e.locator, "confidence": e.confidence, "observed_at": e.observed_at} for e in r.evidence],
                              "tags": list(r.tags), "confidence": r.confidence, "novelty": r.novelty,
                              "created_at": r.created_at, "digest": r.digest} for r in records],
                "orientation": self.engine.orientation_pack(query, limit=min(limit, 8))}

    async def run_now(self) -> dict[str, Any]: return await self.engine.run_once(self.researcher, minimum_score=self.runtime.minimum_score)
    def run_now_sync(self) -> dict[str, Any]: return self.runtime.run_cycle_now()

    def status(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "runtime": self.runtime.snapshot(), "engine": self.engine.stats(),
                "verification": self.engine.verification_status(), "frontier": self.frontier(limit=10)}


_SINGLETON: CuriosityService | None = None
_SINGLETON_LOCK = threading.Lock()


def curiosity_service(root: str | Path | None = None) -> CuriosityService:
    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is None:
            default_root = Path(__file__).resolve().parents[1] / ".runtime" / "curiosity"
            selected = Path(root or os.environ.get("CURIOSITY_DATA_ROOT", default_root))
            _SINGLETON = CuriosityService(selected)
        return _SINGLETON


def reset_curiosity_service_for_tests() -> None:
    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is not None: _SINGLETON.stop()
        _SINGLETON = None
