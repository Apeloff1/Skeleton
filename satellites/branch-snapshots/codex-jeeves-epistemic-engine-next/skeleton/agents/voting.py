"""Agent voting — structured ballots for mesh preference
(complements negotiation).

Negotiation resolves consent; sometimes the mesh picks 1-of-N by
explicit ballot instead. Supports PLURALITY, RANKED (instant runoff),
and APPROVAL voting over named options.

- :class:`Ballot` — agent, method, choices
- :class:`Voting` — elect() returns winner(s) + tallies
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

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
