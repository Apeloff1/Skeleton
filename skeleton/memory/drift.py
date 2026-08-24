"""Persona drift detection — watch a persona wander from its anchor.

A CAG persona accumulates knowledge over time: facts are added, importance
scores shift, evictions fire. Nothing in the trinity currently notices when
the cumulative effect is a persona that no longer resembles its system
prompt — a support persona that has drifted into politics, a tutor persona
whose knowledge graph is now 80% trivia.

The drift detector keeps a fixed **anchor vector** (a term-frequency
fingerprint of the persona's system prompt, taken at registration) and
periodically compares it against a live fingerprint of the knowledge
graph. Drift is 1 − cosine(anchor, live), smoothed over snapshots so a
single odd addition doesn't trip the alarm.

When smoothed drift crosses the threshold, the detector publishes a
``memory.persona.drifted`` event with the terms most responsible — the
dimensions of the drift, not just its size — so the operator can see
*which way* the persona wandered.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


def _fingerprint(text: str) -> Dict[str, float]:
    """L2-normalised term-frequency vector over meaningful words."""
    terms = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    freq: Dict[str, float] = {}
    for t in terms:
        freq[t] = freq.get(t, 0.0) + 1.0
    norm = math.sqrt(sum(v * v for v in freq.values())) or 1.0
    return {t: v / norm for t, v in freq.items()}


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    shared = set(a) & set(b)
    return sum(a[t] * b[t] for t in shared)


@dataclass
class DriftSnapshot:
    drift: float
    taken_at_index: int
    top_divergent_terms: List[str]


@dataclass
class PersonaWatch:
    """Drift state for one persona."""
    persona_id: str
    anchor: Dict[str, float]
    snapshots: List[DriftSnapshot] = field(default_factory=list)
    alerted: bool = False


class PersonaDriftDetector:
    """
    Tracks per-persona drift between the anchor prompt and live knowledge.

    Parameters
    ----------
    threshold:
        Smoothed drift that triggers an alert (0.5 = half the persona's
        effective vocabulary has rotated).
    smoothing:
        EMA weight on the newest snapshot; higher reacts faster.
    """

    def __init__(self, *, threshold: float = 0.5, smoothing: float = 0.3,
                 bus: Optional[EventBus] = None) -> None:
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold must be in (0, 1]")
        self.threshold = threshold
        self.smoothing = smoothing
        self._watches: Dict[str, PersonaWatch] = {}
        self._bus = bus

    def register(self, persona_id: str, system_prompt: str) -> PersonaWatch:
        watch = PersonaWatch(persona_id=persona_id, anchor=_fingerprint(system_prompt))
        self._watches[persona_id] = watch
        return watch

    def check(self, persona_id: str, live_text: str) -> DriftSnapshot:
        """Take a snapshot of the persona's current knowledge text."""
        watch = self._watches.get(persona_id) or self.register(persona_id, live_text)
        live = _fingerprint(live_text)
        raw_drift = 1.0 - _cosine(watch.anchor, live)
        prior = watch.snapshots[-1].drift if watch.snapshots else raw_drift
        smoothed = (1 - self.smoothing) * prior + self.smoothing * raw_drift

        # terms present in live but absent/weak in anchor, by contribution
        divergence = sorted(
            (t for t in live if watch.anchor.get(t, 0.0) < live[t] * 0.5),
            key=lambda t: -live[t],
        )[:5]

        snapshot = DriftSnapshot(
            drift=smoothed,
            taken_at_index=len(watch.snapshots),
            top_divergent_terms=divergence,
        )
        watch.snapshots.append(snapshot)

        if smoothed >= self.threshold and not watch.alerted:
            watch.alerted = True
            if self._bus:
                self._bus.publish(
                    DomainEvent(
                        topic="memory.persona.drifted",
                        payload={
                            "persona_id": persona_id,
                            "drift": round(smoothed, 4),
                            "threshold": self.threshold,
                            "divergent_terms": divergence,
                            "snapshots": len(watch.snapshots),
                        },
                        correlation_id=f"drift_{persona_id}",
                    )
                )
        elif smoothed < self.threshold * 0.8:
            watch.alerted = False  # hysteresis: re-arm well below the line
        return snapshot

    def stats(self) -> Dict[str, Any]:
        return {
            "personas_watched": len(self._watches),
            "alerted": [pid for pid, w in self._watches.items() if w.alerted],
            "mean_drift": round(
                sum(w.snapshots[-1].drift for w in self._watches.values() if w.snapshots)
                / max(sum(1 for w in self._watches.values() if w.snapshots), 1), 4
            ),
        }
