"""Deterministic mechanics replay contract.

Provider-neutral record/replay/compare for combat, progression, economy, and
AI-behavior transitions. Consumes :mod:`skeleton.game.mechanics` without
rewriting it. Clock and entropy are explicit trace inputs; process globals
such as ``time.time`` and ``random.*`` are never read.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from skeleton.game.mechanics import (
    AIBehaviorSpec,
    CombatSystemSpec,
    EconomySystemSpec,
    GameMechanicsError,
    GameMechanicsGenerator,
    ProgressionSystemSpec,
)
from skeleton.kernel.errors import KernelError

REPLAY_SCHEMA: Final = "game.mechanics.replay"
REPLAY_SCHEMA_VERSION: Final = 1

MAX_STEPS: Final = 64
MAX_TRACE_BYTES: Final = 65_536
MAX_SEED: Final = 2_147_483_647
MAX_TICK: Final = 1_000_000
MAX_TOKEN_CHARS: Final = 64
MAX_PAYLOAD_KEYS: Final = 8
MAX_CANONICAL_DEPTH: Final = 16
MAX_CANONICAL_ITEMS: Final = 256
MAX_DAMAGE: Final = 10_000
MAX_XP: Final = 1_000_000
MAX_DELTA: Final = 1_000_000
STARTING_HP: Final = 100
DIGEST_LENGTH: Final = 64

STEP_KINDS: Final[frozenset[str]] = frozenset(
    {"combat", "progression", "economy", "ai_behavior"}
)
STEP_ACTIONS: Final[dict[str, frozenset[str]]] = {
    "combat": frozenset({"strike"}),
    "progression": frozenset({"award_xp"}),
    "economy": frozenset({"transact"}),
    "ai_behavior": frozenset({"transition"}),
}

_TRACE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "schema_version",
        "seed",
        "tick",
        "inputs",
        "steps",
        "spec_digest",
        "state_digest",
        "result_digest",
        "step_digests",
    }
)
_INPUT_KEYS: Final[tuple[str, ...]] = (
    "combat",
    "progression",
    "economy",
    "ai_behavior",
)
_STEP_KEYS: Final[frozenset[str]] = frozenset({"kind", "action", "at_tick", "payload"})
_UUID_RE: Final = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_DIGEST_RE: Final = re.compile(r"^[0-9a-f]{64}$")


class GameReplayError(KernelError):
    """Fail-closed replay contract error."""

    code = "GAME.REPLAY"
    http_status = 422


@dataclass(frozen=True, slots=True)
class ReplayStep:
    kind: str
    action: str
    at_tick: int
    payload: Mapping[str, Any]

    def to_canonical(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "action": self.action,
            "at_tick": self.at_tick,
            "payload": _canonical_json_value(dict(self.payload)),
        }


@dataclass(frozen=True, slots=True)
class ReplayTrace:
    schema: str
    schema_version: int
    seed: int
    tick: int
    inputs: Mapping[str, Any]
    steps: tuple[ReplayStep, ...]
    spec_digest: str
    state_digest: str
    result_digest: str
    step_digests: tuple[str, ...]

    def to_canonical(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "seed": self.seed,
            "tick": self.tick,
            "inputs": _canonical_json_value(dict(self.inputs)),
            "steps": [step.to_canonical() for step in self.steps],
            "spec_digest": self.spec_digest,
            "state_digest": self.state_digest,
            "result_digest": self.result_digest,
            "step_digests": list(self.step_digests),
        }


@dataclass(frozen=True, slots=True)
class ReplayMismatch:
    field: str
    expected: str
    actual: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReplayComparison:
    identical: bool
    mismatches: tuple[ReplayMismatch, ...]

    def reject_if_divergent(self) -> None:
        if self.identical:
            return
        first = self.mismatches[0]
        raise GameReplayError(
            "divergent mechanics execution",
            context={
                "reason": "divergence",
                "field": first.field,
                "expected": first.expected,
                "actual": first.actual,
                "mismatch_count": len(self.mismatches),
            },
        )


class MechanicsReplay:
    """Record, replay, compare, and reject mechanics executions."""

    def record(
        self,
        *,
        seed: int,
        tick: int,
        steps: Sequence[ReplayStep | Mapping[str, Any]],
        combat: CombatSystemSpec | Mapping[str, Any] | None = None,
        progression: ProgressionSystemSpec | Mapping[str, Any] | None = None,
        economy: EconomySystemSpec | Mapping[str, Any] | None = None,
        ai_behavior: AIBehaviorSpec | Mapping[str, Any] | None = None,
    ) -> ReplayTrace:
        seed = _require_int("seed", seed, minimum=0, maximum=MAX_SEED)
        tick = _require_int("tick", tick, minimum=0, maximum=MAX_TICK)
        parsed_steps = _parse_steps(steps)
        inputs = {
            "combat": _combat_input(combat),
            "progression": _progression_input(progression),
            "economy": _economy_input(economy),
            "ai_behavior": _ai_input(ai_behavior),
        }
        return _execute(seed=seed, tick=tick, inputs=inputs, steps=parsed_steps)

    def replay(self, trace: ReplayTrace | Mapping[str, Any] | str | bytes) -> ReplayTrace:
        recorded = parse_trace(trace)
        if recorded.schema != REPLAY_SCHEMA or recorded.schema_version != REPLAY_SCHEMA_VERSION:
            raise GameReplayError(
                "incompatible replay schema",
                context={
                    "reason": "version_mismatch",
                    "expected_schema": REPLAY_SCHEMA,
                    "expected_version": REPLAY_SCHEMA_VERSION,
                    "actual_schema": recorded.schema,
                    "actual_version": recorded.schema_version,
                },
            )
        fresh = _execute(
            seed=recorded.seed,
            tick=recorded.tick,
            inputs=dict(recorded.inputs),
            steps=recorded.steps,
        )
        digest_checks = (
            ("spec_digest", recorded.spec_digest, fresh.spec_digest),
            ("state_digest", recorded.state_digest, fresh.state_digest),
            ("result_digest", recorded.result_digest, fresh.result_digest),
        )
        for field, expected, actual in digest_checks:
            if expected != actual:
                raise GameReplayError(
                    "divergent mechanics execution",
                    context={
                        "reason": "divergence",
                        "field": field,
                        "expected": expected,
                        "actual": actual,
                    },
                )
        if recorded.step_digests != fresh.step_digests:
            raise GameReplayError(
                "divergent mechanics execution",
                context={
                    "reason": "divergence",
                    "field": "step_digests",
                    "expected": list(recorded.step_digests),
                    "actual": list(fresh.step_digests),
                },
            )
        return fresh

    def compare(
        self,
        expected: ReplayTrace | Mapping[str, Any] | str | bytes,
        actual: ReplayTrace | Mapping[str, Any] | str | bytes,
    ) -> ReplayComparison:
        left = parse_trace(expected)
        right = parse_trace(actual)
        mismatches: list[ReplayMismatch] = []
        checks = (
            ("schema", left.schema, right.schema, "schema divergence"),
            (
                "schema_version",
                str(left.schema_version),
                str(right.schema_version),
                "version divergence",
            ),
            ("seed", str(left.seed), str(right.seed), "seed divergence"),
            ("tick", str(left.tick), str(right.tick), "time divergence"),
            (
                "inputs",
                canonical_dumps(left.inputs),
                canonical_dumps(right.inputs),
                "input divergence",
            ),
            ("spec_digest", left.spec_digest, right.spec_digest, "spec digest divergence"),
            ("state_digest", left.state_digest, right.state_digest, "state digest divergence"),
            (
                "result_digest",
                left.result_digest,
                right.result_digest,
                "result digest divergence",
            ),
            (
                "steps",
                canonical_dumps([step.to_canonical() for step in left.steps]),
                canonical_dumps([step.to_canonical() for step in right.steps]),
                "step sequence divergence",
            ),
            (
                "step_digests",
                canonical_dumps(list(left.step_digests)),
                canonical_dumps(list(right.step_digests)),
                "step digest divergence",
            ),
        )
        for field, exp, act, reason in checks:
            if exp != act:
                mismatches.append(ReplayMismatch(field, exp, act, reason))
        return ReplayComparison(identical=not mismatches, mismatches=tuple(mismatches))

    def dumps(self, trace: ReplayTrace | Mapping[str, Any] | str | bytes) -> str:
        parsed = parse_trace(trace)
        return canonical_dumps(parsed.to_canonical())

    def loads(self, raw: str | bytes | Mapping[str, Any]) -> ReplayTrace:
        return parse_trace(raw)


def canonical_dumps(value: Any) -> str:
    """Return stable JSON. Non-finite numbers and non-JSON types fail closed."""

    try:
        return json.dumps(
            _canonical_json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise GameReplayError(
            "replay payload is not canonical JSON",
            context={"reason": "non_canonical_json"},
        ) from exc


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_dumps(value).encode("utf-8")).hexdigest()


def parse_trace(value: ReplayTrace | Mapping[str, Any] | str | bytes) -> ReplayTrace:
    if isinstance(value, ReplayTrace):
        payload = value.to_canonical()
    elif isinstance(value, (bytes, bytearray)):
        try:
            decoded = bytes(value).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GameReplayError(
                "malformed replay trace",
                context={"reason": "malformed_trace", "error": "utf8"},
            ) from exc
        payload = _loads_object(decoded)
    elif isinstance(value, str):
        payload = _loads_object(value)
    elif isinstance(value, Mapping):
        payload = dict(value)
        encoded = canonical_dumps(payload).encode("utf-8")
        if len(encoded) > MAX_TRACE_BYTES:
            raise GameReplayError(
                "replay trace exceeds size bound",
                context={"reason": "malformed_trace", "max_bytes": MAX_TRACE_BYTES},
            )
    else:
        raise GameReplayError(
            "malformed replay trace",
            context={"reason": "malformed_trace", "type": type(value).__name__},
        )
    return _trace_from_mapping(payload)


def _loads_object(raw: str) -> dict[str, Any]:
    try:
        encoded = raw.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise GameReplayError(
            "malformed replay trace",
            context={"reason": "malformed_trace", "error": "utf8"},
        ) from exc
    if len(encoded) > MAX_TRACE_BYTES:
        raise GameReplayError(
            "replay trace exceeds size bound",
            context={"reason": "malformed_trace", "max_bytes": MAX_TRACE_BYTES},
        )
    try:
        loaded = json.loads(raw, object_pairs_hook=_json_object_no_duplicates)
    except json.JSONDecodeError as exc:
        raise GameReplayError(
            "malformed replay trace",
            context={"reason": "malformed_trace", "error": "json"},
        ) from exc
    if not isinstance(loaded, dict):
        raise GameReplayError(
            "malformed replay trace",
            context={"reason": "malformed_trace", "error": "root_not_object"},
        )
    return loaded


def _trace_from_mapping(payload: Mapping[str, Any]) -> ReplayTrace:
    if not isinstance(payload, Mapping):
        raise GameReplayError(
            "malformed replay trace",
            context={"reason": "malformed_trace", "error": "root_not_object"},
        )
    unknown = sorted(set(payload) - _TRACE_KEYS)
    if unknown:
        raise GameReplayError(
            "malformed replay trace",
            context={"reason": "malformed_trace", "unknown_keys": unknown},
        )
    missing = sorted(_TRACE_KEYS - set(payload))
    if missing:
        raise GameReplayError(
            "malformed replay trace",
            context={"reason": "malformed_trace", "missing_keys": missing},
        )
    schema = payload["schema"]
    if not isinstance(schema, str) or schema.strip() != schema or not schema:
        raise GameReplayError(
            "malformed replay trace",
            context={"reason": "malformed_trace", "field": "schema"},
        )
    version = _require_int("schema_version", payload["schema_version"], minimum=1)
    if schema != REPLAY_SCHEMA or version != REPLAY_SCHEMA_VERSION:
        raise GameReplayError(
            "incompatible replay schema",
            context={
                "reason": "version_mismatch",
                "expected_schema": REPLAY_SCHEMA,
                "expected_version": REPLAY_SCHEMA_VERSION,
                "actual_schema": schema,
                "actual_version": version,
            },
        )
    seed = _require_int("seed", payload["seed"], minimum=0, maximum=MAX_SEED)
    tick = _require_int("tick", payload["tick"], minimum=0, maximum=MAX_TICK)
    inputs = _parse_inputs(payload["inputs"])
    steps = _parse_steps(payload["steps"])
    spec_digest = _require_digest("spec_digest", payload["spec_digest"])
    state_digest = _require_digest("state_digest", payload["state_digest"])
    result_digest = _require_digest("result_digest", payload["result_digest"])
    step_digests = _parse_digest_list(payload["step_digests"])
    if len(step_digests) != len(steps):
        raise GameReplayError(
            "malformed replay trace",
            context={
                "reason": "malformed_trace",
                "error": "step_digest_count",
                "steps": len(steps),
                "step_digests": len(step_digests),
            },
        )
    return ReplayTrace(
        schema=schema,
        schema_version=version,
        seed=seed,
        tick=tick,
        inputs=inputs,
        steps=steps,
        spec_digest=spec_digest,
        state_digest=state_digest,
        result_digest=result_digest,
        step_digests=step_digests,
    )


def _execute(
    *,
    seed: int,
    tick: int,
    inputs: Mapping[str, Any],
    steps: Sequence[ReplayStep],
) -> ReplayTrace:
    combat_spec = _combat_spec(inputs.get("combat"))
    progression_spec = _progression_spec(inputs.get("progression"))
    economy_spec = _economy_spec(inputs.get("economy"))
    ai_spec = _ai_spec(inputs.get("ai_behavior"))
    generated = _generate_systems(combat_spec, progression_spec, economy_spec, ai_spec)
    spec_digest = canonical_digest(generated)
    state = _initial_state(tick, progression_spec, economy_spec, ai_spec)
    step_digests: list[str] = []
    previous_tick = tick
    for index, step in enumerate(steps):
        if step.at_tick < previous_tick:
            raise GameReplayError(
                "replay time went backwards",
                context={
                    "reason": "time_regression",
                    "index": index,
                    "previous_tick": previous_tick,
                    "at_tick": step.at_tick,
                },
            )
        _advance_clock(state, step.at_tick)
        outcome = _apply_step(
            index=index,
            seed=seed,
            state=state,
            step=step,
            generated=generated,
            combat_spec=combat_spec,
            progression_spec=progression_spec,
            economy_spec=economy_spec,
            ai_spec=ai_spec,
        )
        step_digests.append(
            canonical_digest(
                {
                    "index": index,
                    "step": step.to_canonical(),
                    "outcome": outcome,
                    "state": state,
                }
            )
        )
        previous_tick = step.at_tick
    state_digest = canonical_digest(state)
    normalized_inputs = {key: inputs.get(key) for key in _INPUT_KEYS}
    result_digest = canonical_digest(
        {
            "schema": REPLAY_SCHEMA,
            "schema_version": REPLAY_SCHEMA_VERSION,
            "seed": seed,
            "tick": tick,
            # Bind the normalized source specs directly. Generated mechanics are
            # not guaranteed to be injective: a custom AI behavior can overlap
            # a generated default and be deduplicated without changing
            # spec_digest. Result identity must still distinguish those inputs.
            "inputs": normalized_inputs,
            "spec_digest": spec_digest,
            "state_digest": state_digest,
            "step_digests": step_digests,
        }
    )
    return ReplayTrace(
        schema=REPLAY_SCHEMA,
        schema_version=REPLAY_SCHEMA_VERSION,
        seed=seed,
        tick=tick,
        inputs=normalized_inputs,
        steps=tuple(steps),
        spec_digest=spec_digest,
        state_digest=state_digest,
        result_digest=result_digest,
        step_digests=tuple(step_digests),
    )


def _generate_systems(
    combat_spec: CombatSystemSpec | None,
    progression_spec: ProgressionSystemSpec | None,
    economy_spec: EconomySystemSpec | None,
    ai_spec: AIBehaviorSpec | None,
) -> dict[str, Any]:
    generated: dict[str, Any] = {}
    if combat_spec is not None:
        generated["combat"] = _redact_generated(
            GameMechanicsGenerator.generate_combat_system(combat_spec)
        )
    if progression_spec is not None:
        generated["progression"] = _redact_generated(
            GameMechanicsGenerator.generate_progression_system(progression_spec)
        )
    if economy_spec is not None:
        generated["economy"] = _redact_generated(
            GameMechanicsGenerator.generate_economy_system(economy_spec)
        )
    if ai_spec is not None:
        generated["ai_behavior"] = _redact_generated(
            GameMechanicsGenerator.generate_ai_behavior(ai_spec)
        )
    return generated


def _initial_state(
    tick: int,
    progression_spec: ProgressionSystemSpec | None,
    economy_spec: EconomySystemSpec | None,
    ai_spec: AIBehaviorSpec | None,
) -> dict[str, Any]:
    wallets = {currency: 0 for currency in (economy_spec.currencies if economy_spec else ())}
    return {
        "tick": tick,
        "combatants": {},
        "progression": {
            "level": 1,
            "xp": 0,
            "total_xp": 0,
            "skill_points": 0,
            "level_cap": progression_spec.max_level if progression_spec else 1,
        },
        "wallets": wallets,
        "ai": {
            "entity_type": ai_spec.entity_type if ai_spec else "",
            "state": "idle" if ai_spec is not None else "",
        },
    }


def _advance_clock(state: dict[str, Any], at_tick: int) -> None:
    delta = at_tick - int(state["tick"])
    if delta < 0:
        raise GameReplayError(
            "replay time went backwards",
            context={"reason": "time_regression", "tick": state["tick"], "at_tick": at_tick},
        )
    if delta == 0:
        return
    for name in sorted(state["combatants"]):
        fighter = state["combatants"][name]
        kept: list[dict[str, Any]] = []
        for status in fighter["statuses"]:
            if status["type"] == "dot" and fighter["alive"]:
                damage = _require_int("damage_per_tick", status["damage_per_tick"], minimum=0)
                fighter["hp"] = max(0, int(fighter["hp"]) - damage * delta)
                if fighter["hp"] == 0:
                    fighter["alive"] = False
            remaining = _require_int("remaining", status["remaining"], minimum=0) - delta
            if remaining > 0:
                kept.append(
                    {
                        "name": status["name"],
                        "type": status["type"],
                        "remaining": remaining,
                        "damage_per_tick": int(status["damage_per_tick"]),
                    }
                )
        fighter["statuses"] = kept
    state["tick"] = at_tick


def _apply_step(
    *,
    index: int,
    seed: int,
    state: dict[str, Any],
    step: ReplayStep,
    generated: Mapping[str, Any],
    combat_spec: CombatSystemSpec | None,
    progression_spec: ProgressionSystemSpec | None,
    economy_spec: EconomySystemSpec | None,
    ai_spec: AIBehaviorSpec | None,
) -> dict[str, Any]:
    if step.kind == "combat":
        if combat_spec is None or "combat" not in generated:
            raise GameReplayError(
                "combat system is required for combat steps",
                context={"reason": "missing_system", "index": index, "kind": step.kind},
            )
        return _apply_combat(index, seed, state, step, generated["combat"])
    if step.kind == "progression":
        if progression_spec is None or "progression" not in generated:
            raise GameReplayError(
                "progression system is required for progression steps",
                context={"reason": "missing_system", "index": index, "kind": step.kind},
            )
        return _apply_progression(state, step, generated["progression"])
    if step.kind == "economy":
        if economy_spec is None or "economy" not in generated:
            raise GameReplayError(
                "economy system is required for economy steps",
                context={"reason": "missing_system", "index": index, "kind": step.kind},
            )
        return _apply_economy(state, step, generated["economy"])
    if step.kind == "ai_behavior":
        if ai_spec is None or "ai_behavior" not in generated:
            raise GameReplayError(
                "AI behavior system is required for AI steps",
                context={"reason": "missing_system", "index": index, "kind": step.kind},
            )
        return _apply_ai(state, step, generated["ai_behavior"])
    raise GameReplayError(
        "unknown replay step kind",
        context={"reason": "unknown_kind", "kind": step.kind, "index": index},
    )


def _apply_combat(
    index: int,
    seed: int,
    state: dict[str, Any],
    step: ReplayStep,
    combat: Mapping[str, Any],
) -> dict[str, Any]:
    payload = step.payload
    _expect_payload_keys(payload, required=("actor", "target", "base_damage"), optional=("status",))
    actor = _require_token("actor", payload["actor"])
    target = _require_token("target", payload["target"])
    base_damage = _require_int("base_damage", payload["base_damage"], minimum=1, maximum=MAX_DAMAGE)
    _ensure_combatant(state, actor)
    _ensure_combatant(state, target)
    target_state = state["combatants"][target]
    if not target_state["alive"]:
        return {"hit": False, "damage": 0, "critical": False, "status": None, "target_hp": 0}
    variance = 900 + _bounded_draw(seed, step.at_tick, index, "variance", 201)
    damage = (base_damage * variance) // 1000
    balance = combat.get("balance_parameters", {})
    if not isinstance(balance, Mapping):
        raise GameReplayError(
            "combat balance parameters are malformed",
            context={"reason": "malformed_spec", "system": "combat"},
        )
    crit_rate_mille = _ratio_to_mille(balance.get("crit_rate_base", 0))
    crit_mult_mille = _ratio_to_mille(balance.get("crit_damage_multiplier", 1))
    critical = _bounded_draw(seed, step.at_tick, index, "crit", 1000) < crit_rate_mille
    if critical:
        damage = max(1, (damage * crit_mult_mille) // 1000)
    damage = max(1, damage)
    target_state["hp"] = max(0, int(target_state["hp"]) - damage)
    if target_state["hp"] == 0:
        target_state["alive"] = False
    applied_status = None
    if "status" in payload:
        applied_status = _apply_status(target_state, payload["status"], combat)
    return {
        "hit": True,
        "damage": damage,
        "critical": critical,
        "status": applied_status,
        "target_hp": target_state["hp"],
    }


def _apply_status(fighter: dict[str, Any], name: Any, combat: Mapping[str, Any]) -> str:
    status_name = _require_token("status", name)
    catalog = combat.get("status_effects", [])
    if not isinstance(catalog, list):
        raise GameReplayError(
            "combat status catalog is malformed",
            context={"reason": "malformed_spec", "system": "combat"},
        )
    match = None
    for entry in catalog:
        if isinstance(entry, Mapping) and entry.get("name") == status_name:
            match = entry
            break
    if match is None:
        raise GameReplayError(
            "unknown combat status",
            context={"reason": "unknown_status", "status": status_name},
        )
    duration = _require_int("duration", match.get("duration"), minimum=1, maximum=MAX_TICK)
    status_type = match.get("type")
    if not isinstance(status_type, str) or status_type not in {"dot", "cc"}:
        raise GameReplayError(
            "combat status type is malformed",
            context={"reason": "malformed_spec", "status": status_name},
        )
    damage_per_tick = match.get("damage_per_tick", 0)
    if damage_per_tick is None:
        damage_per_tick = 0
    fighter["statuses"] = [
        status for status in fighter["statuses"] if status["name"] != status_name
    ]
    fighter["statuses"].append(
        {
            "name": status_name,
            "type": status_type,
            "remaining": duration,
            "damage_per_tick": _require_int(
                "damage_per_tick", damage_per_tick, minimum=0, maximum=MAX_DAMAGE
            ),
        }
    )
    return status_name


def _apply_progression(
    state: dict[str, Any],
    step: ReplayStep,
    progression: Mapping[str, Any],
) -> dict[str, Any]:
    payload = step.payload
    _expect_payload_keys(payload, required=("amount",), optional=())
    amount = _require_int("amount", payload["amount"], minimum=0, maximum=MAX_XP)
    table = progression.get("xp_table")
    if not isinstance(table, list) or not table:
        raise GameReplayError(
            "progression xp table is malformed",
            context={"reason": "malformed_spec", "system": "progression"},
        )
    growth = progression.get("stat_growth", {})
    if not isinstance(growth, Mapping):
        raise GameReplayError(
            "progression stat growth is malformed",
            context={"reason": "malformed_spec", "system": "progression"},
        )
    points_per_level = _require_int(
        "skill_points_per_level",
        growth.get("skill_points_per_level", 1),
        minimum=0,
        maximum=100,
    )
    level_cap = _require_int("level_cap", progression.get("level_cap"), minimum=1, maximum=1_000)
    progress = state["progression"]
    progress["total_xp"] = int(progress["total_xp"]) + amount
    progress["xp"] = int(progress["xp"]) + amount
    leveled = 0
    while int(progress["level"]) < level_cap:
        row = table[int(progress["level"]) - 1]
        if not isinstance(row, Mapping):
            raise GameReplayError(
                "progression xp row is malformed",
                context={"reason": "malformed_spec", "level": progress["level"]},
            )
        threshold = _require_int("total_xp", row.get("total_xp"), minimum=0)
        if int(progress["total_xp"]) < threshold:
            break
        progress["level"] = int(progress["level"]) + 1
        progress["skill_points"] = int(progress["skill_points"]) + points_per_level
        leveled += 1
    return {
        "amount": amount,
        "level": progress["level"],
        "total_xp": progress["total_xp"],
        "skill_points": progress["skill_points"],
        "levels_gained": leveled,
    }


def _apply_economy(
    state: dict[str, Any],
    step: ReplayStep,
    economy: Mapping[str, Any],
) -> dict[str, Any]:
    payload = step.payload
    _expect_payload_keys(payload, required=("currency", "delta"), optional=())
    currency = _require_token("currency", payload["currency"])
    delta = _require_int("delta", payload["delta"], minimum=-MAX_DELTA, maximum=MAX_DELTA)
    if currency not in state["wallets"]:
        raise GameReplayError(
            "unknown currency",
            context={"reason": "unknown_currency", "currency": currency},
        )
    catalog = economy.get("currencies")
    if not isinstance(catalog, Mapping) or currency not in catalog:
        raise GameReplayError(
            "economy currency catalog is malformed",
            context={"reason": "malformed_spec", "currency": currency},
        )
    spec = catalog[currency]
    if not isinstance(spec, Mapping):
        raise GameReplayError(
            "economy currency catalog is malformed",
            context={"reason": "malformed_spec", "currency": currency},
        )
    cap = _require_int("cap", spec.get("cap"), minimum=0)
    next_value = int(state["wallets"][currency]) + delta
    if next_value < 0:
        raise GameReplayError(
            "insufficient currency",
            context={
                "reason": "insufficient_currency",
                "currency": currency,
                "balance": state["wallets"][currency],
                "delta": delta,
            },
        )
    next_value = min(next_value, cap)
    state["wallets"][currency] = next_value
    return {"currency": currency, "delta": delta, "balance": next_value}


def _apply_ai(
    state: dict[str, Any],
    step: ReplayStep,
    ai_behavior: Mapping[str, Any],
) -> dict[str, Any]:
    payload = step.payload
    _expect_payload_keys(payload, required=("to",), optional=())
    destination = _require_token("to", payload["to"])
    states = ai_behavior.get("states")
    if not isinstance(states, Mapping):
        raise GameReplayError(
            "AI state machine is malformed",
            context={"reason": "malformed_spec", "system": "ai_behavior"},
        )
    current = state["ai"]["state"]
    node = states.get(current)
    if not isinstance(node, Mapping):
        raise GameReplayError(
            "AI current state is malformed",
            context={"reason": "malformed_spec", "state": current},
        )
    transitions = node.get("transitions")
    if not isinstance(transitions, list) or not all(isinstance(item, str) for item in transitions):
        raise GameReplayError(
            "AI transitions are malformed",
            context={"reason": "malformed_spec", "state": current},
        )
    if destination not in transitions:
        raise GameReplayError(
            "illegal AI-behavior transition",
            context={
                "reason": "illegal_transition",
                "from": current,
                "to": destination,
                "legal": list(transitions),
            },
        )
    state["ai"]["state"] = destination
    return {"from": current, "to": destination}


def _ensure_combatant(state: dict[str, Any], name: str) -> None:
    combatants = state["combatants"]
    if name in combatants:
        return
    combatants[name] = {
        "hp": STARTING_HP,
        "max_hp": STARTING_HP,
        "alive": True,
        "statuses": [],
    }


def _parse_steps(steps: Any) -> tuple[ReplayStep, ...]:
    if not isinstance(steps, (list, tuple)):
        raise GameReplayError(
            "replay steps must be a list",
            context={"reason": "malformed_trace", "field": "steps"},
        )
    if len(steps) > MAX_STEPS:
        raise GameReplayError(
            "too many replay steps",
            context={"reason": "malformed_trace", "maximum": MAX_STEPS, "actual": len(steps)},
        )
    parsed: list[ReplayStep] = []
    for index, raw in enumerate(steps):
        if isinstance(raw, ReplayStep):
            raw = raw.to_canonical()
        if not isinstance(raw, Mapping):
            raise GameReplayError(
                "malformed replay step",
                context={"reason": "malformed_trace", "index": index},
            )
        unknown = sorted(set(raw) - _STEP_KEYS)
        if unknown:
            raise GameReplayError(
                "malformed replay step",
                context={"reason": "malformed_trace", "index": index, "unknown_keys": unknown},
            )
        missing = sorted(_STEP_KEYS - set(raw))
        if missing:
            raise GameReplayError(
                "malformed replay step",
                context={"reason": "malformed_trace", "index": index, "missing_keys": missing},
            )
        kind = raw["kind"]
        action = raw["action"]
        if not isinstance(kind, str) or kind not in STEP_KINDS:
            raise GameReplayError(
                "unknown replay step kind",
                context={"reason": "unknown_kind", "index": index, "kind": kind},
            )
        if not isinstance(action, str) or action not in STEP_ACTIONS[kind]:
            raise GameReplayError(
                "unknown replay step action",
                context={
                    "reason": "unknown_action",
                    "index": index,
                    "kind": kind,
                    "action": action,
                },
            )
        at_tick = _require_int("at_tick", raw["at_tick"], minimum=0, maximum=MAX_TICK)
        payload = raw["payload"]
        if not isinstance(payload, Mapping):
            raise GameReplayError(
                "replay step payload must be an object",
                context={"reason": "malformed_trace", "index": index},
            )
        if len(payload) > MAX_PAYLOAD_KEYS:
            raise GameReplayError(
                "replay step payload is too large",
                context={"reason": "malformed_trace", "index": index, "maximum": MAX_PAYLOAD_KEYS},
            )
        canonical_payload = _canonical_payload(payload)
        parsed.append(
            ReplayStep(kind=kind, action=action, at_tick=at_tick, payload=canonical_payload)
        )
    return tuple(parsed)


def _parse_inputs(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise GameReplayError(
            "malformed replay inputs",
            context={"reason": "malformed_trace", "field": "inputs"},
        )
    unknown = sorted(set(raw) - set(_INPUT_KEYS))
    if unknown:
        raise GameReplayError(
            "malformed replay inputs",
            context={"reason": "malformed_trace", "unknown_keys": unknown},
        )
    missing = [key for key in _INPUT_KEYS if key not in raw]
    if missing:
        raise GameReplayError(
            "malformed replay inputs",
            context={"reason": "malformed_trace", "missing_keys": missing},
        )
    return {
        "combat": _combat_input(raw["combat"]),
        "progression": _progression_input(raw["progression"]),
        "economy": _economy_input(raw["economy"]),
        "ai_behavior": _ai_input(raw["ai_behavior"]),
    }


def _combat_input(value: CombatSystemSpec | Mapping[str, Any] | None) -> dict[str, Any] | None:
    spec = _combat_spec(value)
    if spec is None:
        return None
    return {
        "style": spec.style.value,
        "include_magic": spec.include_magic,
        "include_status_effects": spec.include_status_effects,
        "party_based": spec.party_based,
        "enemy_ai_complexity": spec.enemy_ai_complexity,
    }


def _progression_input(
    value: ProgressionSystemSpec | Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    spec = _progression_spec(value)
    if spec is None:
        return None
    return {
        "style": spec.style.value,
        "max_level": spec.max_level,
        "include_prestige": spec.include_prestige,
        "skill_tree_branches": spec.skill_tree_branches,
    }


def _economy_input(value: EconomySystemSpec | Mapping[str, Any] | None) -> dict[str, Any] | None:
    spec = _economy_spec(value)
    if spec is None:
        return None
    return {
        "currencies": list(spec.currencies),
        "include_trading": spec.include_trading,
        "include_crafting": spec.include_crafting,
        "inflation_model": spec.inflation_model,
    }


def _ai_input(value: AIBehaviorSpec | Mapping[str, Any] | None) -> dict[str, Any] | None:
    spec = _ai_spec(value)
    if spec is None:
        return None
    return {
        "entity_type": spec.entity_type,
        "behaviors": list(spec.behaviors),
        "aggression_level": spec.aggression_level,
        "intelligence_level": spec.intelligence_level,
    }


def _combat_spec(value: CombatSystemSpec | Mapping[str, Any] | None) -> CombatSystemSpec | None:
    if value is None:
        return None
    if isinstance(value, CombatSystemSpec):
        return value
    if not isinstance(value, Mapping):
        raise GameReplayError(
            "combat input is malformed",
            context={"reason": "malformed_trace", "field": "combat"},
        )
    _expect_spec_keys(
        value,
        field="combat",
        required=("style",),
        optional=("include_magic", "include_status_effects", "party_based", "enemy_ai_complexity"),
    )
    try:
        return CombatSystemSpec(
            style=value["style"],
            include_magic=_require_bool("include_magic", value.get("include_magic", True)),
            include_status_effects=_require_bool(
                "include_status_effects", value.get("include_status_effects", True)
            ),
            party_based=_require_bool("party_based", value.get("party_based", False)),
            enemy_ai_complexity=value.get("enemy_ai_complexity", "moderate"),
        )
    except (GameMechanicsError, KeyError, TypeError, ValueError) as exc:
        raise GameReplayError(
            "combat input is malformed",
            context={"reason": "malformed_trace", "field": "combat"},
        ) from exc


def _progression_spec(
    value: ProgressionSystemSpec | Mapping[str, Any] | None,
) -> ProgressionSystemSpec | None:
    if value is None:
        return None
    if isinstance(value, ProgressionSystemSpec):
        return value
    if not isinstance(value, Mapping):
        raise GameReplayError(
            "progression input is malformed",
            context={"reason": "malformed_trace", "field": "progression"},
        )
    _expect_spec_keys(
        value,
        field="progression",
        required=("style",),
        optional=("max_level", "include_prestige", "skill_tree_branches"),
    )
    try:
        return ProgressionSystemSpec(
            style=value["style"],
            max_level=value.get("max_level", 100),
            include_prestige=_require_bool(
                "include_prestige", value.get("include_prestige", False)
            ),
            skill_tree_branches=value.get("skill_tree_branches", 3),
        )
    except (GameMechanicsError, KeyError, TypeError, ValueError) as exc:
        raise GameReplayError(
            "progression input is malformed",
            context={"reason": "malformed_trace", "field": "progression"},
        ) from exc


def _economy_spec(value: EconomySystemSpec | Mapping[str, Any] | None) -> EconomySystemSpec | None:
    if value is None:
        return None
    if isinstance(value, EconomySystemSpec):
        return value
    if not isinstance(value, Mapping):
        raise GameReplayError(
            "economy input is malformed",
            context={"reason": "malformed_trace", "field": "economy"},
        )
    _expect_spec_keys(
        value,
        field="economy",
        required=(),
        optional=("currencies", "include_trading", "include_crafting", "inflation_model"),
    )
    currencies = value.get("currencies", ("gold",))
    if not isinstance(currencies, (list, tuple)):
        raise GameReplayError(
            "economy input is malformed",
            context={"reason": "malformed_trace", "field": "currencies"},
        )
    currencies = tuple(currencies)
    try:
        return EconomySystemSpec(
            currencies=currencies,
            include_trading=_require_bool("include_trading", value.get("include_trading", True)),
            include_crafting=_require_bool(
                "include_crafting", value.get("include_crafting", False)
            ),
            inflation_model=_require_bool("inflation_model", value.get("inflation_model", False)),
        )
    except (GameMechanicsError, KeyError, TypeError, ValueError) as exc:
        raise GameReplayError(
            "economy input is malformed",
            context={"reason": "malformed_trace", "field": "economy"},
        ) from exc


def _ai_spec(value: AIBehaviorSpec | Mapping[str, Any] | None) -> AIBehaviorSpec | None:
    if value is None:
        return None
    if isinstance(value, AIBehaviorSpec):
        return value
    if not isinstance(value, Mapping):
        raise GameReplayError(
            "AI behavior input is malformed",
            context={"reason": "malformed_trace", "field": "ai_behavior"},
        )
    _expect_spec_keys(
        value,
        field="ai_behavior",
        required=("entity_type",),
        optional=("behaviors", "aggression_level", "intelligence_level"),
    )
    behaviors = value.get("behaviors", ())
    if not isinstance(behaviors, (list, tuple)):
        raise GameReplayError(
            "AI behavior input is malformed",
            context={"reason": "malformed_trace", "field": "behaviors"},
        )
    behaviors = tuple(behaviors)
    try:
        return AIBehaviorSpec(
            entity_type=value["entity_type"],
            behaviors=behaviors,
            aggression_level=value.get("aggression_level", 0.5),
            intelligence_level=value.get("intelligence_level", 0.5),
        )
    except (GameMechanicsError, KeyError, TypeError, ValueError) as exc:
        raise GameReplayError(
            "AI behavior input is malformed",
            context={"reason": "malformed_trace", "field": "ai_behavior"},
        ) from exc


def _canonical_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    canonical: dict[str, Any] = {}
    for key, value in payload.items():
        token = _require_token("payload_key", key)
        if isinstance(value, bool) or value is None:
            raise GameReplayError(
                "replay payload values must be strings or integers",
                context={"reason": "malformed_trace", "key": token},
            )
        if isinstance(value, str):
            canonical[token] = _require_token(token, value)
            continue
        if isinstance(value, int):
            canonical[token] = value
            continue
        raise GameReplayError(
            "replay payload values must be strings or integers",
            context={"reason": "malformed_trace", "key": token, "type": type(value).__name__},
        )
    return canonical


def _canonical_json_value(value: Any, *, depth: int = 0) -> Any:
    if depth > MAX_CANONICAL_DEPTH:
        raise GameReplayError(
            "replay payload is not canonical JSON",
            context={"reason": "non_canonical_json", "error": "nesting"},
        )
    if value is None:
        return value
    if isinstance(value, str):
        if len(value) > MAX_TRACE_BYTES:
            raise GameReplayError(
                "replay payload is not canonical JSON",
                context={"reason": "non_canonical_json", "error": "string_bound"},
            )
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GameReplayError(
                "replay payload is not canonical JSON",
                context={"reason": "non_canonical_json", "error": "non_finite"},
            )
        return value
    if isinstance(value, Mapping):
        if len(value) > MAX_CANONICAL_ITEMS:
            raise GameReplayError(
                "replay payload is not canonical JSON",
                context={"reason": "non_canonical_json", "error": "object_bound"},
            )
        canonical: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise GameReplayError(
                    "replay payload is not canonical JSON",
                    context={"reason": "non_canonical_json", "error": "non_string_key"},
                )
            if key in canonical:
                raise GameReplayError(
                    "replay payload is not canonical JSON",
                    context={"reason": "non_canonical_json", "error": "duplicate_key"},
                )
            canonical[key] = _canonical_json_value(item, depth=depth + 1)
        return canonical
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_CANONICAL_ITEMS:
            raise GameReplayError(
                "replay payload is not canonical JSON",
                context={"reason": "non_canonical_json", "error": "list_bound"},
            )
        return [_canonical_json_value(item, depth=depth + 1) for item in value]
    raise GameReplayError(
        "replay payload is not canonical JSON",
        context={"reason": "non_canonical_json", "type": type(value).__name__},
    )


def _redact_generated(value: Any, *, depth: int = 0) -> Any:
    if depth > MAX_CANONICAL_DEPTH:
        raise GameReplayError(
            "generated mechanics are not canonical JSON",
            context={"reason": "non_canonical_json", "error": "nesting"},
        )
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key == "id" and isinstance(item, str) and _UUID_RE.fullmatch(item):
                continue
            if not isinstance(key, str):
                raise GameReplayError(
                    "generated mechanics are not canonical JSON",
                    context={"reason": "non_canonical_json", "error": "non_string_key"},
                )
            redacted[key] = _redact_generated(item, depth=depth + 1)
        return redacted
    if isinstance(value, list):
        return [_redact_generated(item, depth=depth + 1) for item in value]
    if isinstance(value, tuple):
        return [_redact_generated(item, depth=depth + 1) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise GameReplayError(
            "generated mechanics are not canonical JSON",
            context={"reason": "non_canonical_json", "error": "non_finite"},
        )
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return value
    raise GameReplayError(
        "generated mechanics are not canonical JSON",
        context={"reason": "non_canonical_json", "type": type(value).__name__},
    )


def _bounded_draw(seed: int, at_tick: int, index: int, lane: str, modulus: int) -> int:
    if modulus <= 0:
        raise GameReplayError(
            "invalid entropy modulus",
            context={"reason": "malformed_trace", "modulus": modulus},
        )
    material = canonical_dumps(
        {
            "schema": REPLAY_SCHEMA,
            "schema_version": REPLAY_SCHEMA_VERSION,
            "seed": seed,
            "at_tick": at_tick,
            "index": index,
            "lane": lane,
            "modulus": modulus,
        }
    ).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return int.from_bytes(digest[:8], "big") % modulus


def _ratio_to_mille(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GameReplayError(
            "ratio must be numeric",
            context={"reason": "malformed_spec"},
        )
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise GameReplayError(
            "ratio must be a finite non-negative number",
            context={"reason": "malformed_spec"},
        )
    return round(number * 1000)


def _json_object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GameReplayError(
                "malformed replay trace",
                context={"reason": "malformed_trace", "error": "duplicate_key", "key": key},
            )
        result[key] = value
    return result


def _expect_spec_keys(
    value: Mapping[str, Any],
    *,
    field: str,
    required: tuple[str, ...],
    optional: tuple[str, ...],
) -> None:
    allowed = set(required) | set(optional)
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise GameReplayError(
            f"{field} input is malformed",
            context={"reason": "malformed_trace", "field": field, "unknown_keys": unknown},
        )
    missing = [key for key in required if key not in value]
    if missing:
        raise GameReplayError(
            f"{field} input is malformed",
            context={"reason": "malformed_trace", "field": field, "missing_keys": missing},
        )


def _expect_payload_keys(
    payload: Mapping[str, Any],
    *,
    required: tuple[str, ...],
    optional: tuple[str, ...],
) -> None:
    allowed = set(required) | set(optional)
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise GameReplayError(
            "unexpected replay payload keys",
            context={"reason": "malformed_trace", "unknown_keys": unknown},
        )
    missing = [key for key in required if key not in payload]
    if missing:
        raise GameReplayError(
            "missing replay payload keys",
            context={"reason": "malformed_trace", "missing_keys": missing},
        )


def _require_int(name: str, value: Any, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GameReplayError(
            f"{name} must be an integer",
            context={"reason": "malformed_trace", "field": name},
        )
    if minimum is not None and value < minimum:
        raise GameReplayError(
            f"{name} is out of bounds",
            context={"reason": "malformed_trace", "field": name, "minimum": minimum},
        )
    if maximum is not None and value > maximum:
        raise GameReplayError(
            f"{name} is out of bounds",
            context={"reason": "malformed_trace", "field": name, "maximum": maximum},
        )
    return value


def _require_bool(name: str, value: Any) -> bool:
    if value is not True and value is not False:
        raise GameReplayError(
            f"{name} must be a boolean",
            context={"reason": "malformed_trace", "field": name},
        )
    return value


def _require_token(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise GameReplayError(
            f"{name} must be a non-empty string",
            context={"reason": "malformed_trace", "field": name},
        )
    if any(ord(char) < 32 for char in value):
        raise GameReplayError(
            f"{name} contains control characters",
            context={"reason": "malformed_trace", "field": name},
        )
    if len(value) > MAX_TOKEN_CHARS:
        raise GameReplayError(
            f"{name} is too long",
            context={"reason": "malformed_trace", "field": name, "max_chars": MAX_TOKEN_CHARS},
        )
    return value


def _require_digest(name: str, value: Any) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise GameReplayError(
            f"{name} must be a 64-character lowercase hex digest",
            context={"reason": "malformed_trace", "field": name},
        )
    return value


def _parse_digest_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GameReplayError(
            "step_digests must be a list",
            context={"reason": "malformed_trace", "field": "step_digests"},
        )
    if len(value) > MAX_STEPS:
        raise GameReplayError(
            "step_digests exceeds replay step bound",
            context={"reason": "malformed_trace", "maximum": MAX_STEPS},
        )
    return tuple(_require_digest("step_digest", item) for item in value)
