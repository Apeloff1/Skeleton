"""Dynamic route repair over signed, approved routes (GF-L / GF-P2-40).

World changes (construction, floods, collapse, tides, terrain edits) block
waypoints or hops. A :class:`RouteMonitor` watches authoritative GPS frames
from :class:`~skeleton.frontier_nav.gps.FrameGPSHub` and flags an entity whose
active plan is blocked ahead or who has deviated from the plan corridor for
too many consecutive frames. :class:`RouteRepairer` replans on the graph of
*approved* hops only (never inventing geometry) and re-grounds the result
through :class:`~skeleton.frontier_nav.route_grounding.RouteGrounder`, so a
repaired plan still carries valid design-note signatures. Nothing here
edits GF-H; it composes it.
"""

from __future__ import annotations

import heapq
import math
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from skeleton.frontier_nav.gps import NavUpdate, PositionFix
from skeleton.frontier_nav.route_grounding import (
    GroundedPlan,
    GroundingRejected,
    RouteGrounder,
)

CHANGE_KINDS = frozenset({"construction", "flood", "collapse", "tide", "terrain"})
MAX_WORLD_CHANGE_WAYPOINTS = 4096
MAX_WORLD_CHANGE_HOPS = 8192
MAX_WORLD_CHANGES = 100_000


def _valid_waypoint(value: object) -> bool:
    return (type(value) is str and 1 <= len(value) <= 128
            and value == value.strip()
            and not any(unicodedata.category(ch) in {"Cc", "Cf", "Zl", "Zp"}
                        for ch in value))


def _valid_waypoint_set(values: object) -> bool:
    return (type(values) is frozenset and len(values) <= MAX_WORLD_CHANGE_WAYPOINTS
            and all(_valid_waypoint(value) for value in values))


def _valid_hop_set(values: object) -> bool:
    return (type(values) is frozenset and len(values) <= MAX_WORLD_CHANGE_HOPS
            and all(type(pair) is tuple and len(pair) == 2
                    and _valid_waypoint(pair[0]) and _valid_waypoint(pair[1])
                    and pair[0] != pair[1] for pair in values))


Point = tuple[float, float, float]


class RepairFailed(ValueError):
    """No approved, unblocked route exists (caller must hold or escalate)."""


@dataclass(frozen=True)
class WorldChange:
    change_id: str
    kind: str
    frame: int
    blocked_waypoints: frozenset[str] = frozenset()
    blocked_hops: frozenset[tuple[str, str]] = frozenset()
    reopen_waypoints: frozenset[str] = frozenset()
    reopen_hops: frozenset[tuple[str, str]] = frozenset()

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in CHANGE_KINDS:
            raise ValueError(f"unknown world change kind {self.kind!r}")
        if (type(self.change_id) is not str or not 1 <= len(self.change_id) <= 128
                or any(ord(char) < 32 or ord(char) == 127 for char in self.change_id)):
            raise ValueError("change_id must be a bounded printable identifier")
        if type(self.frame) is not int or not 0 <= self.frame <= 2**63 - 1:
            raise ValueError("world change frame must be a bounded integer")
        if (not _valid_waypoint_set(self.blocked_waypoints)
                or not _valid_waypoint_set(self.reopen_waypoints)
                or not _valid_hop_set(self.blocked_hops)
                or not _valid_hop_set(self.reopen_hops)):
            raise ValueError("world change topology evidence exceeds canonical bounds")
        if self.blocked_waypoints & self.reopen_waypoints or any(
            pair in self.reopen_hops or (pair[1], pair[0]) in self.reopen_hops
            for pair in self.blocked_hops
        ):
            raise ValueError("world change cannot block and reopen the same topology")


