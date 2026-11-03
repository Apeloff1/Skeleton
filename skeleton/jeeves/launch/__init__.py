"""Launch-ready local AI session and app integration facade.

Provides a single entry point the app can call at launch to:
  - start a game-building session
  - run the full pipeline
  - distill results into knowledge cards
  - retrieve prior knowledge for better builds

Immediately usable. Fail-closed.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import time
import uuid

from .ai.conductor import AIGameStudioConductor, run_launch_pipeline
from .game.builders import LocalAIGameBuilder
from .distill.engine import DistillationEngine, KnowledgeCard


class LaunchSession:
    """One local AI game-building session."""

    def __init__(self, brief: str, era: str = "HOUSE_ERA") -> None:
        self.session_id = str(uuid.uuid4())[:8]
        self.brief = brief
        self.era = era
        self.created_at = time.time()
        self.conductor = AIGameStudioConductor(era=era)
        self.builder = LocalAIGameBuilder()
        self.distiller = DistillationEngine(era=era)
        self.result: Optional[Dict[str, Any]] = None
        self.cards: List[KnowledgeCard] = []

    def run(self) -> Dict[str, Any]:
        """Execute the full pipeline and distill knowledge."""
        self.result = self.conductor.run(self.brief)
        self.cards = self.distiller.absorb_pipeline_result(self.result)
        # Also build a concrete artifact set via the builders
        title = self.result.get("stages", [{}])[0].get("artifacts", {}).get("spec", {}).get("title", self.brief[:40])
        concrete = self.builder.build_full(title)
        self.result["concrete"] = concrete
        self.result["session_id"] = self.session_id
        self.result["cards_distilled"] = len(self.cards)
        return self.result

    def status(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "brief": self.brief[:80],
            "era": self.era,
            "ran": self.result is not None,
            "ok": bool(self.result and self.result.get("ok")),
            "fidelity": self.result.get("fidelity") if self.result else None,
            "cards": len(self.cards),
            "ready_for_launch": bool(self.result and self.result.get("ready_for_launch")),
        }


class LaunchAppFacade:
    """
    Single facade the app calls at launch.

    Usage:
        facade = LaunchAppFacade()
        session = facade.start("A dark metroidvania where the player absorbs enemy abilities")
        result = session.run()
        print(result["ready_for_launch"])
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, LaunchSession] = {}
        self._global_distiller = DistillationEngine()

    def start(self, brief: str, era: str = "HOUSE_ERA") -> LaunchSession:
        if not brief or not brief.strip():
            raise ValueError("brief required")
        session = LaunchSession(brief.strip(), era=era)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[LaunchSession]:
        return self._sessions.get(session_id)

    def list_sessions(self) -> List[Dict[str, Any]]:
        return [s.status() for s in self._sessions.values()]

    def run_and_distill(self, brief: str, era: str = "HOUSE_ERA") -> Dict[str, Any]:
        """One-shot: start, run, distill, return result."""
        session = self.start(brief, era)
        result = session.run()
        # Merge cards into global store
        for card in session.cards:
            self._global_distiller._store[card.card_id] = card
        return result

    def knowledge(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        return [c.to_dict() for c in self._global_distiller.query(kind)]

    def health(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "sessions": len(self._sessions),
            "knowledge_cards": self._global_distiller.count(),
            "schema": "skeleton.jeeves.launch.facade.v1",
        }


# Module-level convenience for immediate import
_facade: Optional[LaunchAppFacade] = None


def get_facade() -> LaunchAppFacade:
    global _facade
    if _facade is None:
        _facade = LaunchAppFacade()
    return _facade


def launch_build(brief: str, era: str = "HOUSE_ERA") -> Dict[str, Any]:
    """One-line entry point for the app at launch."""
    return get_facade().run_and_distill(brief, era)
