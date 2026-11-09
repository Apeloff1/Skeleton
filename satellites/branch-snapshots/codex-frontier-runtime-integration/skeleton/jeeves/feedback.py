"""Feedback loop — explicit user signals that feed the assessment engine.

Learners give thumbs up/down or corrections; the collector records them
per session, with an optional sink so assessments can fold the signals
into SkillModel confidence directly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from skeleton.kernel.errors import KernelError


class FeedbackError(KernelError):
    code = "JEE.FEEDBACK"


class FeedbackKind(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    CORRECTION = "CORRECTION"


@dataclass(frozen=True)
class FeedbackRecord:
    session_id: str
    kind: FeedbackKind
    note: str = ""
    at: float = 0.0


class FeedbackCollector:
    """Per-session feedback register with optional live sink."""

    def __init__(self, *, sink: Optional[Callable[[FeedbackRecord], None]] = None) -> None:
        self._sink = sink
        self._records: List[FeedbackRecord] = []

    def log(
        self, session_id: str, kind: FeedbackKind, *, note: str = ""
    ) -> FeedbackRecord:
        record = FeedbackRecord(
            session_id=session_id, kind=kind, note=note, at=time.time()
        )
        self._records.append(record)
        if self._sink is not None:
            self._sink(record)
        return record

    def for_session(self, session_id: str) -> Tuple[FeedbackRecord, ...]:
        return tuple(r for r in self._records if r.session_id == session_id)

    def summary(self, session_id: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for record in self.for_session(session_id):
            counts[record.kind.value] = counts.get(record.kind.value, 0) + 1
        return counts
