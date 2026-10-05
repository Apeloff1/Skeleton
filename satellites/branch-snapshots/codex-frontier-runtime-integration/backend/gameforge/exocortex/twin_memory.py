from __future__ import annotations
"""
Twin coverage for books, journals, diaries, logs, calendar — NEVER filtered.
Original path may filter; twin path is append-only complete truth.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from gameforge.exocortex.twin_logs import TwinHub, TwinEntry


# Canonical memory surfaces that must have twins
MEMORY_SURFACES = (
    "transcript",
    "schedule",
    "progress",
    "journal",
    "diary_memory",
    "diary_introspect",
    "diary_outrospect",
    "diary_retrospect",
    "patient",
    "psychology",
    "neuropsychology",
    "prospect",
    "executive_function",
    "interoception",
    "environmental",
    "cognitive_bias",
    "working_memory",
    "social_boundary",
    "skill_acquisition",
    "stimulus_response",
    "central_synthesis",
    "client_ledger",
    "fisherman",
    "guest",
    "building",
    "calendar_day",
    "era",
    "semantic",
    "neuro",
    "math",
    "system",
    "pfc",
    "jeeves",
    "judgement",
    "handoff",
)


class TwinMemoryService:
    """
    Single facade: every write to an original memory surface MUST twin.
    Twins are never filtered, never salience-gated, never RAS-dropped.
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.hub = TwinHub(user_id)
        # ensure extended streams exist
        for s in MEMORY_SURFACES:
            if s not in self.hub.books:
                from gameforge.exocortex.twin_logs import TwinLogBook
                self.hub.books[s] = TwinLogBook(user_id, s)

    def twin_write(
        self,
        surface: str,
        payload: Dict[str, Any],
        *,
        raw_text: str = "",
        original_filtered: bool = False,
        original_kept: bool = True,
        tags: Optional[List[str]] = None,
    ) -> TwinEntry:
        if surface not in self.hub.books:
            from gameforge.exocortex.twin_logs import TwinLogBook
            self.hub.books[surface] = TwinLogBook(self.user_id, surface)
        tags = list(tags or [])
        if "twin_never_filtered" not in tags:
            tags.append("twin_never_filtered")
        return self.hub.mirror(
            surface,
            payload,
            raw_text=raw_text,
            original_filtered=original_filtered,
            original_kept=original_kept,
            tags=tags,
        )

    def query(self, surface: str, **kwargs) -> List[Dict[str, Any]]:
        return self.hub.query(surface, **kwargs)

    def query_all(self, contains: str, n: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        out = {}
        for s in self.hub.books:
            rows = self.hub.books[s].query(contains=contains, n=n)
            if rows:
                out[s] = rows
        return out

    def overview(self) -> Dict[str, Any]:
        return {s: b.stats() for s, b in self.hub.books.items()}

    def assert_unfiltered_policy(self) -> Dict[str, Any]:
        return {
            "policy": "TWINS_NEVER_FILTERED",
            "surfaces": list(self.hub.books.keys()),
            "rule": "Original paths may RAS/salience filter; twin_write always appends full payload+raw_text.",
        }
