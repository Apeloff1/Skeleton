"""Deterministic, source-bound quest transactions for offline authored games.

This module owns no new runtime service. It composes the canonical FLGB-13
quest graph, event and save contracts; a matching trigger is a game event,
not a security credential or proof of a real-world action.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from .flgb_gameplay_runtime import (
    GameplayContractError,
    GameplayEvent,
    QuestNode,
    SaveableGameplayState,
    quest_order,
    req_digest,
    req_id,
)

MAX_QUESTS = 4096
MAX_EVENTS = 100_000
MAX_ITEMS = 4096
MAX_REWARD = 1_000_000
MAX_CURRENCY = 1_000_000_000
SCHEMA_VERSION = 1


def _integer(value: object, minimum: int = 0, maximum: int = MAX_CURRENCY) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise GameplayContractError("invalid bounded integer")
    return value


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise GameplayContractError("non-canonical quest record") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class QuestReward:
    item_id: str | None = None
    quantity: int = 0
    currency: int = 0

    def __post_init__(self) -> None:
        if self.item_id is None:
            if self.quantity != 0:
                raise GameplayContractError("quantity without item")
        else:
            req_id(self.item_id, "item_id")
            _integer(self.quantity, 1, MAX_REWARD)
        _integer(self.currency, 0, MAX_REWARD)

    def as_record(self) -> dict[str, object]:
        return {"item_id": self.item_id, "quantity": self.quantity, "currency": self.currency}


@dataclass(frozen=True)
class QuestSpec:
    quest_id: str
    dependencies: tuple[str, ...]
    event_type: str
    source_id: str
    payload_digest: str
    reward: QuestReward = QuestReward()
    ending_id: str | None = None

    def __post_init__(self) -> None:
        req_id(self.quest_id, "quest_id")
        req_id(self.event_type, "event_type")
        req_id(self.source_id, "source_id")
        req_digest(self.payload_digest, "payload_digest")
        if self.ending_id is not None:
            req_id(self.ending_id, "ending_id")
        dependencies = tuple(sorted(self.dependencies))
        if self.quest_id in dependencies or len(set(dependencies)) != len(dependencies):
            raise GameplayContractError("invalid quest dependencies")
        for dependency in dependencies:
            req_id(dependency, "dependency")
        object.__setattr__(self, "dependencies", dependencies)

    def as_record(self) -> dict[str, object]:
        return {
            "quest_id": self.quest_id,
            "dependencies": list(self.dependencies),
            "event_type": self.event_type,
            "source_id": self.source_id,
            "payload_digest": self.payload_digest,
            "reward": self.reward.as_record(),
            "ending_id": self.ending_id,
        }


@dataclass(frozen=True)
class QuestTrigger:
    sequence: int
    quest_id: str
    event_type: str
    source_id: str
    payload_digest: str

    def __post_init__(self) -> None:
        _integer(self.sequence, 0, MAX_EVENTS - 1)
        req_id(self.quest_id, "quest_id")
        # Reuse the canonical event contract and its strict identity checks.
        GameplayEvent(self.sequence, self.event_type, self.source_id, self.payload_digest)

    def as_record(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "quest_id": self.quest_id,
            "event_type": self.event_type,
            "source_id": self.source_id,
            "payload_digest": self.payload_digest,
        }


class QuestPlan:
    def __init__(self, world_id: str, quests: Sequence[QuestSpec]) -> None:
        self.world_id = req_id(world_id, "world_id")
        if not quests or len(quests) > MAX_QUESTS:
            raise GameplayContractError("quest count out of bounds")
        ids = [quest.quest_id for quest in quests]
        if len(set(ids)) != len(ids):
            raise GameplayContractError("duplicate quest identity")
        self.quests = tuple(sorted(quests, key=lambda q: q.quest_id))
        self.by_id = {quest.quest_id: quest for quest in self.quests}
        self.order = quest_order(tuple(
            QuestNode(quest.quest_id, quest.dependencies, quest.payload_digest)
            for quest in self.quests
        ))
        self.digest = _digest(self.as_record())

    def as_record(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "world_id": self.world_id,
            "quests": [quest.as_record() for quest in self.quests],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "QuestPlan":
        if not isinstance(record, dict) or set(record) != {"schema_version", "world_id", "quests"}:
            raise GameplayContractError("invalid quest plan envelope")
        if record["schema_version"] != SCHEMA_VERSION or type(record["schema_version"]) is not int:
            raise GameplayContractError("unsupported quest plan version")
        raw = record["quests"]
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_QUESTS:
            raise GameplayContractError("invalid quest list")
        quests = []
        for item in raw:
            if not isinstance(item, dict) or set(item) != {
                "quest_id", "dependencies", "event_type", "source_id",
                "payload_digest", "reward", "ending_id",
            }:
                raise GameplayContractError("invalid quest entry")
            dependencies = item["dependencies"]
            reward = item["reward"]
            if not isinstance(dependencies, list) or not all(isinstance(x, str) for x in dependencies):
                raise GameplayContractError("invalid dependencies")
            if not isinstance(reward, dict) or set(reward) != {"item_id", "quantity", "currency"}:
                raise GameplayContractError("invalid reward entry")
            quests.append(QuestSpec(
                item["quest_id"], tuple(dependencies), item["event_type"],
                item["source_id"], item["payload_digest"],
                QuestReward(**reward), item["ending_id"],
            ))
        return cls(record["world_id"], quests)


@dataclass(frozen=True)
class QuestSession:
    world_id: str
    plan_digest: str
    completed: tuple[str, ...] = ()
    inventory: tuple[tuple[str, int], ...] = ()
    currency: int = 0
    ending_id: str | None = None
    events: tuple[QuestTrigger, ...] = ()

    def __post_init__(self) -> None:
        req_id(self.world_id, "world_id")
        req_digest(self.plan_digest, "plan_digest")
        _integer(self.currency)
        if len(self.events) > MAX_EVENTS or len(self.inventory) > MAX_ITEMS:
            raise GameplayContractError("quest session budget exceeded")
        if len(set(self.completed)) != len(self.completed):
            raise GameplayContractError("duplicate completion")
        for quest_id in self.completed:
            req_id(quest_id, "completed quest")
        for index, event in enumerate(self.events):
            if event.sequence != index:
                raise GameplayContractError("non-canonical event sequence")
        if tuple(sorted(self.inventory)) != self.inventory:
            raise GameplayContractError("inventory not canonical")
        if len({item for item, _ in self.inventory}) != len(self.inventory):
            raise GameplayContractError("duplicate inventory item")
        for item, count in self.inventory:
            req_id(item, "item_id")
            _integer(count, 1, MAX_CURRENCY)
        if self.ending_id is not None:
            req_id(self.ending_id, "ending_id")

    def as_state(self) -> dict[str, object]:
        return {
            "world_id": self.world_id, "plan_digest": self.plan_digest,
            "completed": list(self.completed),
            "inventory": [[item, count] for item, count in self.inventory],
            "currency": self.currency, "ending_id": self.ending_id,
        }

    @property
    def state_digest(self) -> str:
        return _digest(self.as_state())

    @property
    def save_metadata(self) -> SaveableGameplayState:
        return SaveableGameplayState(
            self.world_id, SCHEMA_VERSION, len(self.events),
            self.state_digest, self.plan_digest,
        )

    def save_record(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "plan_digest": self.plan_digest,
            "events": [event.as_record() for event in self.events],
            "state": self.as_state(),
            "state_digest": self.state_digest,
            "save_digest": self.save_metadata.digest,
        }


class QuestEngine:
    def __init__(self, plan: QuestPlan) -> None:
        self.plan = plan

    def new_session(self) -> QuestSession:
        return QuestSession(self.plan.world_id, self.plan.digest)

    def apply(self, session: QuestSession, trigger: QuestTrigger) -> QuestSession:
        # Public state is a value object, not a trusted mutable engine handle.
        # Reconstruct its provenance before accepting a reward-bearing action.
        if self.replay(session.events) != session:
            raise GameplayContractError("quest session lacks verified event history")
        return self._apply_verified(session, trigger)

    def _apply_verified(self, session: QuestSession, trigger: QuestTrigger) -> QuestSession:
        if session.world_id != self.plan.world_id or session.plan_digest != self.plan.digest:
            raise GameplayContractError("quest source identity changed")
        if len(session.events) >= MAX_EVENTS:
            raise GameplayContractError("event budget exhausted")
        if trigger.sequence != len(session.events):
            raise GameplayContractError("event sequence mismatch")
        quest = self.plan.by_id.get(trigger.quest_id)
        if quest is None:
            raise GameplayContractError("unknown quest")
        if trigger.quest_id in session.completed:
            raise GameplayContractError("quest already completed")
        if session.ending_id is not None:
            raise GameplayContractError("game already ended")
        if not set(quest.dependencies).issubset(session.completed):
            raise GameplayContractError("quest prerequisites incomplete")
        if (trigger.event_type, trigger.source_id, trigger.payload_digest) != (
            quest.event_type, quest.source_id, quest.payload_digest
        ):
            raise GameplayContractError("quest trigger does not match authored contract")
        items = dict(session.inventory)
        if quest.reward.item_id is not None:
            current = items.get(quest.reward.item_id, 0)
            if current + quest.reward.quantity > MAX_CURRENCY:
                raise GameplayContractError("inventory overflow")
            items[quest.reward.item_id] = current + quest.reward.quantity
        if len(items) > MAX_ITEMS:
            raise GameplayContractError("inventory capacity exceeded")
        if session.currency + quest.reward.currency > MAX_CURRENCY:
            raise GameplayContractError("currency overflow")
        return QuestSession(
            session.world_id, session.plan_digest,
            session.completed + (quest.quest_id,),
            tuple(sorted(items.items())),
            session.currency + quest.reward.currency,
            quest.ending_id,
            session.events + (trigger,),
        )

    def replay(self, triggers: Sequence[QuestTrigger]) -> QuestSession:
        if len(triggers) > MAX_EVENTS:
            raise GameplayContractError("event budget exceeded")
        session = self.new_session()
        for trigger in triggers:
            session = self._apply_verified(session, trigger)
        return session

    def restore(self, record: Mapping[str, Any]) -> QuestSession:
        if not isinstance(record, dict) or set(record) != {
            "schema_version", "plan_digest", "events", "state",
            "state_digest", "save_digest",
        }:
            raise GameplayContractError("invalid quest save envelope")
        if type(record["schema_version"]) is not int or record["schema_version"] != SCHEMA_VERSION:
            raise GameplayContractError("unsupported quest save version")
        if record["plan_digest"] != self.plan.digest:
            raise GameplayContractError("save belongs to a different authored plan")
        raw_events = record["events"]
        if not isinstance(raw_events, list) or len(raw_events) > MAX_EVENTS:
            raise GameplayContractError("invalid event log")
        events = []
        for raw in raw_events:
            if not isinstance(raw, dict) or set(raw) != {
                "sequence", "quest_id", "event_type", "source_id", "payload_digest",
            }:
                raise GameplayContractError("invalid event record")
            events.append(QuestTrigger(**raw))
        replayed = self.replay(events)
        if (record["state"], record["state_digest"], record["save_digest"]) != (
            replayed.as_state(), replayed.state_digest, replayed.save_metadata.digest
        ):
            raise GameplayContractError("quest save tampered or non-canonical")
        return replayed
