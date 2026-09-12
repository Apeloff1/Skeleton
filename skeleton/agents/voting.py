"""Agent voting — structured ballots for mesh preference
(complements negotiation), plus the Diet time-boxed franchise.

Negotiation resolves consent; sometimes the mesh picks 1-of-N by
explicit ballot instead. Supports PLURALITY, RANKED (instant runoff),
and APPROVAL voting over named options.

The Diet (gameforge-rs ``crates/gf-gameforge/src/voting.rs``) is the
time-boxed franchise: a measure is proposed with options and a close
time; each sworn voter casts one ballot — one voice per measure, no
ballot ever changed. Tally is recomputed from the full roll on every
read. Plurality wins; ties go to the status quo (``options[0]``).

- :class:`Ballot` — agent + ordered/approved choices (elect API)
- :class:`Voting` — elect() returns winner + ballot count (unchanged)
- :class:`Diet` — propose / cast / tally / close (time-boxed franchise)
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from skeleton.kernel.errors import AgentError


class VotingError(AgentError):
    code = "AGT.VOTING"


class VoteMethod(str, Enum):
    PLURALITY = "PLURALITY"
    RANKED = "RANKED"  # instant runoff
    APPROVAL = "APPROVAL"


@dataclass(frozen=True)
class Ballot:
    voter: str
    choices: Tuple[str, ...]  # ordered favourites or approved set


class Voting:
    """Elect options with the configured method."""

    def elect(
        self,
        options: Sequence[str],
        ballots: Sequence[Ballot],
        method: VoteMethod = VoteMethod.RANKED,
    ) -> Tuple[str, int]:
        if method is VoteMethod.PLURALITY:
            return self._plurality(options, ballots)
        if method is VoteMethod.APPROVAL:
            return self._approval(options, ballots)
        return self._ranked(options, ballots)

    def _plurality(self, options: Sequence[str], ballots: Sequence[Ballot]) -> Tuple[str, int]:
        votes = Counter(b.choices[0] for b in ballots if b.choices)
        return self._best(votes, ballots)

    def _approval(self, options: Sequence[str], ballots: Sequence[Ballot]) -> Tuple[str, int]:
        votes = Counter()
        for b in ballots:
            for choice in b.choices:
                votes[choice] += 1
        return self._best(votes, ballots)

    def _ranked(self, options: Sequence[str], ballots: Sequence[Ballot]) -> Tuple[str, int]:
        remaining = list(options)
        if not remaining:
            raise VotingError("no options")
        while len(remaining) > 1:
            votes = Counter()
            for b in ballots:
                # find first choice still remaining in order
                for pref in b.choices:
                    if pref in remaining:
                        votes[pref] += 1
                        break
            worst = min(remaining, key=lambda opt: votes.get(opt, 0))
            remaining.remove(worst)
        winner = remaining[0]
        return (winner, len(ballots))

    def _best(self, votes: Counter, ballots: Sequence[Ballot]) -> Tuple[str, int]:
        if not votes:
            raise VotingError("no votes")
        best, top = max(votes.items(), key=lambda kv: kv[1])  # type: ignore[attr-defined]
        return (best, len(ballots))


# ---------------------------------------------------------------------------
# Diet — time-boxed franchise (gameforge-rs voting.rs)
# ---------------------------------------------------------------------------

MIN_OPEN_SECS = 60
DEFAULT_OPEN_SECS = 86400


@dataclass(frozen=True)
class DietBallot:
    """One immutable voice on a measure. Never amended."""

    voter: str
    option: str
    cast_at: float

    def to_dict(self) -> dict[str, Any]:
        return {"voter": self.voter, "option": self.option, "cast_at": self.cast_at}


@dataclass
class Measure:
    """A proposed question. ``options[0]`` is the status quo."""

    id: str
    title: str
    options: Tuple[str, ...]
    proposer: str
    opened: float
    closes: float
    closed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "options": list(self.options),
            "proposer": self.proposer,
            "opened": self.opened,
            "closes": self.closes,
            "closed": self.closed,
        }


class Diet:
    """In-process Diet: propose, cast, tally, close.

    Ballots are secret in transit but public in the count — the tally is
    always a projection of the roll, so stuffing the box is visible in it.
    Thread-safe via a single RLock (mirrors the RS RwLock).
    """

    def __init__(
        self,
        *,
        clock: Optional[Callable[[], float]] = None,
        id_factory: Optional[Callable[[], str]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._now = clock or time.time
        self._id = id_factory or (lambda: str(uuid.uuid4()))
        self._measures: Dict[str, Measure] = {}
        self._ballots: Dict[str, List[DietBallot]] = {}

    def propose(
        self,
        title: str,
        options: Sequence[str],
        proposer: str,
        open_secs: int = DEFAULT_OPEN_SECS,
    ) -> Measure:
        """Open a measure. Needs at least two options; first is status quo.

        Open window is ``max(open_secs, MIN_OPEN_SECS)`` (RS ``open_secs.max(60)``).
        """
        opts = tuple(options)
        if len(opts) < 2:
            raise VotingError("a measure needs at least two options")
        now = self._now()
        window = max(int(open_secs), MIN_OPEN_SECS)
        measure = Measure(
            id=self._id(),
            title=title,
            options=opts,
            proposer=proposer,
            opened=now,
            closes=now + window,
            closed=False,
        )
        with self._lock:
            self._measures[measure.id] = measure
        return measure

    def cast(self, measure_id: str, voter: str, option: str) -> DietBallot:
        """Cast one voice. One voter per measure; no ballot is ever amended."""
        with self._lock:
            measure = self._measures.get(measure_id)
            if measure is None:
                raise VotingError("no such measure")
            if measure.closed or self._now() > measure.closes:
                raise VotingError("the measure is closed")
            if option not in measure.options:
                raise VotingError("no such option on this measure")
            roll = self._ballots.setdefault(measure_id, [])
            if any(b.voter == voter for b in roll):
                raise VotingError("one voice per measure — you have already spoken")
            ballot = DietBallot(voter=voter, option=option, cast_at=self._now())
            roll.append(ballot)
            return ballot

    def tally(self, measure_id: str) -> dict[str, Any]:
        """Recompute plurality from the full roll. Ties break to status quo."""
        with self._lock:
            measure = self._measures.get(measure_id)
            if measure is None:
                raise VotingError("no such measure")
            roll = list(self._ballots.get(measure_id, ()))
            now = self._now()
            options = measure.options
            title = measure.title
            closed = measure.closed or now > measure.closes

        counts: Dict[str, int] = {opt: 0 for opt in options}
        for ballot in roll:
            if ballot.option in counts:
                counts[ballot.option] += 1
            else:
                counts[ballot.option] = counts.get(ballot.option, 0) + 1

        # Highest count wins; ties prefer the earlier option (status quo first).
        leading = max(options, key=lambda opt: (counts.get(opt, 0), -options.index(opt)))
        return {
            "measure": title,
            "closed": closed,
            "ballots": len(roll),
            "counts": counts,
            "leading": leading,
        }

    def close(self, measure_id: str) -> Measure:
        """Seal the measure so no further ballots are taken."""
        with self._lock:
            measure = self._measures.get(measure_id)
            if measure is None:
                raise VotingError("no such measure")
            measure.closed = True
            return measure

    def measures(self) -> List[Measure]:
        with self._lock:
            return list(self._measures.values())

    def roll(self, measure_id: str) -> List[DietBallot]:
        """Public ballot roll for a measure (empty if none cast)."""
        with self._lock:
            if measure_id not in self._measures:
                raise VotingError("no such measure")
            return list(self._ballots.get(measure_id, ()))