@dataclass
class Blockages:
    """Current blocked state, applied in frame order (idempotent per change_id)."""

    waypoints: set[str] = field(default_factory=set)
    hops: set[tuple[str, str]] = field(default_factory=set)
    applied: dict[str, int] = field(default_factory=dict)
    applied_events: dict[str, WorldChange] = field(default_factory=dict)
    last_frame: int = -1

    def apply(self, change: WorldChange) -> bool:
        if change.change_id in self.applied:
            if self.applied_events.get(change.change_id) != change:
                raise ValueError("conflicting world change identity")
            return False
        if len(self.applied) >= MAX_WORLD_CHANGES:
            raise ValueError("world change history exceeds capacity")
        if change.frame < self.last_frame:
            raise ValueError(
                f"change {change.change_id} at frame {change.frame} "
                f"is older than {self.last_frame}"
            )
        self.waypoints -= change.reopen_waypoints
        for a, b in change.reopen_hops:
            self.hops.discard((a, b))
            self.hops.discard((b, a))
        self.waypoints |= change.blocked_waypoints
        for a, b in change.blocked_hops:
            self.hops |= {(a, b), (b, a)}
        self.applied[change.change_id] = change.frame
        self.applied_events[change.change_id] = change
        self.last_frame = change.frame
        return True

    def hop_blocked(self, a: str, b: str) -> bool:
        return a in self.waypoints or b in self.waypoints or (a, b) in self.hops


def _dist(a: Point, b: Point) -> float:
    return math.dist(a, b)


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    ab = tuple(bb - aa for aa, bb in zip(a, b))
    ap = tuple(pp - aa for aa, pp in zip(a, p))
    denom = sum(c * c for c in ab)
    if denom == 0:
        return _dist(p, a)
    t = max(0.0, min(1.0, sum(x * y for x, y in zip(ab, ap)) / denom))
    proj = tuple(aa + t * c for aa, c in zip(a, ab))
    return _dist(p, proj)  # type: ignore[arg-type]


@dataclass(frozen=True)
class RepairTrigger:
    entity_id: str
    frame: int
    reason: str  # "blocked" | "deviated"
    from_waypoint: str
    detail: str


@dataclass(frozen=True)
class RepairedPlan:
    entity_id: str
    frame: int
    trigger: RepairTrigger
    previous: GroundedPlan
    plan: GroundedPlan
    cost: float


@dataclass
class RouteRepairer:
    grounder: RouteGrounder
    coords: Mapping[str, Point]
    blockages: Blockages = field(default_factory=Blockages)

    def _approved_hops(self, consumer: str) -> set[tuple[str, str]]:
        hops: set[tuple[str, str]] = set()
        for route in self.grounder._routes.values():  # read-only view of GF-H state
            if consumer in route.consumers:
                hops |= route.hops()
        return hops

    def _cost(self, a: str, b: str) -> float:
        if a not in self.coords or b not in self.coords:
            raise RepairFailed(f"no surveyed coordinates for hop {a}->{b}")
        return _dist(self.coords[a], self.coords[b])

    def shortest(self, consumer: str, start: str, goal: str) -> tuple[list[str], float]:
        if start in self.blockages.waypoints or goal in self.blockages.waypoints:
            raise RepairFailed(f"endpoint blocked ({start}->{goal})")
        adj: dict[str, list[str]] = {}
        for a, b in self._approved_hops(consumer):
            if not self.blockages.hop_blocked(a, b):
                adj.setdefault(a, []).append(b)
        best = {start: 0.0}
        prev: dict[str, str] = {}
        heap = [(0.0, start)]
        while heap:
            d, node = heapq.heappop(heap)
            if node == goal:
                path = [goal]
                while path[-1] != start:
                    path.append(prev[path[-1]])
                return path[::-1], d
            if d > best.get(node, math.inf):
                continue
            for nxt in sorted(adj.get(node, ())):
                nd = d + self._cost(node, nxt)
                if nd < best.get(nxt, math.inf):
                    best[nxt] = nd
                    prev[nxt] = node
                    heapq.heappush(heap, (nd, nxt))
        raise RepairFailed(f"no approved unblocked route {start}->{goal}")

    def nearest_waypoint(self, fix: PositionFix, candidates: Iterable[str]) -> str:
        pos = (fix.x, fix.y, fix.z)
        usable = [
            w for w in candidates
            if w in self.coords and w not in self.blockages.waypoints
        ]
        if not usable:
            raise RepairFailed("no reachable waypoint near entity")
        return min(usable, key=lambda w: (_dist(pos, self.coords[w]), w))

    def repair(
        self, trigger: RepairTrigger, previous: GroundedPlan, fix: PositionFix
    ) -> RepairedPlan:
        goal = previous.waypoints[-1]
        if trigger.reason == "deviated":
            start = self.nearest_waypoint(fix, self._nodes(previous.consumer))
        else:
            start = trigger.from_waypoint
        if start == goal:
            raise RepairFailed("entity already at goal; nothing to repair")
        path, cost = self.shortest(previous.consumer, start, goal)
        try:
            plan = self.grounder.ground(previous.consumer, path)
        except GroundingRejected as exc:  # signature revoked/forged since approval
            raise RepairFailed(f"re-grounding failed: {exc}") from exc
        return RepairedPlan(trigger.entity_id, trigger.frame, trigger, previous, plan, cost)

    def _nodes(self, consumer: str) -> set[str]:
        return {w for hop in self._approved_hops(consumer) for w in hop}


