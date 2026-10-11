"""Real time-step escort, leash, escort introduction and combat encounters.

These are independently executable play systems, not renamed generic quest
tokens. Player and escort can occupy the same tile (non-colliding characters);
the escort only progresses along a legal authored route, while leash mode
enforces distance. Combat supports timed rivals, protection and wave survival.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .contracts import canonical_digest


class EncounterError(ValueError):
    """Invalid encounter state, input action or replay proof."""


ENCOUNTERS = frozenset({
    "escort_path", "escort_leash", "escort_introduction",
    "combat", "rival_combat", "timed_combat", "timed_rival_combat",
    "survival_waves", "reinforcement",
})
DIRS = {"east": (1, 0), "west": (-1, 0),
        "north": (0, -1), "south": (0, 1)}
MAX_ACTIONS = 256


@dataclass(frozen=True, slots=True)
class EncounterSpec:
    key: str
    kind: str
    path: tuple[tuple[int, int], ...]
    leash: int = 3
    waves: int = 1
    deadline: int = 60
    health: int = 16

    def __post_init__(self):
        if not isinstance(self.key, str) or not 1 <= len(self.key) <= 80:
            raise EncounterError("typed encounter identity required")
        if self.kind not in ENCOUNTERS:
            raise EncounterError("unrecognized playable quest encounter")
        if not isinstance(self.path, tuple) or not 2 <= len(self.path) <= 96:
            raise EncounterError("encounters need bounded authored movement paths")
        for i, point in enumerate(self.path):
            if (not isinstance(point, tuple) or len(point) != 2
                    or any(type(x) is not int or not 0 <= x <= 40 for x in point)):
                raise EncounterError("invalid authored spatial route")
            if i and sum(abs(a-b) for a,b in zip(point,self.path[i-1])) != 1:
                raise EncounterError("escort paths cannot teleport or skip route segments")
        if len(set(self.path)) != len(self.path):
            raise EncounterError("escort path cannot revisit a point")
        for n, lo, hi in ((self.leash, 1, 8), (self.waves, 1, 12),
                           (self.deadline, 4, MAX_ACTIONS), (self.health, 2, 64)):
            if type(n) is not int or not lo <= n <= hi:
                raise EncounterError("encounter combat, health or range outside budget")

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return {"schema": "skeleton.game_builder.encounter_spec.v1",
                "key": self.key, "kind": self.kind,
                "path": [list(p) for p in self.path],
                "leash": self.leash, "waves": self.waves,
                "deadline": self.deadline, "health": self.health}


@dataclass(frozen=True, slots=True)
class EncounterState:
    spec_digest: str
    player: tuple[int, int]
    escort: tuple[int, int]
    escort_index: int
    turn: int
    health: int
    shield: int
    threat: int
    waves_cleared: int
    greeted: bool
    status: str
    method: str

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return {
            "spec_digest": self.spec_digest,
            "player": list(self.player), "escort": list(self.escort),
            "escort_index": self.escort_index,
            "turn": self.turn, "health": self.health,
            "shield": self.shield, "threat": self.threat,
            "waves_cleared": self.waves_cleared,
            "greeted": self.greeted, "status": self.status,
            "method": self.method,
        }


def encounter_initial(spec: EncounterSpec) -> EncounterState:
    return EncounterState(
        spec.digest, spec.path[0], spec.path[0], 0, 0,
        spec.health, 0, 2, 0, False, "playing", "undecided",
    )


def encounter_options(spec: EncounterSpec, state: EncounterState) -> tuple[str, ...]:
    if not isinstance(spec, EncounterSpec) or not isinstance(state, EncounterState):
        raise EncounterError("typed scene and spatial state required")
    if state.spec_digest != spec.digest or state.status != "playing":
        return ()
    if spec.kind.startswith("escort"):
        out = []
        current = state.player
        for name, (dx,dy) in DIRS.items():
            next_pos = (current[0]+dx,current[1]+dy)
            if next_pos in spec.path:
                out.append(name)
        out.append("wait")
        if (spec.kind == "escort_introduction" and
                state.player == spec.path[-1] and
                state.escort == spec.path[-1]):
            out.append("introduce")
        return tuple(out)
    return ("attack","defend","reinforce","negotiate","wait")


def encounter_advance(spec: EncounterSpec, state: EncounterState,
                      action: str, *, authorized: bool) -> EncounterState:
    if not authorized:
        raise PermissionError("encounter action requires operator authority")
    if action not in encounter_options(spec, state):
        raise EncounterError("unavailable real movement/combat action")
    if state.turn >= MAX_ACTIONS:
        raise EncounterError("encounter action limit exceeded")
    turn = state.turn + 1
    x,y = state.player
    escort = state.escort
    index = state.escort_index
    hp = state.health
    shield = state.shield
    threat = state.threat
    waves = state.waves_cleared
    greeted = state.greeted
    status = "playing"
    method = state.method
    if spec.kind.startswith("escort"):
        if action in DIRS:
            dx,dy = DIRS[action]
            x,y=x+dx,y+dy
        if action == "introduce":
            greeted = True
        # The escort is simulated independently. Its next legal route point
        # may equal the player tile: the pair are non-colliding entities.
        if index + 1 < len(spec.path):
            next_point = spec.path[index + 1]
            dist = abs(x-next_point[0])+abs(y-next_point[1])
            if dist <= spec.leash:
                index += 1
                escort = next_point
        span = abs(x-escort[0])+abs(y-escort[1])
        if spec.kind == "escort_leash" and span > spec.leash:
            status = "lost"
        elif index == len(spec.path)-1 and (x,y)==spec.path[-1]:
            if spec.kind != "escort_introduction" or greeted:
                status = "won"
                method = ("leash_noncolliding" if spec.kind == "escort_leash"
                          else "regional_introduction" if spec.kind == "escort_introduction"
                          else "path_follow")
        if turn >= spec.deadline and status == "playing":
            status = "lost"
    else:
        if action == "attack":
            threat -= 2
            method = "direct_combat"
        elif action == "negotiate":
            threat = 0
            method = "negotiation"
        elif action == "defend":
            shield = min(8,shield+2)
        elif action == "reinforce":
            shield = min(8,shield+3)
        if threat <= 0:
            waves += 1
            if waves >= spec.waves:
                status = "won"
                if method == "undecided":
                    method = "reinforced_survival"
            else:
                threat = 2 + (waves % 2)
        if status == "playing":
            damage = 2 if spec.kind in {"rival_combat","timed_rival_combat"} else 1
            absorbed = min(shield, damage)
            shield -= absorbed
            hp -= damage-absorbed
            if hp <= 0:
                hp = 0
                status = "lost"
        if turn >= spec.deadline and status == "playing":
            status = "lost"
    return EncounterState(
        spec.digest,(x,y),escort,index,turn,hp,shield,threat,
        waves,greeted,status,method,
    )


@dataclass(frozen=True, slots=True)
class EncounterReplay:
    spec_digest: str
    actions: tuple[str, ...]
    state_digests: tuple[str, ...]
    final: EncounterState

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return {
            "schema": "skeleton.game_builder.encounter_replay.v1",
            "spec_digest": self.spec_digest,
            "actions": list(self.actions),
            "state_digests": list(self.state_digests),
            "final": self.final.payload(),
        }


def encounter_play(spec: EncounterSpec, actions: Sequence[str],
                   *, authorized: bool) -> EncounterReplay:
    if not authorized:
        raise PermissionError("encounter replay requires authority")
    if not isinstance(actions, (list, tuple)) or len(actions) > MAX_ACTIONS:
        raise EncounterError("invalid action trace")
    state = encounter_initial(spec)
    digests=[]
    for action in actions:
        state=encounter_advance(spec,state,action,authorized=True)
        digests.append(state.digest)
    return EncounterReplay(spec.digest,tuple(actions),tuple(digests),state)


def encounter_verify(spec: EncounterSpec, replay: EncounterReplay) -> None:
    if not isinstance(replay, EncounterReplay) or replay.spec_digest != spec.digest:
        raise EncounterError("foreign escort/combat proof")
    expected=encounter_play(spec,replay.actions,authorized=True)
    if expected != replay:
        raise EncounterError("encounter state replay divergence")


def demonstrate_encounter(spec: EncounterSpec, *, authorized: bool) -> EncounterReplay:
    if not authorized:
        raise PermissionError("encounter solver requires authority")
    if spec.kind.startswith("escort"):
        actions=[]
        path=spec.path
        for previous,point in zip(path,path[1:]):
            dx=point[0]-previous[0]
            dy=point[1]-previous[1]
            actions.append(next(name for name,offset in DIRS.items()
                                if offset==(dx,dy)))
        actions.append("introduce" if spec.kind=="escort_introduction" else "wait")
    else:
        actions=["reinforce"] if spec.waves>4 else []
        actions.extend("attack" for _ in range(spec.waves+2))
    replay=encounter_play(spec,actions,authorized=True)
    if replay.final.status != "won":
        if not spec.kind.startswith("escort"):
            # Stop on first winning round; don't submit terminal actions.
            moves=[]
            state=encounter_initial(spec)
            for action in (["reinforce"] if spec.waves>4 else [])+["attack"]*spec.waves:
                if state.status != "playing":
                    break
                state=encounter_advance(spec,state,action,authorized=True)
                moves.append(action)
            replay=encounter_play(spec,moves,authorized=True)
    if replay.final.status != "won":
        raise EncounterError("encounter has no demonstrated winning playthrough")
    encounter_verify(spec,replay)
    return replay


__all__ = [
    "EncounterError","EncounterSpec","EncounterState","EncounterReplay",
    "encounter_initial","encounter_options","encounter_advance",
    "encounter_play","encounter_verify","demonstrate_encounter",
]
