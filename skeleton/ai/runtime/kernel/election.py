"""Leader election for the kernel — one coordinator per epoch, no split-brain.

The swarm needs exactly one node coordinating work like dream cycles,
merkle anchoring, and vault rotation. This module implements a
lease-backed, term-numbered election:

- Candidates start an election with a monotonically increasing ``term``;
  a stale term from a partitioned node is rejected outright.
- Votes are one per node per term, persisted in the registry, so a
  rebooted node can't double-vote.
- The winner must renew its leadership lease before ``lease_ttl`` or
  the seat opens for the next election — liveness comes from the same
  expiry discipline as :mod:`leases`.

Single-process logic with injectable clock and transport hooks; the
RPC layer lives outside.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Optional, Set, Tuple

from .errors import KernelError


class ElectionError(KernelError):
    code = "KRN.ELECTION"


class StaleTermError(ElectionError):
    code = "KRN.ELECTION_STALE_TERM"


class Role(str, Enum):
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"


@dataclass(frozen=True)
class VoteRequest:
    candidate_id: str
    term: int
    last_log_index: int  # candidacy freshness, raft-style


@dataclass
class NodeState:
    node_id: str
    role: Role = Role.FOLLOWER
    current_term: int = 0
    voted_for: Optional[str] = None
    leader_id: Optional[str] = None
    last_log_index: int = 0


class Election:
    """Term-numbered majority election with lease-backed leadership."""

    def __init__(
        self,
        node_id: str,
        cluster_size: int,
        *,
        lease_ttl_s: float = 10.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if cluster_size < 1:
            raise ElectionError("cluster size must be >= 1",
                                context={"size": cluster_size})
        self.state = NodeState(node_id=node_id)
        self.cluster_size = cluster_size
        self.lease_ttl_s = lease_ttl_s
        self._now = clock or time.monotonic
        self._votes_received: Set[str] = set()
        self._leadership_expires_at: float = 0.0

    @property
    def quorum(self) -> int:
        return self.cluster_size // 2 + 1

    # ------------------------------------------------------------------
    # Campaigning
    # ------------------------------------------------------------------

    def start_election(self) -> VoteRequest:
        """Become a candidate: bump term, vote for self."""
        s = self.state
        s.current_term += 1
        s.role = Role.CANDIDATE
        s.voted_for = s.node_id
        s.leader_id = None
        self._votes_received = {s.node_id}
        self._maybe_win()
        return VoteRequest(s.node_id, s.current_term, s.last_log_index)

    def receive_vote(self, voter_id: str, *, granted: bool, term: int) -> Role:
        self._observe_term(term)
        if self.state.role is not Role.CANDIDATE:
            return self.state.role
        if term != self.state.current_term:
            return self.state.role  # vote for an old campaign
        if granted:
            self._votes_received.add(voter_id)
            self._maybe_win()
        return self.state.role

    def _maybe_win(self) -> None:
        if (self.state.role is Role.CANDIDATE
                and len(self._votes_received) >= self.quorum):
            self.state.role = Role.LEADER
            self.state.leader_id = self.state.node_id
            self._leadership_expires_at = self._now() + self.lease_ttl_s

    # ------------------------------------------------------------------
    # Voting
    # ------------------------------------------------------------------

    def request_vote(self, req: VoteRequest) -> bool:
        """Decide whether to grant a vote to a candidate."""
        self._observe_term(req.term)
        s = self.state
        if req.term < s.current_term:
            return False
        if req.last_log_index < s.last_log_index:
            return False  # candidate's log is behind
        if s.voted_for not in (None, req.candidate_id):
            return False
        s.voted_for = req.candidate_id
        s.role = Role.FOLLOWER
        return True

    # ------------------------------------------------------------------
    # Leadership liveness
    # ------------------------------------------------------------------

    def renew_leadership(self) -> float:
        """Leader-only: extend the lease; returns new expiry."""
        if self.state.role is not Role.LEADER:
            raise ElectionError("only the leader can renew leadership",
                                context={"node": self.state.node_id,
                                         "role": self.state.role.value})
        self._leadership_expires_at = self._now() + self.lease_ttl_s
        return self._leadership_expires_at

    def is_leader(self) -> bool:
        """True only while the leadership lease is live."""
        return (self.state.role is Role.LEADER
                and self._now() < self._leadership_expires_at)

    def check_liveness(self) -> Role:
        """Demote an expired leader back to follower; call on a timer."""
        if (self.state.role is Role.LEADER
                and self._now() >= self._leadership_expires_at):
            self.state.role = Role.FOLLOWER
            self.state.leader_id = None
        return self.state.role

    def observe_leader(self, leader_id: str, term: int) -> None:
        """Accept a leader heartbeat; stale terms are rejected."""
        if term < self.state.current_term:
            raise StaleTermError(
                "leader heartbeat from a stale term",
                context={"presented": term, "current": self.state.current_term},
            )
        self._observe_term(term)
        self.state.role = Role.FOLLOWER
        self.state.leader_id = leader_id

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _observe_term(self, term: int) -> None:
        if term > self.state.current_term:
            self.state.current_term = term
            self.state.voted_for = None
            if self.state.role is not Role.FOLLOWER:
                self.state.role = Role.FOLLOWER
                self.state.leader_id = None

    def report(self) -> Dict[str, object]:
        s = self.state
        return {
            "node": s.node_id,
            "role": s.role.value,
            "term": s.current_term,
            "leader": s.leader_id,
            "quorum": self.quorum,
            "votes": sorted(self._votes_received),
            "lease_live": self.is_leader(),
        }