@dataclass
class _Track:
    plan: GroundedPlan
    index: int = 0  # index of last waypoint reached
    off_frames: int = 0


@dataclass
class RouteMonitor:
    """Hub hook: feed it NavUpdates; it emits repair triggers."""

    repairer: RouteRepairer
    corridor: float = 2.0
    arrive_radius: float = 0.75
    deviation_frames: int = 3
    tracks: dict[str, _Track] = field(default_factory=dict)
    triggers: list[RepairTrigger] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name in ("corridor", "arrive_radius"):
            value = getattr(self, name)
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not 0 <= value <= 1_000_000):
                raise ValueError(f"{name} must be a bounded finite distance")
        if (type(self.deviation_frames) is not int
                or not 1 <= self.deviation_frames <= 10_000):
            raise ValueError("deviation_frames must be a bounded positive integer")

    def follow(self, entity_id: str, plan: GroundedPlan) -> None:
        self.tracks[entity_id] = _Track(plan)

    def remaining(self, entity_id: str) -> Sequence[str]:
        t = self.tracks[entity_id]
        return t.plan.waypoints[t.index:]

    def __call__(self, update: NavUpdate) -> list[RepairTrigger]:
        out: list[RepairTrigger] = []
        coords = self.repairer.coords
        blk = self.repairer.blockages
        for fix in update.fixes:
            track = self.tracks.get(fix.entity_id)
            if track is None:
                continue
            wps = track.plan.waypoints
            pos = (fix.x, fix.y, fix.z)
            while (
                track.index + 1 < len(wps)
                and _dist(pos, coords[wps[track.index + 1]]) <= self.arrive_radius
            ):
                track.index += 1
            if track.index == len(wps) - 1:
                continue
            ahead = list(zip(wps[track.index:], wps[track.index + 1:]))
            hit = next(((a, b) for a, b in ahead if blk.hop_blocked(a, b)), None)
            if hit is not None:
                track.off_frames = 0
                out.append(RepairTrigger(
                    fix.entity_id, update.frame, "blocked", wps[track.index],
                    f"hop {hit[0]}->{hit[1]} blocked",
                ))
                continue
            a, b = coords[wps[track.index]], coords[wps[track.index + 1]]
            off = point_segment_distance(pos, a, b)
            track.off_frames = track.off_frames + 1 if off > self.corridor else 0
            if track.off_frames >= self.deviation_frames:
                track.off_frames = 0
                out.append(RepairTrigger(
                    fix.entity_id, update.frame, "deviated", wps[track.index],
                    f"{off:.2f} off corridor for {self.deviation_frames} frames",
                ))
        self.triggers.extend(out)
        return out
