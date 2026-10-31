"""Encounter placement with difficulty pacing along the critical path.

Difficulty is expressed as *damage taken as a fraction of player hp*, the
same quantity the validate package's winnable rule measures
(``enemy_hp / player.dps * enemy_dps``). Every room gets a damage budget
``pacing(t) * cap * hp`` where ``t`` is progress along the critical path
(side rooms use their depth relative to the goal) and ``cap`` sits under the
validator's 0.8·hp near-lethal warning. Candidates are built from abstract
combat roles (no names or lore; that belongs to narrative) and chosen with
the FLGB ``select_encounters`` budget selector.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from skeleton.game.generation.encounter_generation import EncounterCandidate, select_encounters
from skeleton.simulation.ecs.rng import DeterministicRng

from .canonical import digest, q
from .errors import ProcgenError
from .layout import Layout

PPM = 1_000_000
BOSS_HEADROOM = 0.9   # fraction of the cap ordinary rooms may use


@dataclass(frozen=True)
class Role:
    """An abstract combat role: hp in player-dps-seconds, dps as a fraction of player hp per second."""
    name: str
    hp_seconds: float        # how many seconds of player dps the enemy soaks
    dps_share: float         # enemy dps / player hp
    min_t: float = 0.0       # earliest progress at which it may appear
    weight: float = 1.0

    def damage_fraction(self, scale: float) -> float:
        return self.hp_seconds * self.dps_share * scale * scale


DEFAULT_ROLES: tuple[Role, ...] = (
    Role("swarm", 1.0, 0.04, 0.0, 1.5),
    Role("skirmisher", 2.0, 0.05, 0.0, 1.2),
    Role("brute", 4.0, 0.05, 0.25, 1.0),
    Role("caster", 2.0, 0.09, 0.35, 0.8),
    Role("elite", 4.5, 0.08, 0.6, 0.5),
)
BOSS_ROLE = Role("boss", 6.0, 0.085, 0.9, 1.0)


@dataclass(frozen=True)
class PacingCurve:
    """Rising tension with periodic rest dips: base + (peak-base)*t^shape, dipped every ``rest_every`` rooms."""
    base: float = 0.2
    peak: float = 0.95
    shape: float = 1.3
    rest_every: int = 3
    rest_depth: float = 0.45
    jitter: float = 0.06

    def __post_init__(self) -> None:
        if not 0.0 <= self.base <= self.peak <= 1.0:
            raise ProcgenError("pacing needs 0 <= base <= peak <= 1")
        if self.shape <= 0 or self.rest_every < 0 or not 0.0 <= self.rest_depth < 1.0 or not 0 <= self.jitter <= 0.5:
            raise ProcgenError("invalid pacing parameters")

    def value(self, t: float, index: int = 0, rng: DeterministicRng | None = None, *, allow_rest: bool = True) -> float:
        t = min(max(t, 0.0), 1.0)
        v = self.base + (self.peak - self.base) * t ** self.shape
        if allow_rest and self.rest_every and index > 0 and index % self.rest_every == 0 and t < 0.95:
            v *= 1.0 - self.rest_depth
        if rng is not None and self.jitter:
            v += rng.uniform(-self.jitter, self.jitter)
        return min(max(v, 0.0), 1.0)


@dataclass(frozen=True)
class EncounterConfig:
    roles: tuple[Role, ...] = DEFAULT_ROLES
    boss: Role | None = BOSS_ROLE
    pacing: PacingCurve = field(default_factory=PacingCurve)
    cap: float = 0.7                 # max damage fraction per room; validator warns at 0.8
    candidates_per_role: int = 2
    scale_jitter: float = 0.15
    side_factor: float = 0.75        # side rooms are a bit easier than path rooms at equal depth
    empty_start: bool = True
    system: str = "combat"
    max_per_room: int = 4

    def __post_init__(self) -> None:
        if not 0.05 <= self.cap < 0.8:
            raise ProcgenError("cap must be in [0.05, 0.8) so rooms stay under the near-lethal warning")
        if not self.roles:
            raise ProcgenError("need at least one role")
        if not 1 <= self.candidates_per_role <= 8 or not 1 <= self.max_per_room <= 12:
            raise ProcgenError("candidates_per_role in [1, 8], max_per_room in [1, 12]")


@dataclass(frozen=True)
class Encounter:
    id: str
    room: str
    role: str
    enemy_hp: float
    enemy_dps: float
    damage: float            # expected damage to the player (hp units)

    def as_plan(self, system: str) -> dict:
        return {"id": self.id, "system": system, "enemy_hp": self.enemy_hp, "enemy_dps": self.enemy_dps,
                "procgen": {"room": self.room, "role": self.role, "damage": self.damage}}


@dataclass(frozen=True)
class RoomPlan:
    room: str
    t: float
    target: float            # target damage fraction
    budget: float            # damage budget in hp units
    encounters: tuple[Encounter, ...]

    @property
    def damage(self) -> float:
        return q(sum(e.damage for e in self.encounters))

    def as_dict(self) -> dict:
        return {"room": self.room, "t": self.t, "target": self.target, "budget": self.budget,
                "damage": self.damage, "encounters": [e.id for e in self.encounters]}


@dataclass(frozen=True)
class EncounterPlan:
    rooms: Mapping[str, RoomPlan]
    order: tuple[str, ...]           # critical path order
    hp: float
    dps: float

    def all(self) -> list[Encounter]:
        return [e for rid in sorted(self.rooms) for e in self.rooms[rid].encounters]

    def curve(self) -> list[float]:
        """Damage fraction per critical-path room, in path order."""
        return [q(self.rooms[r].damage / self.hp) for r in self.order]

    def as_dict(self) -> dict:
        return {"hp": self.hp, "dps": self.dps, "order": list(self.order), "curve": self.curve(),
                "rooms": {k: v.as_dict() for k, v in sorted(self.rooms.items())}}

    def digest(self) -> str:
        return digest({"plan": self.as_dict(), "encounters": [e.as_plan("x") for e in self.all()]})


def progress(layout: Layout) -> dict[str, float]:
    """Per-room progress in [0, 1]: index on the path, or depth / goal depth for side rooms."""
    path = layout.critical_path
    n = max(len(path) - 1, 1)
    out = {rid: i / n for i, rid in enumerate(path)}
    depths = layout.depths()
    goal_depth = max(depths.get(layout.goal, 1), 1)
    for r in layout.rooms:
        if r.id not in out:
            out[r.id] = min(depths.get(r.id, 0) / goal_depth, 1.0)
    return out


def _candidate(room: str, idx: int, role: Role, scale: float, hp: float, dps: float) -> tuple[Encounter, int]:
    enemy_hp = max(1.0, round(role.hp_seconds * scale * dps, 1))
    enemy_dps = max(0.0, round(role.dps_share * scale * hp, 2))
    damage = q(enemy_hp / dps * enemy_dps)
    eid = f"pg_{room}_{role.name}_{idx}"
    return Encounter(eid, room, role.name, enemy_hp, enemy_dps, damage), int(round(damage / hp * PPM))


def plan_room(room: str, t: float, index: int, side: bool, hp: float, dps: float, rng: DeterministicRng,
              cfg: EncounterConfig, *, boss: bool = False, allow_rest: bool = True) -> RoomPlan:
    # regular rooms stay under BOSS_HEADROOM of the cap so the goal fight is the peak
    target = cfg.pacing.value(t, index, rng, allow_rest=allow_rest) * cfg.cap * BOSS_HEADROOM
    if side:
        target *= cfg.side_factor
    budget = q(target * hp)
    pool: list[tuple[Encounter, int]] = []
    roles = [r for r in cfg.roles if r.min_t <= t + 1e-9] or [cfg.roles[0]]
    if boss and cfg.boss is not None:
        roles = [cfg.boss]
    n = 0
    for role in roles:
        for _ in range(cfg.candidates_per_role if not boss else 3):
            scale = 1.0 + rng.uniform(-cfg.scale_jitter, cfg.scale_jitter)
            pool.append(_candidate(room, n, role, scale, hp, dps))
            n += 1
    # boss: sized to land between BOSS_HEADROOM and the cap (damage scales with scale^2)
    if boss:
        role = cfg.boss
        assert role is not None
        frac = rng.uniform(BOSS_HEADROOM + (1 - BOSS_HEADROOM) * 0.25, 1.0 - (1 - BOSS_HEADROOM) * 0.25)
        scale = math.sqrt(frac * cfg.cap / role.damage_fraction(1.0))
        e1, _ = _candidate(room, n, role, scale, hp, dps)
        if e1.damage > cfg.cap * hp:  # rounding guard
            e1, _ = _candidate(room, n, role, scale * 0.98, hp, dps)
        return RoomPlan(room, q(t), q(frac * cfg.cap), q(cfg.cap * hp), (e1,))
    by_id = {e.id: e for e, _ in pool}
    cands = [EncounterCandidate(e.id, max(1, int(round(e.damage * 1000))), ppm, digest(e.as_plan(cfg.system)))
             for e, ppm in pool]
    target_ppm = min(PPM, int(round(target / max(len(roles), 1) * PPM * 1.5)))
    chosen = select_encounters(cands, int(round(budget * 1000)), target_ppm)
    picked = [by_id[i] for i in chosen][: cfg.max_per_room]
    # weight-ordered shuffle so the room's first fight is not always the easiest
    rng.shuffle(picked)
    return RoomPlan(room, q(t), q(target), budget, tuple(picked))


def place_encounters(layout: Layout, player: Mapping[str, float], rng: DeterministicRng,
                     cfg: EncounterConfig = EncounterConfig()) -> EncounterPlan:
    hp, dps = float(player.get("hp") or 0), float(player.get("dps") or 0)
    if hp <= 0 or dps <= 0:
        raise ProcgenError("player needs positive hp and dps for encounter pacing")
    prog = progress(layout)
    path = layout.critical_path
    on_path = set(path)
    rooms: dict[str, RoomPlan] = {}
    for i, rid in enumerate(path):
        if rid == layout.start and cfg.empty_start:
            rooms[rid] = RoomPlan(rid, 0.0, 0.0, 0.0, ())
            continue
        rooms[rid] = plan_room(rid, prog[rid], i, False, hp, dps, rng.fork(f"room/{rid}"), cfg,
                               boss=(rid == layout.goal and len(path) > 1),
                               allow_rest=(i != len(path) - 2))  # no lull right before the goal
    for r in sorted(layout.rooms, key=lambda r: r.id):
        if r.id in on_path:
            continue
        rooms[r.id] = plan_room(r.id, prog[r.id], 0, True, hp, dps, rng.fork(f"room/{r.id}"), cfg)
    return EncounterPlan(rooms, tuple(path), hp, dps)


def pacing_report(curve: Sequence[float], *, spike: float = 0.45, min_trend: float = 0.0) -> dict:
    """Simple pacing diagnostics: biggest jump between consecutive rooms and the overall trend."""
    if len(curve) < 2:
        return {"max_jump": 0.0, "trend": 0.0, "spikes": [], "flat": False}
    jumps = [curve[i + 1] - curve[i] for i in range(len(curve) - 1)]
    n = len(curve)
    xs = range(n)
    mx, my = (n - 1) / 2, sum(curve) / n
    den = sum((x - mx) ** 2 for x in xs) or 1.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, curve)) / den
    spikes = [i + 1 for i, j in enumerate(jumps) if j > spike]
    return {"max_jump": q(max(jumps)), "trend": q(slope), "spikes": spikes, "flat": slope <= min_trend}
