"""B027 deterministic combat/ability framework: abilities, effects, cooldowns, resolution.

Builds on :mod:`.damage`: every hit, including damage-over-time ticks, goes
through :func:`~.damage.resolve_damage`. No new damage maths.

Determinism
    There is no ``random`` and no wall clock. Time is an integer tick. Each roll
    is ``sha256(seed, tick, seq, label)`` mapped into ``[0, 1)``, so a session
    replayed from the same seed and the same commands reproduces every crit,
    every tick of damage and the state :meth:`CombatSession.digest` exactly.
    Effects and combatants are always processed in sorted id order.

Fail closed
    :meth:`CombatSession.cast` validates everything (actor alive, not stunned,
    known ability, cooldown, global cooldown, resource, target, cast guards)
    before mutating anything. A refused cast returns a :class:`CastResult`
    with a stable ``reason`` code and changes no state.

Extensible
    Effect behaviour is looked up by ``kind`` in an :class:`EffectRegistry`.
    Built-in kinds are ``dot``, ``hot``, ``stun``, ``armor``, ``vulnerability``
    and ``damage_mult``. Games register new kinds with an :class:`EffectHandler`.
    Cast guards (for example an economy cost check through
    ``skeleton.economy.gameplay.combat.AbilityBook``) and cast listeners plug
    in without subclassing.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .damage import (
    MAX_ARMOR,
    MAX_LEVEL,
    MAX_VULNERABILITY,
    DamageEvent,
    DamageType,
    DefenderProfile,
    resolve_damage,
)

SCHEMA = "skeleton.combat.abilities.v1"
MAX_TICKS = 10_000_000
MAX_HP = 10_000_000
MAX_STACKS = 99
MAX_COMBATANTS = 4096
MAX_EVENTS = 100_000
MIN_VULNERABILITY = 0.5
MAX_DAMAGE_MULT = 4.0
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")

# Stable refusal codes for :class:`CastResult`.
OK = "ok"
UNKNOWN_ACTOR = "unknown_actor"
UNKNOWN_TARGET = "unknown_target"
UNKNOWN_ABILITY = "unknown_ability"
ACTOR_DEAD = "actor_dead"
TARGET_DEAD = "target_dead"
STUNNED = "stunned"
ON_COOLDOWN = "on_cooldown"
ON_GLOBAL_COOLDOWN = "on_global_cooldown"
INSUFFICIENT_RESOURCE = "insufficient_resource"
INVALID_TARGET = "invalid_target"
GUARD_REFUSED = "guard_refused"


class CombatError(ValueError):
    """Malformed specs or commands. Gameplay refusals use reason codes instead."""


def _req_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise CombatError(f"{name} must match {_ID_RE.pattern}")
    return value


def _req_int(value: Any, name: str, *, minimum: int = 0, maximum: int = MAX_TICKS) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (minimum <= value <= maximum):
        raise CombatError(f"{name} must be an int in [{minimum}, {maximum}]")
    return value


def _req_num(value: Any, name: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not (minimum <= value <= maximum):
        raise CombatError(f"{name} must be a number in [{minimum}, {maximum}]")
    return float(value)


# ---------------------------------------------------------------------------
# specs
# ---------------------------------------------------------------------------

STACK_REFRESH = "refresh"  # reapply resets duration, stacks stay at 1
STACK_ADD = "stack"  # reapply adds a stack (up to max_stacks) and resets duration
STACK_IGNORE = "ignore"  # reapply while active does nothing
STACK_POLICIES = (STACK_REFRESH, STACK_ADD, STACK_IGNORE)


@dataclass(frozen=True)
class EffectSpec:
    """A timed effect applied by an ability.

    ``magnitude`` means different things per kind: damage per period for
    ``dot``, heal per period for ``hot``, armor delta for ``armor``, and a
    multiplier for ``vulnerability`` / ``damage_mult``. ``stun`` ignores it.
    """

    effect_id: str
    kind: str
    duration_ticks: int
    magnitude: float = 0.0
    period_ticks: int = 1
    dtype: DamageType = DamageType.PHYSICAL
    stacking: str = STACK_REFRESH
    max_stacks: int = 1

    def __post_init__(self) -> None:
        _req_id(self.effect_id, "effect_id")
        _req_id(self.kind, "kind")
        _req_int(self.duration_ticks, "duration_ticks", minimum=1)
        _req_int(self.period_ticks, "period_ticks", minimum=1)
        _req_num(self.magnitude, "magnitude", minimum=-MAX_ARMOR, maximum=MAX_ARMOR)
        if not isinstance(self.dtype, DamageType):
            raise CombatError("dtype must be a DamageType")
        if self.stacking not in STACK_POLICIES:
            raise CombatError(f"stacking must be one of {STACK_POLICIES}")
        _req_int(self.max_stacks, "max_stacks", minimum=1, maximum=MAX_STACKS)
        if self.stacking != STACK_ADD and self.max_stacks != 1:
            raise CombatError("max_stacks > 1 requires stacking='stack'")


TARGET_ENEMY = "enemy"
TARGET_SELF = "self"
TARGET_ANY = "any"
TARGET_KINDS = (TARGET_ENEMY, TARGET_SELF, TARGET_ANY)


@dataclass(frozen=True)
class AbilitySpec:
    """A castable ability: optional direct hit, effects, cooldown and cost."""

    ability_id: str
    cooldown_ticks: int = 0
    cost: int = 0
    damage: Optional[DamageEvent] = None
    heal: int = 0
    effects: Tuple[EffectSpec, ...] = ()
    target: str = TARGET_ENEMY
    triggers_gcd: bool = True
    tags: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _req_id(self.ability_id, "ability_id")
        _req_int(self.cooldown_ticks, "cooldown_ticks")
        _req_int(self.cost, "cost", maximum=MAX_HP)
        _req_int(self.heal, "heal", maximum=MAX_HP)
        if self.damage is not None and not isinstance(self.damage, DamageEvent):
            raise CombatError("damage must be a DamageEvent")
        if self.target not in TARGET_KINDS:
            raise CombatError(f"target must be one of {TARGET_KINDS}")
        object.__setattr__(self, "effects", tuple(self.effects))
        object.__setattr__(self, "tags", tuple(sorted(set(self.tags))))
        for tag in self.tags:
            _req_id(tag, "tag")
        seen = set()
        for effect in self.effects:
            if not isinstance(effect, EffectSpec):
                raise CombatError("effects must be EffectSpec")
            if effect.effect_id in seen:
                raise CombatError(f"duplicate effect {effect.effect_id}")
            seen.add(effect.effect_id)
        if self.damage is None and not self.heal and not self.effects:
            raise CombatError("ability must deal damage, heal, or apply an effect")


# ---------------------------------------------------------------------------
# runtime state
# ---------------------------------------------------------------------------


@dataclass
class ActiveEffect:
    spec: EffectSpec
    source_id: str
    applied_tick: int
    expires_tick: int
    stacks: int = 1
    source_level: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect_id": self.spec.effect_id,
            "kind": self.spec.kind,
            "source_id": self.source_id,
            "applied_tick": self.applied_tick,
            "expires_tick": self.expires_tick,
            "stacks": self.stacks,
            "source_level": self.source_level,
        }


@dataclass
class Combatant:
    combatant_id: str
    max_hp: int
    team: str = "neutral"
    level: int = 1
    hp: Optional[int] = None
    max_resource: int = 100
    resource: Optional[int] = None
    resource_regen: int = 0
    defense: DefenderProfile = field(default_factory=DefenderProfile)
    abilities: Tuple[str, ...] = ()
    cooldowns: Dict[str, int] = field(default_factory=dict)
    gcd_ready_tick: int = 0
    effects: Dict[str, ActiveEffect] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _req_id(self.combatant_id, "combatant_id")
        _req_id(self.team, "team")
        _req_int(self.max_hp, "max_hp", minimum=1, maximum=MAX_HP)
        _req_int(self.level, "level", minimum=1, maximum=MAX_LEVEL)
        _req_int(self.max_resource, "max_resource", maximum=MAX_HP)
        _req_int(self.resource_regen, "resource_regen", maximum=MAX_HP)
        self.hp = self.max_hp if self.hp is None else _req_int(self.hp, "hp", maximum=self.max_hp)
        self.resource = (
            self.max_resource
            if self.resource is None
            else _req_int(self.resource, "resource", maximum=self.max_resource)
        )
        if not isinstance(self.defense, DefenderProfile):
            raise CombatError("defense must be a DefenderProfile")
        self.abilities = tuple(sorted(set(_req_id(a, "ability") for a in self.abilities)))

    @property
    def alive(self) -> bool:
        return (self.hp or 0) > 0

    def has_kind(self, kind: str) -> bool:
        return any(effect.spec.kind == kind for effect in self.effects.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.combatant_id,
            "team": self.team,
            "level": self.level,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "resource": self.resource,
            "max_resource": self.max_resource,
            "cooldowns": dict(sorted(self.cooldowns.items())),
            "gcd_ready_tick": self.gcd_ready_tick,
            "effects": [self.effects[k].to_dict() for k in sorted(self.effects)],
        }


# ---------------------------------------------------------------------------
# effect registry
# ---------------------------------------------------------------------------


class EffectHandler:
    """Behaviour for one effect kind. Override any hook; defaults do nothing.

    ``defense`` / ``outgoing`` fold the effect into the holder's derived stats
    and must be pure. ``on_tick`` runs every ``period_ticks`` while active.
    """

    def on_apply(self, session: "CombatSession", holder: Combatant, effect: ActiveEffect) -> None:
        return None

    def on_tick(self, session: "CombatSession", holder: Combatant, effect: ActiveEffect) -> None:
        return None

    def on_expire(self, session: "CombatSession", holder: Combatant, effect: ActiveEffect) -> None:
        return None

    def defense(self, profile: DefenderProfile, effect: ActiveEffect) -> DefenderProfile:
        return profile

    def outgoing(self, multiplier: float, effect: ActiveEffect) -> float:
        return multiplier


class _DotHandler(EffectHandler):
    def on_tick(self, session, holder, effect):
        base = max(0.0, effect.spec.magnitude) * effect.stacks
        event = DamageEvent(base=base, dtype=effect.spec.dtype, attacker_level=effect.source_level, can_crit=False)
        session._apply_hit(effect.source_id, holder, event, label=f"dot:{effect.spec.effect_id}")


class _HotHandler(EffectHandler):
    def on_tick(self, session, holder, effect):
        session._apply_heal(effect.source_id, holder, int(round(max(0.0, effect.spec.magnitude) * effect.stacks)),
                            label=f"hot:{effect.spec.effect_id}")


class _ArmorHandler(EffectHandler):
    def defense(self, profile, effect):
        armor = min(MAX_ARMOR, max(0.0, profile.armor + effect.spec.magnitude * effect.stacks))
        return replace(profile, armor=armor)


class _VulnerabilityHandler(EffectHandler):
    def defense(self, profile, effect):
        vuln = profile.vulnerability * (effect.spec.magnitude ** effect.stacks)
        return replace(profile, vulnerability=min(MAX_VULNERABILITY, max(MIN_VULNERABILITY, vuln)))


class _DamageMultHandler(EffectHandler):
    def outgoing(self, multiplier, effect):
        return multiplier * (effect.spec.magnitude ** effect.stacks)


class EffectRegistry:
    """Maps effect ``kind`` to its :class:`EffectHandler`."""

    def __init__(self, *, builtins: bool = True) -> None:
        self._handlers: Dict[str, EffectHandler] = {}
        if builtins:
            self.register("dot", _DotHandler())
            self.register("hot", _HotHandler())
            self.register("stun", EffectHandler())
            self.register("armor", _ArmorHandler())
            self.register("vulnerability", _VulnerabilityHandler())
            self.register("damage_mult", _DamageMultHandler())

    def register(self, kind: str, handler: EffectHandler, *, replace_existing: bool = False) -> None:
        _req_id(kind, "kind")
        if not isinstance(handler, EffectHandler):
            raise CombatError("handler must be an EffectHandler")
        if kind in self._handlers and not replace_existing:
            raise CombatError(f"effect kind already registered: {kind}")
        self._handlers[kind] = handler

    def get(self, kind: str) -> EffectHandler:
        try:
            return self._handlers[kind]
        except KeyError:
            raise CombatError(f"unknown effect kind: {kind}") from None

    def kinds(self) -> Tuple[str, ...]:
        return tuple(sorted(self._handlers))


# ---------------------------------------------------------------------------
# session
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CastResult:
    ok: bool
    reason: str
    ability_id: str
    actor_id: str
    target_id: str
    tick: int
    damage: int = 0
    heal: int = 0
    crit: bool = False
    effects_applied: Tuple[str, ...] = ()
    killed: bool = False
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok, "reason": self.reason, "ability": self.ability_id, "actor": self.actor_id,
            "target": self.target_id, "tick": self.tick, "damage": self.damage, "heal": self.heal,
            "crit": self.crit, "effects": list(self.effects_applied), "killed": self.killed,
            "detail": self.detail,
        }


CastGuard = Callable[[Combatant, AbilitySpec, Combatant], Optional[str]]
CastListener = Callable[["CombatSession", CastResult], None]


class CombatSession:
    """Authoritative, replayable combat state for one encounter."""

    def __init__(
        self,
        *,
        seed: int,
        abilities: Mapping[str, AbilitySpec] | Tuple[AbilitySpec, ...] | List[AbilitySpec] = (),
        registry: Optional[EffectRegistry] = None,
        gcd_ticks: int = 0,
        max_events: int = MAX_EVENTS,
    ) -> None:
        self.seed = _req_int(seed, "seed", maximum=2**63 - 1)
        self.gcd_ticks = _req_int(gcd_ticks, "gcd_ticks")
        self.max_events = _req_int(max_events, "max_events", minimum=1, maximum=MAX_EVENTS)
        self.registry = registry or EffectRegistry()
        self.tick = 0
        self._seq = 0
        self._abilities: Dict[str, AbilitySpec] = {}
        self._combatants: Dict[str, Combatant] = {}
        self._guards: List[CastGuard] = []
        self._listeners: List[CastListener] = []
        self.events: List[Dict[str, Any]] = []
        self._log_head = hashlib.sha256(f"{SCHEMA}:{self.seed}".encode()).hexdigest()
        specs = abilities.values() if isinstance(abilities, Mapping) else abilities
        for spec in specs:
            self.register_ability(spec)

    # -- setup ---------------------------------------------------------------

    def register_ability(self, spec: AbilitySpec) -> None:
        if not isinstance(spec, AbilitySpec):
            raise CombatError("spec must be an AbilitySpec")
        if spec.ability_id in self._abilities:
            raise CombatError(f"ability already registered: {spec.ability_id}")
        for effect in spec.effects:
            self.registry.get(effect.kind)  # unknown kinds fail at registration, not mid-fight
        self._abilities[spec.ability_id] = spec

    def add(self, combatant: Combatant) -> Combatant:
        if not isinstance(combatant, Combatant):
            raise CombatError("combatant must be a Combatant")
        if combatant.combatant_id in self._combatants:
            raise CombatError(f"combatant already present: {combatant.combatant_id}")
        if len(self._combatants) >= MAX_COMBATANTS:
            raise CombatError("too many combatants")
        for ability_id in combatant.abilities:
            if ability_id not in self._abilities:
                raise CombatError(f"combatant {combatant.combatant_id} knows unknown ability {ability_id}")
        self._combatants[combatant.combatant_id] = combatant
        return combatant

    def add_cast_guard(self, guard: CastGuard) -> None:
        """``guard(actor, ability, target)`` returns ``None`` to allow or a short refusal detail."""
        if not callable(guard):
            raise CombatError("guard must be callable")
        self._guards.append(guard)

    def on_cast(self, listener: CastListener) -> None:
        if not callable(listener):
            raise CombatError("listener must be callable")
        self._listeners.append(listener)

    def combatant(self, combatant_id: str) -> Combatant:
        try:
            return self._combatants[combatant_id]
        except KeyError:
            raise CombatError(f"unknown combatant: {combatant_id}") from None

    # -- derived stats -------------------------------------------------------

    def defense_of(self, holder: Combatant) -> DefenderProfile:
        profile = holder.defense
        for key in sorted(holder.effects):
            effect = holder.effects[key]
            profile = self.registry.get(effect.spec.kind).defense(profile, effect)
        return profile

    def outgoing_multiplier(self, holder: Combatant) -> float:
        mult = 1.0
        for key in sorted(holder.effects):
            effect = holder.effects[key]
            mult = self.registry.get(effect.spec.kind).outgoing(mult, effect)
        return min(MAX_DAMAGE_MULT, max(0.0, mult))

    # -- determinism ---------------------------------------------------------

    def roll(self, label: str) -> float:
        """Next keyed roll in ``[0, 1)``; advances the sequence counter."""
        payload = f"{self.seed}:{self.tick}:{self._seq}:{label}".encode()
        self._seq += 1
        return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") / 2**64

    def _emit(self, event_kind: str, **data: Any) -> None:
        event = {"tick": self.tick, "kind": event_kind, **data}
        line = json.dumps(event, sort_keys=True, separators=(",", ":"))
        self._log_head = hashlib.sha256(f"{self._log_head}|{line}".encode()).hexdigest()
        self.events.append(event)
        if len(self.events) > self.max_events:
            del self.events[: len(self.events) - self.max_events]

    # -- resolution primitives (used by handlers) ----------------------------

    def _apply_hit(self, source_id: str, target: Combatant, event: DamageEvent, *, label: str) -> Tuple[int, bool]:
        if not target.alive:
            return 0, False
        source = self._combatants.get(source_id)
        mult = self.outgoing_multiplier(source) if source is not None and source.alive else 1.0
        if mult != 1.0:
            event = replace(event, base=min(event.base * mult, 1_000_000))
        result = resolve_damage(
            event,
            self.defense_of(target),
            crit_roll=self.roll(f"{label}:crit"),
            variance_roll=self.roll(f"{label}:var"),
        )
        dealt = min(int(target.hp or 0), result.final)
        target.hp = int(target.hp or 0) - dealt
        self._emit("damage", source=source_id, target=target.combatant_id, amount=dealt,
                   crit=result.crit, label=label, dtype=event.dtype.value)
        if not target.alive:
            self._kill(target, source_id)
        return dealt, result.crit

    def _apply_heal(self, source_id: str, target: Combatant, amount: int, *, label: str) -> int:
        if not target.alive or amount <= 0:
            return 0
        healed = min(target.max_hp - int(target.hp or 0), amount)
        target.hp = int(target.hp or 0) + healed
        self._emit("heal", source=source_id, target=target.combatant_id, amount=healed, label=label)
        return healed

    def _kill(self, target: Combatant, source_id: str) -> None:
        for key in sorted(target.effects):
            effect = target.effects.pop(key)
            self.registry.get(effect.spec.kind).on_expire(self, target, effect)
        self._emit("death", target=target.combatant_id, source=source_id)

    def apply_effect(self, source: Combatant, target: Combatant, spec: EffectSpec) -> bool:
        if not target.alive:
            return False
        handler = self.registry.get(spec.kind)
        current = target.effects.get(spec.effect_id)
        expires = self.tick + spec.duration_ticks
        if current is not None:
            if spec.stacking == STACK_IGNORE:
                return False
            if spec.stacking == STACK_ADD:
                current.stacks = min(spec.max_stacks, current.stacks + 1)
            current.applied_tick = self.tick
            current.expires_tick = expires
            current.source_id = source.combatant_id
            current.source_level = source.level
            self._emit("effect_refresh", target=target.combatant_id, effect=spec.effect_id, stacks=current.stacks)
            return True
        active = ActiveEffect(spec, source.combatant_id, self.tick, expires, 1, source.level)
        target.effects[spec.effect_id] = active
        self._emit("effect_apply", target=target.combatant_id, effect=spec.effect_id, effect_kind=spec.kind,
                   source=source.combatant_id, expires=expires)
        handler.on_apply(self, target, active)
        return True

    # -- commands ------------------------------------------------------------

    def _refuse(self, reason: str, ability_id: str, actor_id: str, target_id: str, detail: str = "") -> CastResult:
        return CastResult(False, reason, ability_id, actor_id, target_id, self.tick, detail=detail)

    def check(self, actor_id: str, ability_id: str, target_id: str) -> CastResult:
        """Validate a cast without changing any state."""
        actor = self._combatants.get(actor_id)
        if actor is None:
            return self._refuse(UNKNOWN_ACTOR, ability_id, actor_id, target_id)
        target = self._combatants.get(target_id)
        if target is None:
            return self._refuse(UNKNOWN_TARGET, ability_id, actor_id, target_id)
        spec = self._abilities.get(ability_id)
        if spec is None or ability_id not in actor.abilities:
            return self._refuse(UNKNOWN_ABILITY, ability_id, actor_id, target_id)
        if not actor.alive:
            return self._refuse(ACTOR_DEAD, ability_id, actor_id, target_id)
        if not target.alive:
            return self._refuse(TARGET_DEAD, ability_id, actor_id, target_id)
        if actor.has_kind("stun"):
            return self._refuse(STUNNED, ability_id, actor_id, target_id)
        if spec.target == TARGET_SELF and target is not actor:
            return self._refuse(INVALID_TARGET, ability_id, actor_id, target_id, "self-only")
        if spec.target == TARGET_ENEMY and (target is actor or target.team == actor.team):
            return self._refuse(INVALID_TARGET, ability_id, actor_id, target_id, "enemy-only")
        ready = actor.cooldowns.get(ability_id, 0)
        if self.tick < ready:
            return self._refuse(ON_COOLDOWN, ability_id, actor_id, target_id, f"ready_at={ready}")
        if spec.triggers_gcd and self.tick < actor.gcd_ready_tick:
            return self._refuse(ON_GLOBAL_COOLDOWN, ability_id, actor_id, target_id,
                                f"ready_at={actor.gcd_ready_tick}")
        if int(actor.resource or 0) < spec.cost:
            return self._refuse(INSUFFICIENT_RESOURCE, ability_id, actor_id, target_id,
                                f"need={spec.cost} have={actor.resource}")
        for guard in self._guards:
            detail = guard(actor, spec, target)
            if detail:
                return self._refuse(GUARD_REFUSED, ability_id, actor_id, target_id, str(detail)[:200])
        return CastResult(True, OK, ability_id, actor_id, target_id, self.tick)

    def cast(self, actor_id: str, ability_id: str, target_id: str) -> CastResult:
        verdict = self.check(actor_id, ability_id, target_id)
        if not verdict.ok:
            self._emit("cast_refused", actor=actor_id, ability=ability_id, target=target_id, reason=verdict.reason)
            return verdict
        actor = self._combatants[actor_id]
        target = self._combatants[target_id]
        spec = self._abilities[ability_id]
        actor.resource = int(actor.resource or 0) - spec.cost
        if spec.cooldown_ticks:
            actor.cooldowns[ability_id] = self.tick + spec.cooldown_ticks
        if spec.triggers_gcd and self.gcd_ticks:
            actor.gcd_ready_tick = self.tick + self.gcd_ticks
        self._emit("cast", actor=actor_id, ability=ability_id, target=target_id, cost=spec.cost)
        damage, crit, heal = 0, False, 0
        if spec.damage is not None:
            event = replace(spec.damage, attacker_level=actor.level)
            damage, crit = self._apply_hit(actor_id, target, event, label=f"cast:{ability_id}")
        if spec.heal:
            heal = self._apply_heal(actor_id, target, spec.heal, label=f"cast:{ability_id}")
        applied = tuple(e.effect_id for e in spec.effects if self.apply_effect(actor, target, e))
        result = CastResult(True, OK, ability_id, actor_id, target_id, self.tick, damage, heal, crit,
                            applied, killed=not target.alive)
        for listener in self._listeners:
            listener(self, result)
        return result

    def advance(self, ticks: int = 1) -> None:
        """Advance time: regen resources, run periodic effects, expire effects."""
        _req_int(ticks, "ticks", minimum=1)
        if self.tick + ticks > MAX_TICKS:
            raise CombatError("tick budget exhausted")
        for _ in range(ticks):
            self.tick += 1
            for cid in sorted(self._combatants):
                holder = self._combatants[cid]
                if not holder.alive:
                    continue
                if holder.resource_regen:
                    holder.resource = min(holder.max_resource, int(holder.resource or 0) + holder.resource_regen)
                for key in sorted(holder.effects):
                    effect = holder.effects.get(key)
                    if effect is None or not holder.alive:
                        continue
                    elapsed = self.tick - effect.applied_tick
                    if elapsed > 0 and elapsed % effect.spec.period_ticks == 0:
                        self.registry.get(effect.spec.kind).on_tick(self, holder, effect)
                    if holder.alive and self.tick >= effect.expires_tick and key in holder.effects:
                        holder.effects.pop(key)
                        self.registry.get(effect.spec.kind).on_expire(self, holder, effect)
                        self._emit("effect_expire", target=cid, effect=key)

    # -- state ---------------------------------------------------------------

    def state(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA,
            "seed": self.seed,
            "tick": self.tick,
            "seq": self._seq,
            "log_head": self._log_head,
            "combatants": [self._combatants[k].to_dict() for k in sorted(self._combatants)],
        }

    def digest(self) -> str:
        """sha256 over canonical state, including the hash-chained event log head."""
        blob = json.dumps(self.state(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    def winner(self) -> Optional[str]:
        """The only team with living members, or ``None`` while contested."""
        teams = sorted({c.team for c in self._combatants.values() if c.alive})
        return teams[0] if len(teams) == 1 else None


def replay(
    *,
    seed: int,
    abilities: Tuple[AbilitySpec, ...] | List[AbilitySpec],
    combatants: Callable[[], List[Combatant]],
    script: List[Tuple[Any, ...]],
    gcd_ticks: int = 0,
    registry_factory: Callable[[], EffectRegistry] = EffectRegistry,
) -> CombatSession:
    """Rebuild a session from a command script.

    The script contains ``("cast", actor, ability, target)`` and
    ``("advance", n)`` commands. Compare digests to verify determinism.
    """

    session = CombatSession(seed=seed, abilities=list(abilities), registry=registry_factory(), gcd_ticks=gcd_ticks)
    for combatant in combatants():
        session.add(combatant)
    for command in script:
        if not command:
            raise CombatError("empty command")
        if command[0] == "cast" and len(command) == 4:
            session.cast(command[1], command[2], command[3])
        elif command[0] == "advance" and len(command) == 2:
            session.advance(command[1])
        else:
            raise CombatError(f"bad command: {command!r}")
    return session


__all__ = [
    "AbilitySpec", "ActiveEffect", "CastResult", "CombatError", "CombatSession", "Combatant",
    "EffectHandler", "EffectRegistry", "EffectSpec", "SCHEMA", "STACK_ADD", "STACK_IGNORE",
    "STACK_REFRESH", "TARGET_ANY", "TARGET_ENEMY", "TARGET_SELF", "replay",
    "ACTOR_DEAD", "GUARD_REFUSED", "INSUFFICIENT_RESOURCE", "INVALID_TARGET", "ON_COOLDOWN",
    "ON_GLOBAL_COOLDOWN", "OK", "STUNNED", "TARGET_DEAD", "UNKNOWN_ABILITY", "UNKNOWN_ACTOR",
    "UNKNOWN_TARGET",
]
