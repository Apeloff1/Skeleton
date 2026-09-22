"""Forgetting-curve scheduler — spaced repetition over episodic memory.

MAG stores episodes with an exponential decay model; this module decides
*when* each episode should be rehearsed to keep it above the retention
floor for the least total effort. It is the SM-2 family insight expressed
in the codebase's own vocabulary: the optimal moment to review is the
moment recall probability is about to cross the floor.

How it works
------------
1. Every scheduled episode carries a **stability** — how slowly its decay
   constant grows with each successful review (ease in the classic model).
2. The next review interval is computed as ``-ln(floor) * stability``:
   the time until recall probability hits the retention floor.
3. Reviews report outcomes (recalled / struggled / forgotten); stability
   grows on success and collapses on lapse, so hard episodes are reviewed
   sooner and easy ones drift apart.
4. ``due()`` returns the episodes whose review deadline has passed,
   ordered by urgency (most overdue first).

The scheduler is deterministic given the same clock: pass a clock callable
in tests for exact replay.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class ReviewCard:
    """Scheduling state for one episode."""
    episode_id: str
    stability: float = 3600.0          # seconds until P(recall) hits floor, at ease 1.0
    ease: float = 1.0                  # growth multiplier on successful review (>= 1.0)
    reviews: int = 0
    lapses: int = 0
    next_due: float = field(default_factory=time.time)
    last_reviewed: Optional[float] = None

    def interval(self, floor: float) -> float:
        """Seconds until recall probability crosses the retention floor."""
        return -math.log(floor) * self.stability * self.ease


class Outcome:
    RECALLED = "recalled"
    STRUGGLED = "struggled"
    FORGOTTEN = "forgotten"


class RepetitionScheduler:
    """
    Schedules MAG episode reviews against the forgetting curve.

    Parameters
    ----------
    floor:
        Retention floor (target recall probability), 0 < floor < 1.
        Reviews are due when P(recall) would drop below it.
    ease_growth / ease_shrink:
        Multiplicative ease adjustment per outcome.
    """

    def __init__(
        self,
        *,
        floor: float = 0.5,
        ease_growth: float = 1.3,
        ease_shrink: float = 0.5,
        bus: Optional[EventBus] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if not 0.0 < floor < 1.0:
            raise ValueError("floor must be in (0, 1)")
        self.floor = floor
        self.ease_growth = ease_growth
        self.ease_shrink = ease_shrink
        self._cards: Dict[str, ReviewCard] = {}
        self._bus = bus
        self._now = clock or time.time

    # ------------------------------------------------------------------
    # Enrollment and review
    # ------------------------------------------------------------------

    def enroll(self, episode_id: str, *, stability: float = 3600.0) -> ReviewCard:
        """Start tracking an episode. First review is due one interval out."""
        card = self._cards.get(episode_id)
        if card is None:
            card = ReviewCard(episode_id=episode_id, stability=stability)
            card.next_due = self._now() + card.interval(self.floor)
            self._cards[episode_id] = card
        return card

    def review(self, episode_id: str, outcome: str) -> ReviewCard:
        """
        Record a review outcome and reschedule.

        - RECALLED: stability grows by current ease; ease grows.
        - STRUGGLED: stability holds; ease unchanged; shorter next interval.
        - FORGOTTEN: stability collapses to base; ease shrinks; lapse counted.
        """
        card = self._cards.get(episode_id) or self.enroll(episode_id)
        now = self._now()
        card.reviews += 1
        card.last_reviewed = now

        if outcome == Outcome.RECALLED:
            card.stability *= card.ease
            card.ease *= self.ease_growth
        elif outcome == Outcome.STRUGGLED:
            pass  # stability and ease unchanged — same interval again
        elif outcome == Outcome.FORGOTTEN:
            card.stability = 3600.0
            card.ease = max(1.0, card.ease * self.ease_shrink)
            card.lapses += 1
        else:
            raise ValueError(f"unknown outcome {outcome!r}")

        card.next_due = now + card.interval(self.floor)

        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="memory.repetition.reviewed",
                    payload={
                        "episode_id": episode_id,
                        "outcome": outcome,
                        "stability": round(card.stability, 1),
                        "ease": round(card.ease, 3),
                        "next_due_in_s": round(card.next_due - now, 1),
                    },
                    correlation_id=f"srs_{episode_id}",
                )
            )
        return card

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def due(self, *, limit: int = 10) -> List[ReviewCard]:
        """Cards whose review deadline has passed, most overdue first."""
        now = self._now()
        overdue = [c for c in self._cards.values() if c.next_due <= now]
        overdue.sort(key=lambda c: c.next_due)
        return overdue[:limit]

    def retention(self, episode_id: str) -> float:
        """Current predicted recall probability for an episode."""
        card = self._cards.get(episode_id)
        if card is None or card.last_reviewed is None:
            return 1.0 if card is None else math.exp(
                -(self._now() - card.next_due + card.interval(self.floor))
                / max(card.stability * card.ease, 1e-9)
            )
        elapsed = self._now() - card.last_reviewed
        return math.exp(-elapsed / max(card.stability * card.ease, 1e-9))

    def stats(self) -> Dict[str, Any]:
        cards = list(self._cards.values())
        return {
            "cards": len(cards),
            "due_now": len([c for c in cards if c.next_due <= self._now()]),
            "total_reviews": sum(c.reviews for c in cards),
            "total_lapses": sum(c.lapses for c in cards),
            "mean_stability_h": round(
                sum(c.stability for c in cards) / len(cards) / 3600, 2
            ) if cards else 0.0,
        }
