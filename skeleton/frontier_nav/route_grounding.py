"""Ground NPC travel, quests, Dragon and Jeeves map cognition in approved routes (GF-P0-132).

A plan (sequence of waypoint ids) is accepted only if every hop lies on an
:class:`ApprovedRoute` whose authorising :class:`DesignNote` carries a valid
signature. Signature checking is a port so the Internal Systems vault/seal
service can be wired in through an adapter; :func:`hmac_verifier` is the
local reference adapter.
"""

from __future__ import annotations

import hashlib
import hmac
import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

CONSUMERS = frozenset({"npc_travel", "quest", "dragon_map", "jeeves_map"})

Verifier = Callable[[bytes, str], bool]


class GroundingRejected(ValueError):
    """Raised when a plan cannot be grounded in approved, signed routes."""


@dataclass(frozen=True)
class DesignNote:
    note_id: str
    body: str
    signature: str

    def payload(self) -> bytes:
        return f"{self.note_id}\n{self.body}".encode()


@dataclass(frozen=True)
class ApprovedRoute:
    route_id: str
    waypoints: tuple[str, ...]
    note: DesignNote
    consumers: frozenset[str] = CONSUMERS
    bidirectional: bool = True

    def hops(self) -> set[tuple[str, str]]:
        pairs = set(zip(self.waypoints, self.waypoints[1:]))
        if self.bidirectional:
            pairs |= {(b, a) for a, b in pairs}
        return pairs


@dataclass(frozen=True)
class GroundedPlan:
    consumer: str
    waypoints: tuple[str, ...]
    route_ids: tuple[str, ...]
    note_ids: tuple[str, ...]


def hmac_verifier(key: bytes) -> Verifier:
    def verify(payload: bytes, signature: str) -> bool:
        expected = hmac.new(key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    return verify


@dataclass
class RouteGrounder:
    verifier: Verifier
    _routes: dict[str, ApprovedRoute] = field(default_factory=dict)

    def approve(self, route: ApprovedRoute) -> None:
        if len(route.waypoints) < 2:
            raise GroundingRejected("route needs at least two waypoints")
        if not route.consumers <= CONSUMERS:
            raise GroundingRejected(
                f"unknown consumers {set(route.consumers - CONSUMERS)}"
            )
        if not self.verifier(route.note.payload(), route.note.signature):
            raise GroundingRejected(
                f"design note {route.note.note_id} signature invalid"
            )
        if route.route_id in self._routes:
            raise GroundingRejected(
                f"route {route.route_id} already approved (extend-only)"
            )
        self._routes[route.route_id] = route

    def ground(self, consumer: str, waypoints: Sequence[str]) -> GroundedPlan:
        if consumer not in CONSUMERS:
            raise GroundingRejected(f"unknown consumer {consumer}")
        if len(waypoints) < 2:
            raise GroundingRejected("plan needs at least two waypoints")
        route_ids: list[str] = []
        for hop in itertools.pairwise(waypoints):
            match = next(
                (
                    r
                    for r in self._routes.values()
                    if consumer in r.consumers
                    and hop in r.hops()
                    and self.verifier(r.note.payload(), r.note.signature)
                ),
                None,
            )
            if match is None:
                raise GroundingRejected(
                    f"hop {hop[0]}->{hop[1]} not on an approved route"
                )
            route_ids.append(match.route_id)
        notes = tuple(dict.fromkeys(self._routes[r].note.note_id for r in route_ids))
        return GroundedPlan(consumer, tuple(waypoints), tuple(route_ids), notes)
