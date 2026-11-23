"""Signed event authority for approved environmental RPG event actions.

Covers GF-P0-98 (connect approved environmental RPG event actions to the
existing quest/canon and save-state authority in each era engine) and
GF-P0-196 (extend reference physics proxies to NPC/gear/interaction
controllers with signed event authority).

``evaluate_environment_events`` only proposes. This module is the single
place that turns an approved proposal into a save-state change:

1. An operator (or the era engine's authority) signs an ``EventApproval``
   over the decision's ``evidence_digest`` with HMAC-SHA256.
2. ``commit_approved_events`` verifies every signature, checks each action
   against the quest graph / canon rules and the controller registry, and
   applies the whole batch atomically to an immutable ``SaveState``.
3. Every applied action is appended to a hash-chained journal, so replay
   can prove the exact order and authority of every mutation.

Any failure rejects the whole batch and leaves the prior state untouched.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import sha256
import hmac
import json
from types import MappingProxyType
from typing import Iterable, Mapping

from .game_frontier_rpg_events import RPGEventAction, RPGEventDecision

APPROVAL_SCHEMA = "skeleton.forge.frontier_event_approval.v1"
GENESIS = "0" * 64


class EventAuthorityError(ValueError):
    pass


def _canon(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _freeze(mapping: Mapping) -> Mapping:
    return MappingProxyType(dict(sorted(mapping.items())))


# --------------------------------------------------------------------------
# Quest / canon authority
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class QuestSpec:
    quest_id: str
    stages: tuple[str, ...]
    prerequisites: tuple[str, ...] = ()
    era_engines: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.quest_id or not 1 <= len(self.stages) <= 256:
            raise EventAuthorityError("quest needs id and 1..256 stages")
        if len(set(self.stages)) != len(self.stages):
            raise EventAuthorityError("duplicate quest stage")


@dataclass(frozen=True)
class CanonRules:
    """Canon constraints the event layer may not contradict."""

    quests: Mapping[str, QuestSpec]
    immutable_flags: frozenset[str] = frozenset()
    reputation_bounds: tuple[int, int] = (-1000, 1000)

    @classmethod
    def build(cls, quests: Iterable[QuestSpec], **kwargs) -> "CanonRules":
        table = {}
        for q in quests:
            if q.quest_id in table:
                raise EventAuthorityError("duplicate quest id")
            table[q.quest_id] = q
        for q in table.values():
            missing = set(q.prerequisites) - set(table)
            if missing:
                raise EventAuthorityError(f"unknown prerequisite {sorted(missing)}")
        return cls(_freeze(table), **kwargs)


# --------------------------------------------------------------------------
# Controller registry (P0-196)
# --------------------------------------------------------------------------

CONTROLLER_KINDS = frozenset(("npc", "gear", "interaction"))

#: Action kinds each controller kind may receive.
CONTROLLER_ACTIONS: Mapping[str, frozenset[str]] = {
    "npc": frozenset(("set_npc_emotion", "show_dialogue", "start_combat",
                      "take_damage", "heal_health", "set_faction_reputation")),
    "gear": frozenset(("consume_item", "craft_item", "inspect_instrument",
                       "apply_gameplay_effect", "take_damage")),
    "interaction": frozenset(("open_shop", "world_portal", "spawn_prefab",
                              "despawn_prefab", "trigger_impact_fx",
                              "trigger_foliage_fx", "deform_terrain")),
}


@dataclass(frozen=True)
class ControllerBinding:
    controller_id: str
    kind: str
    era_engines: frozenset[str]
    max_health: int = 100

    def __post_init__(self) -> None:
        if self.kind not in CONTROLLER_KINDS:
            raise EventAuthorityError("unknown controller kind")
        if not self.controller_id or len(self.controller_id) > 128:
            raise EventAuthorityError("controller id required")
        if not self.era_engines:
            raise EventAuthorityError("controller must declare era engines")
        if type(self.max_health) is not int or not 1 <= self.max_health <= 1_000_000:
            raise EventAuthorityError("max_health out of bounds")


# --------------------------------------------------------------------------
# Save state
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SaveState:
    era_engine: str
    flags: Mapping[str, bool] = field(default_factory=lambda: _freeze({}))
    quest_stage: Mapping[str, int] = field(default_factory=lambda: _freeze({}))
    completed_quests: frozenset[str] = frozenset()
    reputation: Mapping[str, int] = field(default_factory=lambda: _freeze({}))
    controller_health: Mapping[str, int] = field(default_factory=lambda: _freeze({}))
    inventory: Mapping[str, int] = field(default_factory=lambda: _freeze({}))
    xp: int = 0
    last_fired_ms: Mapping[str, int] = field(default_factory=lambda: _freeze({}))
    journal_head: str = GENESIS
    revision: int = 0

    def snapshot(self) -> dict:
        return {
            "era": self.era_engine, "flags": dict(self.flags),
            "quest_stage": dict(self.quest_stage),
            "completed": sorted(self.completed_quests),
            "reputation": dict(self.reputation),
            "health": dict(self.controller_health),
            "inventory": dict(self.inventory), "xp": self.xp,
            "last_fired_ms": dict(self.last_fired_ms),
            "journal_head": self.journal_head, "revision": self.revision,
        }

    @property
    def digest(self) -> str:
        return sha256(_canon(self.snapshot()).encode()).hexdigest()


# --------------------------------------------------------------------------
# Approvals
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class EventApproval:
    evidence_digest: str
    page_id: str
    era_engine: str
    authority_id: str
    signature: str

    def body(self) -> dict:
        return {"schema": APPROVAL_SCHEMA, "evidence": self.evidence_digest,
                "page": self.page_id, "era": self.era_engine,
                "authority": self.authority_id}


def _mac(key: bytes, body: Mapping) -> str:
    if type(key) is not bytes or len(key) < 16:
        raise EventAuthorityError("authority key must be >=16 bytes")
    return hmac.new(key, _canon(body).encode(), sha256).hexdigest()


def approve_decision(decision: RPGEventDecision, *, era_engine: str,
                     authority_id: str, key: bytes) -> EventApproval:
    if not authority_id:
        raise EventAuthorityError("authority id required")
    unsigned = EventApproval(decision.evidence_digest, decision.page_id,
                             era_engine, authority_id, "")
    return replace(unsigned, signature=_mac(key, unsigned.body()))


# --------------------------------------------------------------------------
# Commit
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class JournalEntry:
    sequence: int
    page_id: str
    action: Mapping[str, str]
    authority_id: str
    evidence_digest: str
    prev: str
    entry_digest: str

    def recompute(self) -> str:
        body = {"seq": self.sequence, "page": self.page_id,
                "action": dict(self.action), "authority": self.authority_id,
                "evidence": self.evidence_digest, "prev": self.prev}
        return sha256(_canon(body).encode()).hexdigest()


@dataclass(frozen=True)
class CommitResult:
    state: SaveState
    journal: tuple[JournalEntry, ...]
    deferred_presentation: tuple[RPGEventAction, ...]


#: Actions that only affect presentation; recorded, then handed to the
#: runtime without touching save state.
PRESENTATION_ACTIONS = frozenset((
    "show_dialogue", "play_cutscene", "play_music", "spatial_audio",
    "change_camera", "trigger_impact_fx", "trigger_foliage_fx",
    "change_light", "weather_transition", "change_tide", "set_world_axis",
    "inspect_instrument", "save_bookmark", "open_shop", "world_portal",
    "spawn_prefab", "despawn_prefab", "deform_terrain", "craft_item",
    "unlock_skill", "start_combat", "set_npc_emotion",
    "apply_gameplay_effect",
))


class _Draft:
    def __init__(self, state: SaveState):
        self.flags = dict(state.flags)
        self.stage = dict(state.quest_stage)
        self.done = set(state.completed_quests)
        self.rep = dict(state.reputation)
        self.health = dict(state.controller_health)
        self.inv = dict(state.inventory)
        self.xp = state.xp


def _int_value(action: RPGEventAction, low: int, high: int) -> int:
    try:
        value = int(action.value)
    except ValueError:
        raise EventAuthorityError(f"{action.kind} needs integer value") from None
    if str(value) != action.value.strip() or not low <= value <= high:
        raise EventAuthorityError(f"{action.kind} value out of bounds")
    return value


def _controller(controllers: Mapping[str, ControllerBinding], action: RPGEventAction,
                era: str) -> ControllerBinding | None:
    binding = controllers.get(action.target)
    if binding is None:
        return None
    if era not in binding.era_engines:
        raise EventAuthorityError(f"controller {binding.controller_id} not bound in {era}")
    if action.kind not in CONTROLLER_ACTIONS[binding.kind]:
        raise EventAuthorityError(
            f"{binding.kind} controller cannot receive {action.kind}")
    return binding


def _apply(draft: _Draft, action: RPGEventAction, canon: CanonRules,
           controllers: Mapping[str, ControllerBinding], era: str) -> bool:
    """Apply one action; return True if it mutated save state."""
    ctrl = _controller(controllers, action, era)
    kind = action.kind
    if kind == "set_flag":
        if action.target in canon.immutable_flags:
            raise EventAuthorityError(f"canon flag {action.target} is immutable")
        if action.value not in ("true", "false"):
            raise EventAuthorityError("set_flag value must be true/false")
        draft.flags[action.target] = action.value == "true"
        return True
    if kind in ("start_quest", "advance_quest"):
        quest = canon.quests.get(action.target)
        if quest is None:
            raise EventAuthorityError(f"quest {action.target} not in canon")
        if quest.era_engines and era not in quest.era_engines:
            raise EventAuthorityError(f"quest {quest.quest_id} not in era {era}")
        if quest.quest_id in draft.done:
            raise EventAuthorityError("quest already completed in canon")
        if kind == "start_quest":
            if quest.quest_id in draft.stage:
                raise EventAuthorityError("quest already started")
            if not set(quest.prerequisites) <= draft.done:
                raise EventAuthorityError("quest prerequisites incomplete")
            draft.stage[quest.quest_id] = 0
            return True
        if quest.quest_id not in draft.stage:
            raise EventAuthorityError("cannot advance an unstarted quest")
        nxt = draft.stage[quest.quest_id] + 1
        if nxt >= len(quest.stages):
            raise EventAuthorityError("quest has no further stage")
        if action.value and action.value not in quest.stages:
            raise EventAuthorityError("unknown quest stage")
        index = quest.stages.index(action.value) if action.value else nxt
        if index != nxt:
            raise EventAuthorityError("quest stages must advance one at a time")
        if index == len(quest.stages) - 1:
            del draft.stage[quest.quest_id]
            draft.done.add(quest.quest_id)
        else:
            draft.stage[quest.quest_id] = index
        return True
    if kind == "set_faction_reputation":
        low, high = canon.reputation_bounds
        draft.rep[action.target] = _int_value(action, low, high)
        return True
    if kind in ("take_damage", "heal_health"):
        if ctrl is None:
            raise EventAuthorityError(f"{kind} needs a registered controller")
        amount = _int_value(action, 0, ctrl.max_health)
        current = draft.health.get(ctrl.controller_id, ctrl.max_health)
        sign = -1 if kind == "take_damage" else 1
        draft.health[ctrl.controller_id] = max(0, min(ctrl.max_health,
                                                      current + sign * amount))
        return True
    if kind == "consume_item":
        count = _int_value(action, 1, 1_000_000)
        have = draft.inv.get(action.target, 0)
        if have < count:
            raise EventAuthorityError("cannot consume more items than held")
        draft.inv[action.target] = have - count
        return True
    if kind == "award_xp":
        draft.xp += _int_value(action, 0, 1_000_000)
        return True
    if kind in PRESENTATION_ACTIONS:
        return False
    raise EventAuthorityError(f"no authority path for {kind}")


def commit_approved_events(
    state: SaveState,
    decisions: Iterable[RPGEventDecision],
    approvals: Mapping[str, EventApproval],
    *,
    canon: CanonRules,
    controllers: Mapping[str, ControllerBinding],
    keys: Mapping[str, bytes],
    now_ms: int,
) -> CommitResult:
    """Atomically apply approved decisions. ``approvals`` keyed by evidence digest."""
    if type(now_ms) is not int or now_ms < max(state.last_fired_ms.values(), default=0):
        raise EventAuthorityError("canonical clock moved backwards")
    draft = _Draft(state)
    fired = dict(state.last_fired_ms)
    head = state.journal_head
    seq = state.revision
    journal: list[JournalEntry] = []
    presentation: list[RPGEventAction] = []
    seen: set[str] = set()
    for decision in decisions:
        if decision.evidence_digest in seen:
            raise EventAuthorityError("duplicate decision in batch")
        seen.add(decision.evidence_digest)
        approval = approvals.get(decision.evidence_digest)
        if approval is None:
            raise EventAuthorityError(f"decision {decision.page_id} not approved")
        key = keys.get(approval.authority_id)
        if key is None:
            raise EventAuthorityError("unknown approving authority")
        if not hmac.compare_digest(_mac(key, approval.body()), approval.signature):
            raise EventAuthorityError("approval signature invalid")
        if approval.page_id != decision.page_id or approval.era_engine != state.era_engine:
            raise EventAuthorityError("approval does not match decision/era")
        for action in decision.actions:
            mutated = _apply(draft, action, canon, controllers, state.era_engine)
            if not mutated:
                presentation.append(action)
            seq += 1
            body = {"seq": seq, "page": decision.page_id,
                    "action": dict(action.__dict__),
                    "authority": approval.authority_id,
                    "evidence": decision.evidence_digest, "prev": head}
            entry_digest = sha256(_canon(body).encode()).hexdigest()
            journal.append(JournalEntry(seq, decision.page_id,
                                        _freeze(action.__dict__),
                                        approval.authority_id,
                                        decision.evidence_digest, head,
                                        entry_digest))
            head = entry_digest
        fired[decision.page_id] = now_ms
    new_state = SaveState(
        state.era_engine, _freeze(draft.flags), _freeze(draft.stage),
        frozenset(draft.done), _freeze(draft.rep), _freeze(draft.health),
        _freeze(draft.inv), draft.xp, _freeze(fired), head, seq)
    return CommitResult(new_state, tuple(journal), tuple(presentation))


def verify_journal(journal: Iterable[JournalEntry], *, start: str = GENESIS) -> str:
    """Re-derive the hash chain; return the head digest or raise."""
    head = start
    for entry in journal:
        if entry.prev != head:
            raise EventAuthorityError(f"journal break at {entry.sequence}")
        if entry.recompute() != entry.entry_digest:
            raise EventAuthorityError(f"journal entry {entry.sequence} tampered")
        head = entry.entry_digest
    return head
