"""Offline source-bound, turn-based combat sessions.

A playable two-sided encounter using the canonical FLGB event/save contracts and
Combat Design's deterministic damage and readable-telegraph owners. No network,
provider, hidden entropy, executable authored content or asset downloads.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    EventBus, SaveableGameplayState, dig, req_id,
)
from skeleton.simulation.game.combat_design.damage import (
    DamageEvent, DamageType, DefenderProfile, resolve_damage,
)
from skeleton.simulation.game.combat_design.telegraph import (
    AttackTelegraph, TelegraphChannel, ThreatTier, audit_telegraph,
)

SCHEMA = "skeleton.game.combat_session.v1"
SAVE_SCHEMA = "skeleton.game.combat_save.v1"
MAX_TURNS = 128
MAX_ATTACKS = 16
MAX_HP = 100_000
MAX_STAMINA = 1000


class CombatSessionError(ValueError):
    """Untrusted combat source, command, or save rejected without side effects."""


def _integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise CombatSessionError(f"{name} must be an integer in [{low}, {high}]")
    return value


def _object(value: Any, fields: set[str], required: set[str], name: str) -> dict:
    if not isinstance(value, dict) or set(value) - fields or not required <= set(value):
        raise CombatSessionError(f"invalid {name} fields")
    return value


def _identifier(value: Any, name: str) -> str:
    try:
        return req_id(value, name)
    except ValueError as exc:
        raise CombatSessionError(f"invalid {name}") from exc


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise CombatSessionError("combat source is not canonical JSON") from exc


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode("ascii")).hexdigest()


def _attack(raw: Any, player_hp: int, hostile: bool) -> dict:
    fields = {"id", "power", "stamina_cost", "damage_type", "tier", "windup_ms",
              "active_ms", "recovery_ms", "channels", "crit_percent"}
    a = _object(raw, fields, fields - {"crit_percent"}, "attack")
    _identifier(a["id"], "attack id")
    _integer(a["power"], "power", 1, 10_000)
    _integer(a["stamina_cost"], "stamina cost", 0, MAX_STAMINA)
    _integer(a.get("crit_percent", 0), "crit percent", 0, 50)
    try:
        dtype = DamageType(a["damage_type"])
        tier = ThreatTier(a["tier"])
        if type(a["channels"]) is not list or len(a["channels"]) > 5:
            raise ValueError("channels")
        channels = frozenset(TelegraphChannel(c) for c in a["channels"])
        if len(channels) != len(a["channels"]):
            raise ValueError("duplicate channel")
        telegraph = AttackTelegraph(
            name=a["id"], tier=tier,
            windup_ms=_integer(a["windup_ms"], "windup", 0, 10_000),
            active_ms=_integer(a["active_ms"], "active", 1, 10_000),
            recovery_ms=_integer(a["recovery_ms"], "recovery", 0, 10_000),
            channels=channels, damage_fraction=a["power"] / player_hp if hostile else 0.0,
        )
        failures = audit_telegraph(telegraph) if hostile else []
        if failures:
            raise CombatSessionError("unreadable attack: " + ",".join(v.code for v in failures))
    except (ValueError, TypeError, KeyError) as exc:
        raise CombatSessionError("invalid attack telegraph or damage type") from exc
    return dict(a)


def validate_source(source: Any) -> dict:
    """Freeze the complete authored encounter; reject unknown authority fields."""
    s = _object(source, {"schema", "world_id", "encounter_id", "player", "enemy", "attacks",
                         "reward_item"}, {"schema", "world_id", "encounter_id", "player",
                                         "enemy", "attacks"}, "source")
    if s["schema"] != SCHEMA:
        raise CombatSessionError("unsupported combat source version")
    _identifier(s["world_id"], "world_id")
    _identifier(s["encounter_id"], "encounter_id")
    if "reward_item" in s:
        _identifier(s["reward_item"], "reward_item")
    actors = {}
    for role in ("player", "enemy"):
        a = _object(s[role], {"id", "hp", "stamina", "armor", "level", "attack_ids",
                              "healing_items"}, {"id", "hp", "stamina", "armor", "level",
                                                 "attack_ids"}, role)
        _identifier(a["id"], "actor id")
        _integer(a["hp"], "hp", 1, MAX_HP)
        _integer(a["stamina"], "stamina", 1, MAX_STAMINA)
        _integer(a["armor"], "armor", 0, 100_000)
        _integer(a["level"], "level", 1, 100)
        _integer(a.get("healing_items", 0), "healing_items", 0, 20)
        if not isinstance(a["attack_ids"], list) or not 1 <= len(a["attack_ids"]) <= MAX_ATTACKS:
            raise CombatSessionError("attack_ids must be a bounded list")
        for name in a["attack_ids"]:
            _identifier(name, "attack_id")
        if len(set(a["attack_ids"])) != len(a["attack_ids"]):
            raise CombatSessionError("duplicate actor attack")
        actors[role] = a
    if actors["player"]["id"] == actors["enemy"]["id"]:
        raise CombatSessionError("combatants require distinct ids")
    if not isinstance(s["attacks"], list) or not 1 <= len(s["attacks"]) <= MAX_ATTACKS:
        raise CombatSessionError("attacks must be a bounded list")
    attacks = [_attack(a, actors["player"]["hp"],
                       isinstance(a, dict) and a.get("id") in actors["enemy"]["attack_ids"])
               for a in s["attacks"]]
    ids = [a["id"] for a in attacks]
    if len(set(ids)) != len(ids):
        raise CombatSessionError("duplicate attack id")
    for actor in actors.values():
        if not set(actor["attack_ids"]) <= set(ids):
            raise CombatSessionError("actor references missing attack")
    try:
        frozen = json.loads(_canonical(s))
    except (ValueError, TypeError) as exc:
        raise CombatSessionError("combat source is not JSON") from exc
    if len(_canonical(frozen)) > 48 * 1024:
        raise CombatSessionError("combat source exceeds 48KiB")
    return frozen


def _roll(source_digest: str, turn: int, actor: str, attack: str) -> float:
    data = f"{source_digest}:{turn}:{actor}:{attack}".encode("utf-8")
    return (int.from_bytes(sha256(data).digest()[:7], "big") >> 3) / (1 << 53)


def _initial(source: dict) -> dict:
    return {
        "turn": 0,
        "phase": "active",
        "player": {"hp": source["player"]["hp"], "stamina": source["player"]["stamina"],
                   "healing_items": source["player"].get("healing_items", 0), "guard": False},
        "enemy": {"hp": source["enemy"]["hp"], "stamina": source["enemy"]["stamina"],
                  "healing_items": 0, "guard": False},
        "reward": None,
    }


def _strike(source: dict, state: dict, side: str, attack_id: str, source_digest: str) -> dict:
    actor = source[side]
    opponent = "enemy" if side == "player" else "player"
    if attack_id not in actor["attack_ids"]:
        raise CombatSessionError("actor cannot use this attack")
    attack = next(a for a in source["attacks"] if a["id"] == attack_id)
    stamina = state[side]["stamina"]
    if stamina < attack["stamina_cost"]:
        raise CombatSessionError("insufficient stamina")
    state[side]["stamina"] -= attack["stamina_cost"]
    event = DamageEvent(
        base=attack["power"], dtype=DamageType(attack["damage_type"]),
        attacker_level=actor["level"], crit_chance=attack.get("crit_percent", 0) / 100,
    )
    defender = DefenderProfile(armor=source[opponent]["armor"])
    result = resolve_damage(event, defender,
                            crit_roll=_roll(source_digest, state["turn"], side, attack_id),
                            variance_roll=0.5)
    amount = result.final // 2 if state[opponent]["guard"] else result.final
    state[opponent]["guard"] = False
    state[opponent]["hp"] = max(0, state[opponent]["hp"] - amount)
    return {"actor": side, "action": "attack", "attack_id": attack_id,
            "damage": amount, "crit": result.crit, "target_hp": state[opponent]["hp"]}


def _act(source: dict, state: dict, side: str, command: dict, digest: str) -> dict:
    c = _object(command, {"action", "attack_id"}, {"action"}, "command")
    if c["action"] == "attack":
        if set(c) != {"action", "attack_id"}:
            raise CombatSessionError("attack requires attack_id only")
        return _strike(source, state, side, _identifier(c["attack_id"], "attack_id"), digest)
    if set(c) != {"action"}:
        raise CombatSessionError("unexpected command argument")
    if c["action"] == "guard":
        state[side]["guard"] = True
        return {"actor": side, "action": "guard"}
    if c["action"] == "rest":
        cap = source[side]["stamina"]
        state[side]["stamina"] = min(cap, state[side]["stamina"] + max(1, cap // 3))
        return {"actor": side, "action": "rest", "stamina": state[side]["stamina"]}
    if c["action"] == "heal" and side == "player":
        if state[side]["healing_items"] == 0:
            raise CombatSessionError("no healing items remain")
        state[side]["healing_items"] -= 1
        state[side]["hp"] = min(source[side]["hp"], state[side]["hp"] + max(1, source[side]["hp"] // 4))
        return {"actor": side, "action": "heal", "hp": state[side]["hp"]}
    raise CombatSessionError("unsupported combat command")


def _enemy_command(source: dict, state: dict) -> dict:
    attacks = {a["id"]: a for a in source["attacks"]}
    available = [a for a in source["enemy"]["attack_ids"]
                 if attacks[a]["stamina_cost"] <= state["enemy"]["stamina"]]
    if available:
        # The authored order is the deterministic enemy priority, not an RNG.
        return {"action": "attack", "attack_id": available[state["turn"] % len(available)]}
    return {"action": "rest"}


def replay(source: Mapping[str, Any], commands: Sequence[Mapping[str, Any]]) -> dict:
    """Rebuild authoritative state from the immutable source and player actions."""
    s = validate_source(dict(source))
    if not isinstance(commands, (list, tuple)) or len(commands) > MAX_TURNS:
        raise CombatSessionError("combat turn budget exceeded")
    source_digest = _digest(s)
    state = _initial(s)
    bus = EventBus()
    trace: list[dict] = []
    for index, command in enumerate(commands):
        if state["phase"] != "active":
            raise CombatSessionError("cannot act after terminal combat")
        if not isinstance(command, dict):
            raise CombatSessionError("command must be a JSON object")
        state["turn"] = index + 1
        record = _act(s, state, "player", command, source_digest)
        bus = bus.publish("combat.player", s["player"]["id"], _digest(record))
        trace.append(record)
        if state["enemy"]["hp"] > 0:
            response = _act(s, state, "enemy", _enemy_command(s, state), source_digest)
            bus = bus.publish("combat.enemy", s["enemy"]["id"], _digest(response))
            trace.append(response)
        if state["enemy"]["hp"] == 0:
            state["phase"] = "victory"
            state["reward"] = s.get("reward_item")
        elif state["player"]["hp"] == 0:
            state["phase"] = "defeat"
        if state["phase"] != "active":
            terminal = {"phase": state["phase"], "turn": state["turn"]}
            bus = bus.publish("combat.terminal", s["encounter_id"], _digest(terminal))
    if state["phase"] == "active" and len(commands) == MAX_TURNS:
        state["phase"] = "turn_limit"
    canon = dig({"world_id": s["world_id"], "encounter_id": s["encounter_id"],
                 "source_digest": source_digest})
    save = SaveableGameplayState(
        world_id=s["world_id"], schema_version=1, tick=state["turn"],
        state_digest=_digest(state), canon_digest=canon,
    )
    return {"schema": SAVE_SCHEMA, "source_digest": source_digest,
            "commands": deepcopy(list(commands)), "state": state, "trace": trace,
            "state_digest": _digest(state), "event_digest": bus.digest,
            "save_metadata_digest": save.digest, "terminal": state["phase"] != "active"}


def verify_save(source: Mapping[str, Any], saved: Any) -> dict:
    """Verify every claimed state/trace/event byte by recomputing from source."""
    data = _object(saved, {"schema", "source_digest", "commands", "state", "trace",
                           "state_digest", "event_digest", "save_metadata_digest", "terminal"},
                   {"schema", "source_digest", "commands", "state", "trace",
                    "state_digest", "event_digest", "save_metadata_digest", "terminal"}, "save")
    if data["schema"] != SAVE_SCHEMA:
        raise CombatSessionError("unsupported combat save version")
    expected = replay(source, data["commands"])
    if _canonical(data) != _canonical(expected):
        raise CombatSessionError("combat save does not match deterministic source replay")
    return expected


def advance(source: Mapping[str, Any], saved: Any, command: Mapping[str, Any]) -> dict:
    prior = replay(source, []) if saved is None else verify_save(source, saved)
    if prior["terminal"]:
        raise CombatSessionError("combat is terminal")
    return replay(source, [*prior["commands"], dict(command)])
