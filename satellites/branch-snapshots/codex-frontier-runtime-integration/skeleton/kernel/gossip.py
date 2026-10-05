"""SWIM-lite gossip — failure detection + membership dissemination.

The supervisor knows when an agent is sick *locally*; the rest of the
swarm needs to find out without a central bulletin board. This module
implements the SWIM ideas Skeleton actually needs:

- Direct probe with **indirect fallback**: when A can't reach B, it asks
  k random peers to probe B on its behalf before declaring suspicion.
- **Suspicion with refutation**: a SUSPECT member can refute by bumping
  its incarnation number; gossip spreads the higher incarnation and the
  suspicion dies.
- **Piggyback dissemination**: membership deltas ride on ordinary probe
  traffic, bounded per message, so news spreads in O(log n) rounds.

Pure state machine — transports plug in via the ``ProbeTransport``
protocol, keeping this testable without sockets.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Dict, List, Optional, Protocol, Tuple

from .errors import KernelError


class GossipError(KernelError):
    code = "KRN.GOSSIP"


class MemberState(str, Enum):
    ALIVE = "ALIVE"
    SUSPECT = "SUSPECT"
    DEAD = "DEAD"
    LEFT = "LEFT"


@dataclass(frozen=True)
class Member:
    node_id: str
    incarnation: int = 0
    state: MemberState = MemberState.ALIVE

    def version(self) -> Tuple[int, int]:
        """Ordering key: (incarnation, state-priority) — higher wins."""
        return (self.incarnation, {MemberState.ALIVE: 0, MemberState.SUSPECT: 1,
                                   MemberState.DEAD: 2, MemberState.LEFT: 2}[self.state])


@dataclass(frozen=True)
class GossipUpdate:
    member: Member


class ProbeTransport(Protocol):
    def probe(self, target: str) -> bool: ...
    def probe_via(self, intermediary: str, target: str) -> bool: ...


class GossipProtocol:
    """Per-node SWIM state. One instance per agent."""

    def __init__(
        self,
        node_id: str,
        *,
        indirect_probes: int = 3,
        max_piggyback: int = 6,
        seed: Optional[int] = None,
    ) -> None:
        if not node_id:
            raise GossipError("node_id is required")
        self.node_id = node_id
        self.indirect_probes = max(1, indirect_probes)
        self.max_piggyback = max(1, max_piggyback)
        self._rng = random.Random(seed)
        self._members: Dict[str, Member] = {node_id: Member(node_id)}
        self._hot: List[GossipUpdate] = []  # recent deltas awaiting piggyback

    # ------------------------------------------------------------------
    # Membership
    # ------------------------------------------------------------------

    def join(self, peer: str) -> None:
        if peer not in self._members:
            self._members[peer] = Member(peer)
            self._announce(self._members[peer])

    def leave(self) -> None:
        self._members[self.node_id] = replace(
            self._members[self.node_id],
            incarnation=self._members[self.node_id].incarnation + 1,
            state=MemberState.LEFT,
        )
        self._announce(self._members[self.node_id])

    def refute(self) -> None:
        """Bump own incarnation to kill any suspicion of this node."""
        me = self._members[self.node_id]
        self._members[self.node_id] = replace(me, incarnation=me.incarnation + 1,
                                              state=MemberState.ALIVE)
        self._announce(self._members[self.node_id])

    # ------------------------------------------------------------------
    # Probe cycle — call once per protocol period
    # ------------------------------------------------------------------

    def probe_cycle(self, transport: ProbeTransport) -> Optional[Member]:
        """Probe one random peer; returns the member if it turned SUSPECT."""
        peers = [m for m in self._members.values()
                 if m.node_id != self.node_id and m.state in (MemberState.ALIVE, MemberState.SUSPECT)]
        if not peers:
            return None
        target = self._rng.choice(peers)
        if transport.probe(target.node_id):
            self._apply(Member(target.node_id, max(target.incarnation,
                               self._members[target.node_id].incarnation), MemberState.ALIVE))
            return None
        # indirect fallback
        helpers = [m.node_id for m in peers if m.node_id != target.node_id]
        self._rng.shuffle(helpers)
        for helper in helpers[: self.indirect_probes]:
            if transport.probe_via(helper, target.node_id):
                return None
        suspect = replace(target, state=MemberState.SUSPECT)
        self._apply(suspect)
        return suspect

    def declare_dead(self, node_id: str) -> None:
        """After the suspicion window lapses (timed by the caller)."""
        member = self._members.get(node_id)
        if member and member.state == MemberState.SUSPECT:
            self._apply(replace(member, state=MemberState.DEAD))

    # ------------------------------------------------------------------
    # Dissemination
    # ------------------------------------------------------------------

    def _apply(self, update: Member) -> None:
        current = self._members.get(update.node_id)
        if current is None or update.version() > current.version():
            self._members[update.node_id] = update
            self._announce(update)

    def _announce(self, member: Member) -> None:
        self._hot.append(GossipUpdate(member))
        if len(self._hot) > 256:
            del self._hot[: len(self._hot) - 256]

    def piggyback(self) -> Tuple[GossipUpdate, ...]:
        """Bounded batch of recent deltas to attach to the next message."""
        batch = tuple(self._hot[: self.max_piggyback])
        del self._hot[: self.max_piggyback]
        return batch

    def receive(self, updates: Tuple[GossipUpdate, ...]) -> None:
        for u in updates:
            self._apply(u.member)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def member(self, node_id: str) -> Optional[Member]:
        return self._members.get(node_id)

    def roster(self, *, state: Optional[MemberState] = None) -> Tuple[Member, ...]:
        members = sorted(self._members.values(), key=lambda m: m.node_id)
        if state is None:
            return tuple(members)
        return tuple(m for m in members if m.state == state)
