"""
Skeleton Contexts — The Oracle Matrix

Oracle, Prophet, and Seer abilities woven into a matrix of
ever-changing strings of fate. The matrix reads the live state of
every context plane and projects outcome trajectories — guiding the
user toward a finished product at max capability and quality.

Three sight-lines:

- ORACLE  (the what):  reads current state — queue scorecards, backlog
           density, plan progress — and names the most probable next
           material event.
- PROPHET (the when):  extrapolates trajectories — regression over
           recent cycles — and forecasts when the active plan will
           complete and at what quality band.
- SEER    (the path):  enumerates alternative futures — permutations
           of remaining steps — and ranks the strings of fate by
           expected terminal quality, marking the golden path.

The matrix is ever-changing: every observation re-weaves the strings.
"""

from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class FateString:
    """One projected future trajectory."""
    string_id: str
    path: List[str]                 # ordered step descriptions
    terminal_quality: float         # predicted quality at completion
    probability: float              # likelihood of this future
    completion_eta_cycles: float
    golden: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "string_id": self.string_id,
            "path": self.path[:6],
            "terminal_quality": round(self.terminal_quality, 3),
            "probability": round(self.probability, 3),
            "eta_cycles": round(self.completion_eta_cycles, 1),
            "golden": self.golden,
        }


@dataclass
class OracleReading:
    """One full matrix reading: oracle + prophet + seer."""
    read_at: float
    next_event: str                 # oracle: most probable next event
    next_event_probability: float
    completion_forecast: Dict[str, Any]  # prophet: eta + quality band
    strings: List[FateString]       # seer: ranked futures
    golden_path: Optional[FateString]

    def narrate(self) -> str:
        """Positive, user-facing narration of the reading."""
        lines = [f"Reading the threads: {self.next_event} is next ({self.next_event_probability:.0%} likely)."]
        if self.golden_path:
            lines.append(
                f"The golden path runs through {len(self.golden_path.path)} steps "
                f"and lands at {self.golden_path.terminal_quality:.0%} quality "
                f"in about {self.golden_path.completion_eta_cycles:.0f} cycles."
            )
        return " ".join(lines)


class OracleMatrix:
    """Oracle/Prophet/Seer prediction matrix over the context fabric."""

    MAX_STRINGS = 24  # cap on enumerated futures (seer bound)

    def __init__(self, queue: Optional[Any] = None, planning: Optional[Any] = None,
                 backlog: Optional[Any] = None, workorders: Optional[Any] = None,
                 bus: Optional[EventBus] = None):
        self._queue = queue
        self._planning = planning
        self._backlog = backlog
        self._workorders = workorders
        self._bus = bus
        self._history: List[Dict[str, Any]] = []
        self._stats = {"readings": 0, "golden_found": 0, "predictions_made": 0}

    # --- ORACLE: the what ---------------------------------------------------

    def _oracle(self) -> tuple[str, float]:
        """Most probable next material event, from queue scorecards."""
        if self._queue is None or not self._queue.items:
            return ("conversation continues", 0.5)
        top = max(self._queue.items, key=lambda i: i.blended)
        kind_names = {
            "workorder": "external work executes",
            "plan_step": "next plan step begins",
            "backlog_resume": "unfinished work resurfaces",
            "response": "response continues",
        }
        return (kind_names.get(top.kind, "conversation continues"), min(0.99, top.blended))

    # --- PROPHET: the when ---------------------------------------------------

    def _prophet(self) -> Dict[str, Any]:
        """Forecast completion time and quality band for the active plan."""
        if self._planning is None or not self._planning.active_plans():
            return {"eta_cycles": 0, "quality_band": "steady", "confidence": 0.5}
        plan = self._planning.active_plans()[0]
        remaining = [s for s in plan.steps if s.status == "pending"]
        cost = sum(s.estimated_cost for s in remaining) or 1.0
        progress = plan.progress()

        # Trajectory: quality improves as progress rises, tapering near the end
        projected_quality = min(1.0, 0.6 + 0.4 * (progress + 0.1))
        band = "golden" if projected_quality >= 0.9 else "strong" if projected_quality >= 0.75 else "steady"

        # Regression over history for confidence
        if len(self._history) >= 3:
            recent = [h.get("progress", 0.0) for h in self._history[-5:]]
            trend = (recent[-1] - recent[0]) / max(1, len(recent) - 1)
            confidence = min(0.95, 0.5 + abs(trend))
            if trend > 0:
                eta = (1.0 - progress) / max(0.01, trend)
            else:
                eta = cost
        else:
            confidence = 0.5
            eta = cost

        self._history.append({"progress": progress, "ts": time.time()})
        self._stats["predictions_made"] += 1
        return {
            "eta_cycles": round(eta, 1),
            "projected_quality": round(projected_quality, 3),
            "quality_band": band,
            "confidence": round(confidence, 3),
        }

    # --- SEER: the path ------------------------------------------------------

    def _seer(self) -> List[FateString]:
        """Enumerate and rank alternative futures for remaining plan steps."""
        if self._planning is None or not self._planning.active_plans():
            return []
        plan = self._planning.active_plans()[0]
        remaining = [s for s in plan.steps if s.status == "pending"]
        if not remaining:
            return []

        # Respect dependency order but permute free steps; cap enumeration
        descs = [s.description for s in remaining]
        if len(descs) > 5:
            # Too many futures: sample the field instead of enumerating
            orderings = [descs, list(reversed(descs)), sorted(descs)]
        else:
            orderings = list(itertools.permutations(descs))[: self.MAX_STRINGS]

        strings: List[FateString] = []
        for i, ordering in enumerate(orderings):
            cost = sum(
                next((s.estimated_cost for s in remaining if s.description == d), 1.0)
                for d in ordering
            )
            # Terminal quality: connector steps done early ground the rest better
            connector_first = sum(
                1 for d in ordering[: max(1, len(ordering) // 2)]
                if any(s.description == d and s.connector for s in remaining)
            )
            quality = min(1.0, 0.55 + 0.15 * connector_first + 0.05 * len(ordering))
            probability = 1.0 / (i + 1)  # front orderings more likely
            strings.append(FateString(
                string_id=f"fate-{i}",
                path=list(ordering),
                terminal_quality=quality,
                probability=probability,
                completion_eta_cycles=cost,
            ))

        strings.sort(key=lambda s: s.terminal_quality * s.probability, reverse=True)
        if strings:
            strings[0].golden = True
            self._stats["golden_found"] += 1
        return strings

    # --- Full reading ---------------------------------------------------------

    def read(self) -> OracleReading:
        """One full matrix reading, re-weaving all strings of fate."""
        self._stats["readings"] += 1
        next_event, prob = self._oracle()
        forecast = self._prophet()
        strings = self._seer()
        golden = next((s for s in strings if s.golden), None)

        reading = OracleReading(
            read_at=time.time(),
            next_event=next_event,
            next_event_probability=prob,
            completion_forecast=forecast,
            strings=strings,
            golden_path=golden,
        )

        if self._bus:
            self._bus.publish(DomainEvent(
                topic="contexts.oracle.reading",
                payload={
                    "next_event": next_event,
                    "probability": prob,
                    "quality_band": forecast.get("quality_band"),
                    "strings": len(strings),
                },
                correlation_id=f"oracle_{self._stats['readings']}",
            ))
        return reading

    def guide(self) -> str:
        """User-facing guidance toward the finished product."""
        return self.read().narrate()

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)
