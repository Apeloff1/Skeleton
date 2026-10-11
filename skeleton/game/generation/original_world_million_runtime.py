"""Executable million-config reference game: ten genres × twelve progressions.

All 1,228,800 indices address a mechanically composed bounded sandbox,
not finished native games. Original root text, regime operator, game-form
physics, and progression rules are independently typed and conserved.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError
from .original_foundation_runtime import (
    CausalAction, CausalState, available_exits, create_causal,
    restore_causal, save_causal, step_causal, validate_causal,
)
from .original_world_million_compiler import (
    AdvancedWorld, advanced_at, advanced_from_id, ADVANCED_VERSION,
)
from .original_world_play_forms import FORM_BY_ID, ARC_BY_ID
from .original_world_million_synergy import evaluate_pressure

RUNTIME_VERSION = "original-million-world-game.v1"
MAX_ACTIONS = 1000
LAYERS = ("causal", "mode", "arc")
ARC_ACTIONS = frozenset(("commit", "aid", "investigate", "choose", "reflect"))


@dataclass(frozen=True)
class ModeState:
    course: int = 0
    height: int = 0
    damage: int = 0
    shield: int = 0
    enemy: int = 8
    switches: int = 0
    gates: int = 0
    thirst: int = 0
    warmth: int = 8
    water: int = 5
    shelter: int = 0
    deposit: int = 12
    housing: int = 1
    population: int = 1
    colony_food: int = 5
    farms: int = 0
    vehicle_speed: int = 0
    vehicle_integrity: int = 12
    distance: int = 0
    corners: int = 0
    laps: int = 0
    alert: int = 0
    market_stock: int = 10
    wallet: int = 8
    goods: int = 2
    price: int = 2
    revealed: tuple[int, ...] = (0,)
    beat: int = 0
    combo: int = 0
    music_score: int = 0
    cleared: bool = False
    actions: int = 0


@dataclass(frozen=True)
class ArcState:
    chapter: int = 0
    attempts: int = 0
    legacy: int = 0
    generation: int = 0
    faction_a: int = 5
    faction_b: int = 5
    clues: int = 0
    uncertainty: int = 0
    season: int = 0
    outstanding: int = 0
    rescues: int = 0
    territory: int = 0
    civic: int = 0
    checkpoint: int = 0
    branch: str = ""
    completed: bool = False


@dataclass(frozen=True)
class AdvancedState:
    game_id: str
    causal: CausalState
    mode: ModeState
    arc: ArcState
    events: int = 0
    event_head: str = "0" * 64


@dataclass(frozen=True)
class AdvancedAction:
    layer: str
    verb: str
    amount: int = 1
    target: int = -1
    option: str = ""


@dataclass(frozen=True)
class AdvancedReceipt:
    event_id: str
    number: int
    layer: str
    verb: str
    changes: tuple[str, ...]
    causal_receipt: str = ""


def _digest(value: object) -> str:
    return sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _require(value: int, low: int, high: int, name: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise FoundationError("invalid " + name)


MODE_BOUNDS = {
    "course": (0, 20), "height": (0, 3),
    "damage": (0, 20), "shield": (0, 10),
    "enemy": (0, 20), "switches": (0, 7), "gates": (0, 4),
    "thirst": (0, 20), "warmth": (0, 20),
    "water": (0, 100), "shelter": (0, 5),
    "deposit": (0, 100), "housing": (0, 10),
    "population": (0, 20), "colony_food": (0, 100),
    "farms": (0, 8), "vehicle_speed": (0, 6),
    "vehicle_integrity": (0, 20), "distance": (0, 200),
    "corners": (0, 2), "laps": (0, 10), "alert": (0, 20),
    "market_stock": (0, 100), "wallet": (0, 200),
    "goods": (0, 100), "price": (1, 8),
    "beat": (0, 1000), "combo": (0, 100),
    "music_score": (0, 1000), "actions": (0, MAX_ACTIONS),
}
ARC_BOUNDS = {
    "chapter": (0, 100), "attempts": (0, 100),
    "legacy": (0, 100), "generation": (0, 100),
    "faction_a": (0, 20), "faction_b": (0, 20),
    "clues": (0, 100), "uncertainty": (0, 100),
    "season": (0, 3), "outstanding": (0, 100),
    "rescues": (0, 100), "territory": (0, 100),
    "civic": (0, 100), "checkpoint": (0, 1000000),
}


def validate_game(game: AdvancedState) -> AdvancedWorld:
    if not isinstance(game, AdvancedState):
        raise FoundationError("invalid advanced game state")
    law = advanced_from_id(game.game_id)
    validate_causal(game.causal)
    if game.causal.foundation_id != law.mode.base.foundation_id:
        raise FoundationError("original world law identity mismatch")
    if not isinstance(game.mode, ModeState) or not isinstance(game.arc, ArcState):
        raise FoundationError("invalid genre or progression state")
    for name, (minimum, maximum) in MODE_BOUNDS.items():
        _require(getattr(game.mode, name), minimum, maximum, "mode." + name)
    for name, (minimum, maximum) in ARC_BOUNDS.items():
        _require(getattr(game.arc, name), minimum, maximum, "arc." + name)
    if not isinstance(game.mode.cleared, bool) or not isinstance(game.arc.completed, bool):
        raise FoundationError("invalid victory status flag")
    if game.arc.branch not in ("", "care", "power"):
        raise FoundationError("unknown story branch")
    if not isinstance(game.mode.revealed, tuple) or 0 not in game.mode.revealed:
        raise FoundationError("incomplete exploration history")
    if (len(set(game.mode.revealed)) != len(game.mode.revealed) or
            len(game.mode.revealed) > 12 or any(
                type(room) is not int or not 0 <= room < 12 for room in game.mode.revealed
            )):
        raise FoundationError("invalid visibility ledger")
    if game.mode.population > game.mode.housing * 3:
        raise FoundationError("colony population exceeds shelter capacity")
    _require(game.events, 0, MAX_ACTIONS, "event count")
    if (not isinstance(game.event_head, str) or len(game.event_head) != 64
            or any(ch not in "0123456789abcdef" for ch in game.event_head)):
        raise FoundationError("invalid advanced event receipt")
    if law.arc.continuation_policy == "unwinnable" and game.arc.completed:
        raise FoundationError("unwinnable continuation cannot have final completion")
    return law


def create_advanced(index: int | str) -> AdvancedState:
    law = advanced_at(index) if type(index) is int else advanced_from_id(index)
    state = AdvancedState(law.advanced_id,
                          create_causal(law.mode.base.foundation_id),
                          ModeState(), ArcState())
    validate_game(state)
    return state


def _debit(causal: CausalState, *, energy: int = 0, supplies: int = 0,
           evidence: int = 0, reserve: int = 0,
           trust: int = 0) -> CausalState:
    costs = {"energy": energy, "supplies": supplies,
             "evidence": evidence, "reserve": reserve, "trust": trust}
    if any(type(cost) is not int or cost < 0 for cost in costs.values()):
        raise FoundationError("invalid resource expenditure")
    if any(getattr(causal, key) < cost for key, cost in costs.items()):
        raise FoundationError("infeasible world resource expenditure")
    return replace(causal, **{
        key: getattr(causal, key) - cost for key, cost in costs.items()
    })


def _mode_operation(
    law: AdvancedWorld, causal: CausalState, mode: ModeState, action: AdvancedAction
) -> tuple[CausalState, ModeState, tuple[str, ...]]:
    form = law.mode.form.form_id
    if action.verb not in FORM_BY_ID[form].mechanics:
        raise FoundationError("mechanic unsupported in this gameplay form")
    if causal.action_points < 1:
        raise FoundationError("end turn to refresh control budget")
    # Clearing a milestone is not permission to terminate an open world.
    # Actions remain available after victory; arcs decide whether a chapter
    # is closed, continued, replayed or forever unfinishable.
    n, option, target = action.amount, action.option, action.target
    causal = replace(causal, action_points=causal.action_points - 1)
    effects = []
    if form == "platform":
        if action.verb == "step":
            landing = min(20, mode.course + n)
            exposed = any(cell % 5 == 4 for cell in range(mode.course + 1, landing + 1))
            if exposed and mode.height == 0 and mode.shield == 0:
                raise FoundationError("a grounded path crosses a gap; jump or brace first")
            causal = _debit(causal, energy=n)
            mode = replace(mode, course=landing,
                           shield=mode.shield - (1 if exposed and mode.height == 0 else 0))
        elif action.verb == "jump":
            causal = _debit(causal, energy=2)
            mode = replace(mode, course=min(20, mode.course + n),
                           height=min(3, 1 + n))
        else:
            causal = _debit(causal, supplies=n)
            mode = replace(mode, shield=min(10, mode.shield + n))
        effects.append("Grounded traversal, collision and finite jump energy evaluated")
    elif form == "puzzle":
        if action.verb == "toggle":
            if target not in (0, 1, 2):
                raise FoundationError("switch target is 0, 1 or 2")
            causal = _debit(causal, energy=1)
            mode = replace(mode, switches=mode.switches ^ (1 << target))
        elif action.verb == "pass":
            if mode.switches != 5:
                raise FoundationError("locked door requires switches 0 and 2")
            mode = replace(mode, gates=mode.gates + 1)
        else:
            causal = _debit(causal, evidence=n)
            effects.append("Verified one complete switch-state proof")
        effects.append("Three-bit circuit state checked against the door")
    elif form == "tactics":
        if action.verb == "strike":
            causal = _debit(causal, energy=n)
            mode = replace(mode, enemy=max(0, mode.enemy - (2 * n)))
            if mode.enemy:
                mode = replace(mode, damage=min(20, mode.damage + max(0, 2 - mode.shield)),
                               shield=max(0, mode.shield - 2))
        elif action.verb == "guard":
            causal = _debit(causal, energy=1)
            mode = replace(mode, shield=min(10, mode.shield + 3 * n))
        else:
            causal = _debit(causal, trust=n)
            mode = replace(mode, enemy=max(0, mode.enemy - n))
        effects.append("Opponent health and guarded counterstrike accounted")
    elif form == "survival":
        if action.verb == "drink":
            if mode.water < n:
                raise FoundationError("water inventory depleted")
            mode = replace(mode, water=mode.water - n,
                           thirst=max(0, mode.thirst - 4 * n))
        elif action.verb == "shelter":
            causal = _debit(causal, supplies=2 * n)
            mode = replace(mode, shelter=min(5, mode.shelter + n),
                           warmth=min(20, mode.warmth + 2 * n))
        else:
            if mode.deposit < n:
                raise FoundationError("local resource deposit exhausted")
            causal = _debit(causal, energy=n)
            mode = replace(mode, deposit=mode.deposit - n,
                           water=min(100, mode.water + n))
        effects.append("Exposure, hydration and finite supplies revised")
    elif form == "colony":
        if action.verb == "construct":
            causal = _debit(causal, supplies=3 * n)
            mode = replace(mode, housing=min(10, mode.housing + n))
        elif action.verb == "cultivate":
            causal = _debit(causal, supplies=n)
            mode = replace(mode, farms=min(8, mode.farms + n))
        else:
            causal = _debit(causal, supplies=n)
            mode = replace(mode, colony_food=min(100, mode.colony_food + n),
                           damage=max(0, mode.damage - n))
        effects.append("Population support, materials and food systems reconciled")
    elif form == "racing":
        if action.verb == "accelerate":
            causal = _debit(causal, energy=n)
            speed = min(6, mode.vehicle_speed + n)
            next_gate = 12 if mode.corners == 0 else (28 if mode.corners == 1 else 200)
            mode = replace(mode, vehicle_speed=speed,
                           distance=min(next_gate, mode.distance + speed))
        elif action.verb == "brake":
            mode = replace(mode, vehicle_speed=max(0, mode.vehicle_speed - n))
        else:
            if mode.vehicle_speed == 0:
                raise FoundationError("cannot corner a stopped vehicle")
            required = 12 if mode.corners == 0 else 28
            if mode.corners >= 2 or mode.distance < required:
                raise FoundationError("turning requires reaching the next marked course bend")
            wear = max(1, mode.vehicle_speed - 3) * n
            mode = replace(mode, corners=mode.corners + 1,
                           distance=min(200, mode.distance + mode.vehicle_speed),
                           vehicle_integrity=max(0, mode.vehicle_integrity - wear))
        if mode.distance >= 40 and mode.corners == 2 and mode.vehicle_integrity > 0:
            mode = replace(mode, laps=1)
        effects.append("Track distance, mandatory physical corners and vehicle wear accounted")
    elif form == "stealth":
        if action.verb == "sneak":
            causal = _debit(causal, energy=n)
            mode = replace(mode, course=min(20, mode.course + n),
                           alert=min(20, mode.alert + n))
        elif action.verb == "distract":
            causal = _debit(causal, supplies=n)
            mode = replace(mode, alert=max(0, mode.alert - 3 * n))
        else:
            causal = _debit(causal, energy=1)
            mode = replace(mode, alert=max(0, mode.alert - 2 * n))
        effects.append("Patrol visibility and bounded alertness changed")
    elif form == "commerce":
        if action.verb == "buy":
            cost = mode.price * n
            if mode.wallet < cost or mode.market_stock < n:
                raise FoundationError("purchase lacks cash or market inventory")
            mode = replace(mode, wallet=mode.wallet - cost, goods=mode.goods + n,
                           market_stock=mode.market_stock - n)
        elif action.verb == "sell":
            if mode.goods < n or mode.wallet + n * mode.price > 200:
                raise FoundationError("sale lacks goods or wallet capacity")
            mode = replace(mode, wallet=mode.wallet + mode.price * n,
                           goods=mode.goods - n, market_stock=mode.market_stock + n)
        else:
            causal = _debit(causal, evidence=n)
            mode = replace(mode, price=1 + (causal.tick + n) % 5)
        effects.append("Market inventory and wallet changed by quoted finite price")
    elif form == "exploration":
        if action.verb == "explore":
            choices = [x for x in available_exits(causal) if x not in mode.revealed]
            if not choices:
                raise FoundationError("no adjacent unseen site from present position")
            causal = _debit(causal, energy=n)
            destination = choices[0]
            causal = replace(causal, position=destination,
                             investigated=tuple(sorted(
                                 set(causal.investigated) | {destination})))
            mode = replace(mode, revealed=tuple(sorted(
                set(mode.revealed) | {destination})))
        elif action.verb == "resupply":
            causal = _debit(causal, reserve=n)
            causal = replace(causal, supplies=causal.supplies + n)
        else:
            causal = _debit(causal, evidence=n)
            # This is a documented chart action, not a free discovery.
            mode = replace(mode, music_score=min(1000, mode.music_score + n))
        effects.append("Physical navigation and independent discovery ledger revised")
    else:  # rhythm
        expected = (0, 2, 1, 3)[mode.beat % 4]
        if action.verb == "tap":
            if target not in (0, 1, 2, 3):
                raise FoundationError("note position must be 0..3")
            causal = _debit(causal, energy=1)
            good = target == expected
            mode = replace(mode, beat=mode.beat + 1,
                           combo=min(100, mode.combo + 1) if good else 0,
                           music_score=min(1000, mode.music_score + (2 if good else 0)))
        elif action.verb == "hold":
            causal = _debit(causal, energy=2)
            mode = replace(mode, beat=mode.beat + n,
                           music_score=min(1000, mode.music_score + 1), combo=0)
        else:
            causal = _debit(causal, evidence=n)
            mode = replace(mode, shield=min(10, mode.shield + n))
        effects.append("Beat timing, score and errors accounted without free combo")
    mode = replace(mode, actions=mode.actions + 1)
    return causal, mode, tuple(effects)


def _form_completed(form: str, mode: ModeState, tick: int) -> bool:
    return {
        "platform": mode.course >= 12 and mode.damage < 12,
        "puzzle": mode.gates >= 1,
        "tactics": mode.enemy == 0,
        "survival": tick >= 6 and mode.warmth > 0 and mode.thirst < 15,
        "colony": mode.housing >= 3 and mode.population >= 3,
        "racing": mode.laps >= 1 and mode.vehicle_integrity > 0,
        "stealth": mode.course >= 10 and mode.alert < 10,
        "commerce": mode.wallet >= 14 and mode.goods >= 1,
        "exploration": len(mode.revealed) >= 6,
        "rhythm": mode.combo >= 4,
    }[form]


def _arc_operation(
    law: AdvancedWorld, causal: CausalState, mode: ModeState,
    arc: ArcState, action: AdvancedAction
) -> tuple[CausalState, ModeState, ArcState, tuple[str, ...]]:
    name, n, verb = law.arc.arc_id, action.amount, action.verb
    if verb not in ARC_ACTIONS:
        raise FoundationError("unknown progression operation")
    if causal.action_points < 1:
        raise FoundationError("world turn is out of player actions")
    causal = replace(causal, action_points=causal.action_points - 1)
    if verb == "reflect":
        causal = _debit(causal, energy=n)
        arc = replace(arc, legacy=min(100, arc.legacy + n))
        return causal, mode, arc, ("Preserved experience, not newly minted resources",)
    if verb == "investigate":
        causal = _debit(causal, evidence=n)
        arc = replace(arc, clues=min(100, arc.clues + n),
                      uncertainty=max(0, arc.uncertainty - n))
        return causal, mode, arc, ("Spent verifiable evidence on the continuation",)
    if verb == "aid":
        causal = _debit(causal, supplies=2 * n)
        arc = replace(arc, rescues=min(100, arc.rescues + n),
                      outstanding=max(0, arc.outstanding - n))
        if name == "factions":
            arc = replace(arc, faction_b=min(20, arc.faction_b + n))
        elif name == "civilization":
            arc = replace(arc, civic=min(100, arc.civic + n))
        return causal, mode, arc, ("Delivered finite relief with persistent recipients",)
    if verb == "choose":
        if name not in ("branching", "factions") or action.option not in ("care", "power"):
            raise FoundationError("irreversible choice unavailable to this continuation")
        if arc.branch:
            raise FoundationError("story decision already irreversible")
        if action.option == "care":
            causal = _debit(causal, supplies=n)
            arc = replace(arc, branch="care",
                          faction_b=min(20, arc.faction_b + n))
        else:
            causal = _debit(causal, trust=n)
            arc = replace(arc, branch="power",
                          faction_a=min(20, arc.faction_a + n))
        return causal, mode, arc, ("Selected one persistent noncosmetic narrative fork",)
    # Commit: each arc has a different success/failure gate and ledger.
    if name == "chapters":
        if not mode.cleared:
            raise FoundationError("complete the gameplay objective first")
        arc = replace(arc, chapter=min(100, arc.chapter + 1),
                      completed=True)
    elif name == "endless":
        causal = _debit(causal, supplies=n)
        arc = replace(arc, chapter=min(100, arc.chapter + n))
    elif name == "roguelite":
        if causal.evidence < n:
            raise FoundationError("a new expedition needs proof of experience")
        causal = _debit(causal, evidence=n)
        arc = replace(arc, attempts=min(100, arc.attempts + 1),
                      legacy=min(100, arc.legacy + n))
        mode = ModeState()
    elif name == "dynasty":
        if arc.legacy < n:
            raise FoundationError("intergenerational milestone needs a durable legacy")
        arc = replace(arc, generation=min(100, arc.generation + n),
                      legacy=arc.legacy - n)
    elif name == "factions":
        if not arc.branch:
            raise FoundationError("faction campaign requires a choice")
        arc = replace(arc, chapter=min(100, arc.chapter + n))
    elif name == "sandbox":
        causal = _debit(causal, supplies=n)
        arc = replace(arc, civic=min(100, arc.civic + n))
    elif name == "mystery":
        if arc.clues < 3 * n:
            causal = _debit(causal, trust=n)
            arc = replace(arc, uncertainty=min(100, arc.uncertainty + n))
            return causal, mode, arc, (
                "Unsupported conclusion recorded as uncertain and reduced public trust",
            )
        arc = replace(arc, clues=arc.clues - 3 * n, chapter=arc.chapter + n)
    elif name == "seasonal":
        causal = _debit(causal, supplies=n)
        arc = replace(arc, civic=min(100, arc.civic + n))
    elif name == "rescue":
        if arc.rescues < n:
            raise FoundationError("a rescue milestone requires delivered aid")
        arc = replace(arc, chapter=min(100, arc.chapter + n))
    elif name == "campaign":
        if not mode.cleared:
            raise FoundationError("the mission must resolve before territorial credit")
        causal = _debit(causal, supplies=n)
        arc = replace(arc, territory=min(100, arc.territory + n),
                      chapter=min(100, arc.chapter + n))
    elif name == "civilization":
        if arc.civic < n:
            raise FoundationError("institution requires real community investment")
        arc = replace(arc, civic=arc.civic - n, chapter=min(100, arc.chapter + n))
    else:  # branching
        if not arc.branch:
            raise FoundationError("branching finale requires an irreversible choice")
        arc = replace(arc, chapter=min(100, arc.chapter + n))
    if name not in ("endless", "rescue", "sandbox") and arc.chapter >= 3:
        arc = replace(arc, completed=True)
    return causal, mode, arc, ("Advanced a mechanically gated authored continuation contract",)


def _genre_stress(mode: ModeState, form: str) -> int:
    """Physical player-facing stress, not difficulty labels or visual style."""
    raw = {
        "platform": mode.damage + (3 if mode.course % 5 == 4 and mode.height == 0 else 0),
        "puzzle": (0 if mode.gates else (2 if mode.switches != 5 else 1)),
        "tactics": mode.damage * 2 + max(0, mode.enemy - mode.shield),
        "survival": mode.thirst + max(0, 8 - mode.warmth),
        "colony": max(0, mode.population * 2 - mode.colony_food) + mode.damage,
        "racing": max(0, 12 - mode.vehicle_integrity) * 2 + max(0, mode.vehicle_speed - 3),
        "stealth": mode.alert + mode.damage,
        "commerce": max(0, 8 - mode.wallet) + max(0, 2 - mode.goods),
        "exploration": max(0, 6 - len(mode.revealed)),
        "rhythm": (3 if mode.beat > 0 and mode.combo == 0 else 0),
    }[form]
    return min(100, max(0, raw))


def _advance_world(
    law: AdvancedWorld, causal: CausalState, mode: ModeState,
    arc: ArcState,
) -> tuple[CausalState, ModeState, ArcState, tuple[str, ...]]:
    form, name, tick = law.mode.form.form_id, law.arc.arc_id, causal.tick
    messages = []
    if form == "platform" and mode.height:
        mode = replace(mode, height=max(0, mode.height - 1))
    elif form == "tactics" and mode.enemy and mode.shield < 2:
        mode = replace(mode, damage=min(20, mode.damage + 1))
    elif form == "survival":
        thirst = min(20, mode.thirst + 2)
        warmth = max(0, mode.warmth - (0 if mode.shelter else 2))
        mode = replace(mode, thirst=thirst, warmth=warmth,
                       damage=min(20, mode.damage + (1 if thirst >= 12 or not warmth else 0)))
        messages.append("Weather and hydration caused persistent survival pressure")
    elif form == "colony":
        food = mode.colony_food - mode.population
        if food < 0:
            mode = replace(mode, damage=min(20, mode.damage - food),
                           colony_food=0)
        else:
            mode = replace(mode, colony_food=min(100, food + mode.farms * 2))
        if mode.population < mode.housing * 3 and mode.colony_food >= 3:
            mode = replace(mode, population=mode.population + 1)
    elif form == "racing" and mode.vehicle_speed:
        mode = replace(mode, vehicle_speed=max(0, mode.vehicle_speed - 1))
    elif form == "stealth":
        mode = replace(mode, alert=min(20, mode.alert + (tick % 3)))
        if mode.alert >= 15:
            mode = replace(mode, damage=min(20, mode.damage + 1))
    elif form == "commerce":
        mode = replace(mode, price=1 + (tick % 5))
    elif form == "rhythm" and mode.beat % 8 == 7:
        mode = replace(mode, combo=0)
    if tick % law.arc.checkpoint_interval == 0:
        arc = replace(arc, checkpoint=tick)
        if name == "endless":
            causal = replace(causal, hazard=min(100, causal.hazard + 2))
            messages.append("An endless world's challenges intensified without final victory")
        elif name == "roguelite":
            arc = replace(arc, attempts=min(100, arc.attempts + 1),
                          legacy=min(100, arc.legacy + 1))
            mode = ModeState()
            messages.append("Run reset while durable experience survived")
        elif name == "dynasty":
            arc = replace(arc, generation=min(100, arc.generation + 1),
                          outstanding=min(100, arc.outstanding + 1))
            messages.append("Next generation inherited outstanding duties")
        elif name == "factions":
            if abs(arc.faction_a - arc.faction_b) >= 4:
                causal = replace(causal, hazard=min(100, causal.hazard + 2))
                messages.append("Imbalanced factions increased real conflict exposure")
        elif name == "sandbox":
            mode = replace(mode, deposit=min(100, mode.deposit + 2))
            messages.append("Sandbox resource sites renewed, never producing a final credit roll")
        elif name == "mystery":
            arc = replace(arc, uncertainty=min(100, arc.uncertainty + 1))
            messages.append("Uninvestigated questions became harder to settle")
        elif name == "seasonal":
            arc = replace(arc, season=(arc.season + 1) % 4)
            mode = replace(mode, warmth=max(0, mode.warmth - (2 if arc.season == 3 else 0)))
            messages.append("Season changed and exposed current preparations")
        elif name == "rescue":
            arc = replace(arc, outstanding=min(100, arc.outstanding + 2))
            messages.append("Two new distant aid needs entered an unfinishable ledger")
        elif name == "campaign":
            if arc.territory > causal.reserve:
                causal = replace(causal, hazard=min(100, causal.hazard + 1))
                messages.append("Overextended campaign raised logistical danger")
        elif name == "civilization":
            if arc.civic < 1:
                causal = replace(causal, trust=max(0, causal.trust - 1))
                messages.append("Neglected public institutions reduced legitimacy")
        elif name == "branching" and arc.branch:
            if arc.branch == "care":
                causal = replace(causal, trust=min(100, causal.trust + 1))
            else:
                causal = replace(causal, hazard=min(100, causal.hazard + 1))
            messages.append("The past irrevocable choice continued to shape the future")
    pressure = evaluate_pressure(
        law.mode.base.domain, form, name, _genre_stress(mode, form),
        tick, law.arc.checkpoint_interval,
    )
    if pressure.triggered:
        n = pressure.amount
        if pressure.consequence == "hazard":
            causal = replace(causal, hazard=min(100, causal.hazard + n))
        elif pressure.consequence == "duty":
            causal = replace(causal, duty=min(1000, causal.duty + n))
        elif pressure.consequence == "trust":
            causal = replace(causal, trust=max(0, causal.trust - n))
        elif pressure.consequence == "reserve":
            causal = replace(causal, reserve=max(0, causal.reserve - n))
        elif pressure.consequence == "legacy":
            arc = replace(arc, legacy=min(100, arc.legacy + n))
        elif pressure.consequence == "outstanding":
            arc = replace(arc, outstanding=min(100, arc.outstanding + n))
        elif pressure.consequence == "uncertainty":
            arc = replace(arc, uncertainty=min(100, arc.uncertainty + n))
        elif pressure.consequence == "civic":
            arc = replace(arc, civic=max(0, arc.civic - n))
        elif pressure.consequence == "warmth":
            mode = replace(mode, warmth=max(0, mode.warmth - n))
        else:
            raise FoundationError("unsupported cross-layer consequence")
        messages.append("World-law, gameplay and continuation strain: " + pressure.explanation)
    return causal, mode, arc, tuple(messages)


def step_advanced(
    state: AdvancedState, action: AdvancedAction
) -> tuple[AdvancedState, AdvancedReceipt]:
    law = validate_game(state)
    if state.events >= MAX_ACTIONS:
        raise FoundationError("advanced game event budget exhausted")
    if not isinstance(action, AdvancedAction) or action.layer not in LAYERS:
        raise FoundationError("unsupported action layer")
    _require(action.amount, 1, 3, "action amount")
    _require(action.target, -1, 11, "action target")
    if not isinstance(action.verb, str) or not action.verb or len(action.verb) > 64:
        raise FoundationError("invalid advanced action verb")
    if not isinstance(action.option, str) or len(action.option) > 32:
        raise FoundationError("invalid advanced action choice")
    causal, mode, arc = state.causal, state.mode, state.arc
    causal_receipt = ""
    if action.layer == "causal":
        causal, receipt = step_causal(causal, CausalAction(
            action.verb, action.amount, action.option, action.target,
        ))
        causal_receipt = receipt.event_hash
        messages = receipt.changes
        if action.verb == "end_turn":
            causal, mode, arc, next_messages = _advance_world(law, causal, mode, arc)
            messages += next_messages
    elif action.layer == "mode":
        causal, mode, messages = _mode_operation(law, causal, mode, action)
    else:
        causal, mode, arc, messages = _arc_operation(law, causal, mode, arc, action)
    if not mode.cleared and _form_completed(law.mode.form.form_id, mode, causal.tick):
        mode = replace(mode, cleared=True)
        messages += ("Genre objective was completed with accounted actions",)
    updated = replace(state, causal=causal, mode=mode, arc=arc)
    evidence = _digest({
        "schema": RUNTIME_VERSION, "prior": state.event_head,
        "world": law.design_id, "from": asdict(state),
        "to": asdict(updated), "action": asdict(action),
        "messages": messages, "base_receipt": causal_receipt,
    })
    outcome = replace(updated, events=state.events + 1, event_head=evidence)
    validate_game(outcome)
    return outcome, AdvancedReceipt(
        evidence, outcome.events, action.layer, action.verb,
        tuple(messages), causal_receipt,
    )


def replay_advanced(
    index: int, actions: tuple[AdvancedAction, ...],
) -> tuple[AdvancedState, tuple[AdvancedReceipt, ...]]:
    if not isinstance(actions, tuple) or len(actions) > MAX_ACTIONS:
        raise FoundationError("advanced replay requires a bounded tuple")
    state = create_advanced(index)
    history = []
    for action in actions:
        state, receipt = step_advanced(state, action)
        history.append(receipt)
    return state, tuple(history)


def save_advanced(state: AdvancedState) -> str:
    law = validate_game(state)
    payload = {
        "schema": RUNTIME_VERSION, "design_id": law.design_id,
        "game_id": state.game_id,
        "causal": json.loads(save_causal(state.causal)),
        "mode": asdict(state.mode), "arc": asdict(state.arc),
        "events": state.events, "event_head": state.event_head,
    }
    return json.dumps(
        {"payload": payload, "checksum": _digest(payload)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def restore_advanced(text: str) -> AdvancedState:
    if not isinstance(text, str) or len(text.encode("utf-8")) > 131072:
        raise FoundationError("invalid or oversized advanced save")
    try:
        envelope = json.loads(text)
        if set(envelope) != {"payload", "checksum"}:
            raise FoundationError("unexpected save envelope")
        payload = envelope["payload"]
        if (set(payload) != {
                "schema", "design_id", "game_id", "causal",
                "mode", "arc", "events", "event_head",
            } or payload["schema"] != RUNTIME_VERSION or
                envelope["checksum"] != _digest(payload)):
            raise FoundationError("advanced save integrity mismatch")
        mode_raw, arc_raw = payload["mode"], payload["arc"]
        if (set(mode_raw) != set(ModeState.__dataclass_fields__)
                or set(arc_raw) != set(ArcState.__dataclass_fields__)):
            raise FoundationError("unexpected advanced save fields")
        mode_raw["revealed"] = tuple(mode_raw["revealed"])
        state = AdvancedState(
            payload["game_id"],
            restore_causal(json.dumps(payload["causal"])),
            ModeState(**mode_raw), ArcState(**arc_raw),
            payload["events"], payload["event_head"],
        )
        law = validate_game(state)
        if law.design_id != payload["design_id"]:
            raise FoundationError("world source identity differs from save")
        return state
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        raise FoundationError("advanced save rejected") from exc
