"""Deterministic restoration quest workflow for the world director plane.

The module is a pure, bounded state transition engine. It does not perform
network I/O, persist receipts, authorize account access or certify a release.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

SCHEMA = "skeleton.quest_flow.v1"
QUEST_ID = "world_restoration"
DOMAIN = "world"
STAGES = (
    ("discover_restoration", "world:restoration:discover:proof", "world:restoration:stage:1"),
    ("prepare_restoration", "world:restoration:prepare:proof", "world:restoration:stage:2"),
    ("execute_restoration", "world:restoration:execute:proof", "world:restoration:stage:3"),
    ("resolve_restoration", "world:restoration:resolve:proof", "world:restoration:stage:4"),
)
MAX_EVENTS = 4096
MAX_EVIDENCE_ITEMS = 16


@dataclass(frozen=True, slots=True)
class QuestState:
    stage: int = 0
    version: int = 0
    status: str = "active"
    grants: frozenset[str] = field(default_factory=frozenset)
    event_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if type(self.stage) is not int or not 0 <= self.stage <= len(STAGES):
            raise ValueError("invalid-stage")
        if type(self.version) is not int or self.version < 0:
            raise ValueError("invalid-version")
        if self.status not in ("active", "completed", "abandoned"):
            raise ValueError("invalid-status")
        if self.status == "completed" and self.stage != len(STAGES):
            raise ValueError("completed-with-pending-stages")
        if self.status == "active" and self.stage == len(STAGES):
            raise ValueError("active-without-pending-stages")
        if type(self.grants) is not frozenset or type(self.event_ids) is not frozenset:
            raise ValueError("invalid-immutable-ledger")
        if any(type(v) is not str or not v for v in self.grants | self.event_ids):
            raise ValueError("invalid-ledger-entry")
        if len(self.event_ids) > MAX_EVENTS:
            raise ValueError("event-ledger-capacity")
        expected_grants = frozenset(stage[2] for stage in STAGES[:self.stage])
        if self.grants != expected_grants:
            raise ValueError("grant-ledger-mismatch")
        if self.version != len(self.event_ids):
            raise ValueError("event-version-mismatch")
        if self.status == "abandoned" and self.stage == len(STAGES):
            raise ValueError("abandoned-after-completion")


@dataclass(frozen=True, slots=True)
class Decision:
    event_id: str
    accepted: bool
    reason: str
    before_version: int
    after_version: int
    stage: int
    status: str


def _command(raw: Mapping[str, Any]) -> tuple[str, str, int, tuple[str, ...]]:
    if type(raw) is not dict or set(raw) != {"id", "action", "expected_version", "evidence"}:
        raise ValueError("invalid-command-shape")
    key, action, version, evidence = (
        raw["id"], raw["action"], raw["expected_version"], raw["evidence"]
    )
    if type(key) is not str or not 1 <= len(key) <= 128:
        raise ValueError("invalid-event-id")
    if action not in ("advance", "abandon", "inspect"):
        raise ValueError("unknown-action")
    if type(version) is not int or version < 0:
        raise ValueError("invalid-expected-version")
    if type(evidence) is not list or len(evidence) > MAX_EVIDENCE_ITEMS:
        raise ValueError("invalid-evidence")
    if any(type(item) is not str or not 1 <= len(item) <= 128 for item in evidence):
        raise ValueError("invalid-evidence-item")
    if len(evidence) != len(set(evidence)):
        raise ValueError("duplicate-evidence")
    return key, action, version, tuple(evidence)


def decide(state: QuestState, command: dict[str, Any]) -> tuple[QuestState, Decision]:
    """Apply exactly one validated command with optimistic version fencing."""
    if type(state) is not QuestState:
        raise TypeError("invalid-quest-state")
    event_id, action, expected_version, evidence = _command(command)

    def reject(reason: str) -> tuple[QuestState, Decision]:
        return state, Decision(
            event_id, False, reason, state.version, state.version,
            state.stage, state.status,
        )

    if event_id in state.event_ids:
        return reject("duplicate-event")
    if expected_version != state.version:
        return reject("stale-version")
    if state.status != "active":
        return reject("terminal-state")
    if len(state.event_ids) >= MAX_EVENTS:
        return reject("event-ledger-capacity")
    if action == "inspect":
        return reject("inspection-is-readonly")

    if action == "abandon":
        updated = QuestState(
            state.stage, state.version + 1, "abandoned",
            state.grants, state.event_ids | {event_id},
        )
        return updated, Decision(
            event_id, True, "abandoned", state.version, updated.version,
            updated.stage, updated.status,
        )

    name, required, grant = STAGES[state.stage]
    if required not in evidence:
        return reject("required-evidence-missing")
    if state.stage and STAGES[state.stage - 1][2] not in state.grants:
        return reject("prerequisite-grant-missing")
    next_stage = state.stage + 1
    next_status = "completed" if next_stage == len(STAGES) else "active"
    updated = QuestState(
        next_stage, state.version + 1, next_status,
        state.grants | {grant}, state.event_ids | {event_id},
    )
    return updated, Decision(
        event_id, True, "advanced", state.version, updated.version,
        updated.stage, updated.status,
    )


def inspect(state: QuestState) -> dict[str, Any]:
    if type(state) is not QuestState:
        raise TypeError("invalid-quest-state")
    next_key = STAGES[state.stage][0] if state.status == "active" else None
    required = STAGES[state.stage][1] if state.status == "active" else None
    return {
        "schema": SCHEMA, "quest_id": QUEST_ID, "domain": DOMAIN,
        "stage": state.stage, "stage_count": len(STAGES),
        "version": state.version, "status": state.status,
        "next_stage": next_key, "required_evidence": required,
        "grants": sorted(state.grants), "event_count": len(state.event_ids),
    }


def replay(
    commands: list[dict[str, Any]], initial: QuestState | None = None
) -> tuple[QuestState, tuple[Decision, ...]]:
    if type(commands) is not list or len(commands) > MAX_EVENTS:
        raise ValueError("invalid-replay-batch")
    state = QuestState() if initial is None else initial
    decisions: list[Decision] = []
    for command in commands:
        state, decision = decide(state, command)
        decisions.append(decision)
    return state, tuple(decisions)
