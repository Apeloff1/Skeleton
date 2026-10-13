"""Executable four-realm crossover campaign with persistent independent worlds.

The four rule-adapted original worlds can be visited in one game, and
player-carried resources cross realms *without duplication*. Each realm keeps
its own discovered rooms, promises, settlements, climate and postgame state.
No copyrighted franchise data, binaries or external model are used.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_world_campaign import (
    SCENARIOS, CampaignAction, CampaignError, CampaignState,
    create_campaign, import_save, export_save, step, validate_state,
)

NEXUS_SCHEMA = "original-four-world-nexus.v1"
REALM_IDS = ("serenity-05", "topology-02", "ecology-03", "civilization-01")
_PORTABLE = (
    "health", "energy", "hunger", "wood", "stone", "food", "water",
    "seeds", "tools", "medicine", "coins", "courage",
)
MAX_NEXUS_EVENTS = 1024


@dataclass(frozen=True)
class NexusState:
    seed: str
    current_realm: int
    realms: tuple[CampaignState, ...]
    charges: int
    completed_realms: tuple[int, ...]
    archive: tuple[str, ...]
    event_count: int = 0
    event_head: str = "0" * 64


@dataclass(frozen=True)
class NexusReceipt:
    action_type: str
    from_realm: int
    to_realm: int
    event_count: int
    event_id: str
    world_receipt: str
    messages: tuple[str, ...]


def _digest(data: object) -> str:
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _portable(state: CampaignState) -> dict[str, int]:
    return {key: getattr(state, key) for key in _PORTABLE}


def _park(state: CampaignState) -> CampaignState:
    # World-local trust, knowledge, promises, crops, pollution, and chapters
    # stay in their own world. Only tangible carried resources leave.
    return replace(state, **{key: 0 for key in _PORTABLE})


def _arrive(destination: CampaignState, traveler: CampaignState) -> CampaignState:
    return replace(destination, **_portable(traveler))


def _record(state: NexusState, updated: NexusState, kind: str,
            source: int, dest: int, world_receipt: str,
            messages: tuple[str, ...]) -> tuple[NexusState, NexusReceipt]:
    digest = _digest({
        "schema": NEXUS_SCHEMA,
        "before": state.event_head,
        "current_before": _digest(asdict(state)),
        "new_state": asdict(updated), "kind": kind,
        "source": source, "target": dest,
        "underlying_world_event": world_receipt,
    })
    next_state = replace(updated, event_count=state.event_count + 1,
                         event_head=digest)
    validate_nexus(next_state)
    return next_state, NexusReceipt(
        kind, source, dest, next_state.event_count,
        digest, world_receipt, messages,
    )


def validate_nexus(state: NexusState) -> None:
    if not isinstance(state, NexusState):
        raise CampaignError("not a nexus state")
    if not isinstance(state.seed, str) or not 0 < len(state.seed.encode("utf-8")) <= 1024:
        raise CampaignError("invalid nexus seed")
    if type(state.current_realm) is not int or not 0 <= state.current_realm < 4:
        raise CampaignError("invalid active realm")
    if not isinstance(state.realms, tuple) or len(state.realms) != 4:
        raise CampaignError("invalid realm inventory")
    if any(realm.world_id != REALM_IDS[i] or
           realm.seed != state.seed + ":realm:" + str(i)
           for i, realm in enumerate(state.realms)):
        raise CampaignError("world identity mismatch")
    for i, world in enumerate(state.realms):
        validate_state(world)
        if i != state.current_realm and any(_portable(world).values()):
            raise CampaignError("portable inventory exists in an inactive world")
    if type(state.charges) is not int or not 0 <= state.charges <= 64:
        raise CampaignError("portal charges outside budget")
    if (not isinstance(state.completed_realms, tuple)
            or any(type(i) is not int or not 0 <= i < 4
                   for i in state.completed_realms)
            or len(set(state.completed_realms)) != len(state.completed_realms)):
        raise CampaignError("invalid completed realm ledger")
    if any(not state.realms[i].chapter_complete for i in state.completed_realms):
        raise CampaignError("completed-realm claim not backed by local state")
    if (not isinstance(state.archive, tuple) or len(state.archive) > 256
            or any(not isinstance(record, str) or len(record) > 128
                   for record in state.archive)):
        raise CampaignError("invalid world archive")
    if type(state.event_count) is not int or not 0 <= state.event_count <= MAX_NEXUS_EVENTS:
        raise CampaignError("invalid nexus event count")
    if (not isinstance(state.event_head, str) or len(state.event_head) != 64
            or any(c not in "0123456789abcdef" for c in state.event_head)):
        raise CampaignError("invalid nexus event hash")


def create_nexus(seed: str = "four-world-adventure") -> NexusState:
    if not isinstance(seed, str) or not 0 < len(seed.encode("utf-8")) <= 1024:
        raise CampaignError("invalid nexus seed")
    realms = tuple(create_campaign(
        key, seed + ":realm:" + str(i)
    ) for i, key in enumerate(REALM_IDS))
    # Players begin in the welcoming refuge. Unvisited worlds are empty of
    # player-carried inventory, but still have their own native resources.
    parked = (realms[0], *(_park(world) for world in realms[1:]))
    nexus = NexusState(seed, 0, tuple(parked), charges=8,
                       completed_realms=(), archive=())
    validate_nexus(nexus)
    return nexus


def active_world(state: NexusState) -> CampaignState:
    validate_nexus(state)
    return state.realms[state.current_realm]


def connections(state: NexusState) -> tuple[int, ...]:
    """A ring of distinct persistent worlds rather than one merged map."""
    validate_nexus(state)
    current = state.current_realm
    return tuple(sorted({(current - 1) % 4, (current + 1) % 4}))


def _updated_realms(state: NexusState, changes: dict[int, CampaignState]
                    ) -> tuple[CampaignState, ...]:
    new = list(state.realms)
    for index, world in changes.items():
        new[index] = world
    return tuple(new)


def act(state: NexusState, action: CampaignAction
        ) -> tuple[NexusState, NexusReceipt]:
    """Play a real campaign action in the current realm; persist its changes."""
    validate_nexus(state)
    if state.event_count >= MAX_NEXUS_EVENTS:
        raise CampaignError("nexus event limit reached")
    at = state.current_realm
    changed, underlying = step(state.realms[at], action)
    updates = {at: changed}
    # On a turn advance, other worlds evolve autonomously. Parked-player
    # hunger/energy are disposable and never transferred back to the traveler.
    if action.verb == "end_turn":
        for i, world in enumerate(state.realms):
            if i != at:
                evolved, _ = step(world, CampaignAction("end_turn"))
                updates[i] = _park(evolved)
    realms = _updated_realms(state, updates)
    completed = tuple(sorted(set(state.completed_realms) |
                             {i for i, world in enumerate(realms)
                              if world.chapter_complete}))
    archive = state.archive
    if completed != state.completed_realms:
        archive = (archive + (f"chapters:{','.join(map(str, completed))}",))[-256:]
    updated = replace(state, realms=realms, completed_realms=completed,
                      archive=archive)
    return _record(state, updated, "realm-action", at, at,
                   underlying.event_id, underlying.messages)


def travel(state: NexusState, target: int) -> tuple[NexusState, NexusReceipt]:
    """Cross between adjacent worlds with conservation of player inventory."""
    validate_nexus(state)
    if type(target) is not int or target not in connections(state):
        raise CampaignError("destination is not a neighboring realm")
    if state.event_count >= MAX_NEXUS_EVENTS:
        raise CampaignError("nexus event limit reached")
    if state.charges < 1:
        raise CampaignError("no portal charge remains")
    current = state.current_realm
    leaving = state.realms[current]
    destination = state.realms[target]
    if leaving.position not in (0, 4, 8):
        raise CampaignError("cross-world travel requires a town's portal")
    if leaving.energy < 2:
        raise CampaignError("too exhausted for a cross-world journey")
    arriving = replace(_arrive(destination, leaving), energy=leaving.energy - 2)
    parked = _park(leaving)
    updated = replace(state,
                      realms=_updated_realms(state, {
                          current: parked, target: arriving,
                      }),
                      current_realm=target,
                      charges=state.charges - 1,
                      archive=(state.archive +
                               (f"travel:{current}->{target}",))[-256:])
    return _record(state, updated, "realm-travel", current, target, "",
                   ("Crossed between independent original worlds",))


def recharge(state: NexusState, amount: int = 1) -> tuple[NexusState, NexusReceipt]:
    """Craft new interworld travel energy from tangible source resources."""
    validate_nexus(state)
    if type(amount) is not int or not 1 <= amount <= 3:
        raise CampaignError("charge amount must be 1–3")
    if state.event_count >= MAX_NEXUS_EVENTS:
        raise CampaignError("nexus event limit reached")
    current = state.current_realm
    traveler = state.realms[current]
    if traveler.position not in (0, 4, 8):
        raise CampaignError("recharge requires a town workshop")
    if traveler.stone < amount or traveler.wood < amount or traveler.coins < amount:
        raise CampaignError("not enough portal crafting resources")
    if state.charges + amount > 64:
        raise CampaignError("portal energy capacity reached")
    changed = replace(
        traveler, stone=traveler.stone - amount,
        wood=traveler.wood - amount, coins=traveler.coins - amount,
    )
    updated = replace(state,
                      realms=_updated_realms(state, {current: changed}),
                      charges=state.charges + amount)
    return _record(state, updated, "portal-recharge", current, current, "",
                   ("Crafted a finite portal charge with local resources",))


def nexus_replay(seed: str, commands: tuple[tuple[str, object], ...]
                 ) -> tuple[NexusState, tuple[NexusReceipt, ...]]:
    if not isinstance(commands, tuple) or len(commands) > MAX_NEXUS_EVENTS:
        raise CampaignError("invalid bounded nexus command sequence")
    state = create_nexus(seed)
    receipts = []
    for opcode, payload in commands:
        if opcode == "act":
            if not isinstance(payload, CampaignAction):
                raise CampaignError("act command requires CampaignAction")
            state, receipt = act(state, payload)
        elif opcode == "travel":
            state, receipt = travel(state, payload)
        elif opcode == "recharge":
            state, receipt = recharge(state, payload)
        else:
            raise CampaignError("unsupported nexus command")
        receipts.append(receipt)
    return state, tuple(receipts)


def nexus_save(state: NexusState) -> str:
    validate_nexus(state)
    payload = {"schema": NEXUS_SCHEMA, "state": asdict(state)}
    return json.dumps({"payload": payload, "checksum": _digest(payload)},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def nexus_restore(encoded: str) -> NexusState:
    if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > 1048576:
        raise CampaignError("nexus save too large or invalid")
    try:
        data = json.loads(encoded)
        if set(data) != {"payload", "checksum"}:
            raise CampaignError("nexus save envelope invalid")
        payload = data["payload"]
        if payload["schema"] != NEXUS_SCHEMA or _digest(payload) != data["checksum"]:
            raise CampaignError("nexus save identity mismatch")
        raw = payload["state"]
        if set(raw) != set(NexusState.__dataclass_fields__):
            raise CampaignError("unknown or missing nexus save fields")
        realms = []
        for world in raw["realms"]:
            # Delegate to the existing strict world-save decoder and enforce
            # all world-level schema and conservation validation.
            state_payload = {"schema": "original-campaign.v1", "state": world}
            wrapper = json.dumps({
                "payload": state_payload,
                "checksum": _digest(state_payload),
            }, sort_keys=True, separators=(",", ":"))
            realms.append(import_save(wrapper))
        raw["realms"] = tuple(realms)
        raw["completed_realms"] = tuple(raw["completed_realms"])
        raw["archive"] = tuple(raw["archive"])
        result = NexusState(**raw)
        validate_nexus(result)
        return result
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise CampaignError("nexus save validation failed") from exc
