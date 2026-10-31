"""Deterministic trade_merchant_seats governance ballot for fictional world simulation.

Pure state transition with optimistic concurrency and stable delegate identity.
All ballots are game data, not real-world elections or legal permissions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

POLICY_ID = "trade_merchant_seats"
DOMAIN = "trade"
TOPIC = "merchant_seats"
SCHEMA = "skeleton.faction_governance.v1"
DELEGATES = ("delegate_1", "delegate_2", "delegate_3", "delegate_4", "delegate_5", "delegate_6", "delegate_7")
QUORUM = 5
APPROVAL = 4
MAX_RECEIPTS = 256


@dataclass(frozen=True, slots=True)
class State:
    phase: str = "idle"
    proposal: str = ""
    ballots: tuple[tuple[str, str], ...] = ()
    version: int = 0
    event_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.phase not in ("idle", "voting", "approved", "rejected"):
            raise ValueError("phase")
        if type(self.proposal) is not str or len(self.proposal) > 128:
            raise ValueError("proposal")
        if (self.phase == "idle") != (self.proposal == ""):
            raise ValueError("proposal-phase")
        if type(self.ballots) is not tuple or len(self.ballots) > len(DELEGATES):
            raise ValueError("ballots")
        if any(type(b) is not tuple or len(b) != 2 or
               b[0] not in DELEGATES or b[1] not in ("yes", "no") for b in self.ballots):
            raise ValueError("ballot-entry")
        if len({b[0] for b in self.ballots}) != len(self.ballots):
            raise ValueError("duplicate-delegate")
        if type(self.version) is not int or self.version < 0:
            raise ValueError("version")
        if type(self.event_ids) is not frozenset or len(self.event_ids) > MAX_RECEIPTS:
            raise ValueError("event-ledger")
        if any(type(v) is not str or not 1 <= len(v) <= 128 for v in self.event_ids):
            raise ValueError("event-identity")


@dataclass(frozen=True, slots=True)
class Receipt:
    event_id: str
    accepted: bool
    reason: str
    prior_version: int
    next_version: int
    phase: str


def _parse(raw: dict[str, Any]) -> tuple[str, str, str, str, str, int]:
    if type(raw) is not dict or set(raw) != {
        "id", "action", "proposal", "delegate", "choice", "expected_version"
    }:
        raise ValueError("command-shape")
    key, action, proposal, delegate, choice, version = (
        raw[k] for k in ("id", "action", "proposal", "delegate", "choice", "expected_version")
    )
    if type(key) is not str or not 1 <= len(key) <= 128:
        raise ValueError("event-id")
    if type(action) is not str or action not in ("open", "cast", "finalize", "cancel", "inspect"):
        raise ValueError("action")
    if type(proposal) is not str or not 1 <= len(proposal) <= 128:
        raise ValueError("proposal")
    if type(delegate) is not str or delegate not in ("",) + DELEGATES:
        raise ValueError("delegate")
    if type(choice) is not str or choice not in ("", "yes", "no"):
        raise ValueError("choice")
    if type(version) is not int or version < 0:
        raise ValueError("version")
    return key, action, proposal, delegate, choice, version


def decide(state: State, command: dict[str, Any]) -> tuple[State, Receipt]:
    if type(state) is not State:
        raise TypeError("state")
    key, action, proposal, delegate, choice, version = _parse(command)

    def reject(reason: str) -> tuple[State, Receipt]:
        return state, Receipt(key, False, reason, state.version, state.version, state.phase)

    if key in state.event_ids:
        return reject("duplicate-event")
    if version != state.version:
        return reject("stale-version")
    if len(state.event_ids) >= MAX_RECEIPTS:
        return reject("receipt-capacity")
    if action == "inspect":
        return reject("read-only")
    if action == "open":
        if state.phase != "idle":
            return reject("already-open")
        if delegate or choice:
            return reject("unexpected-vote")
        next_state = State("voting", proposal, (), version + 1, state.event_ids | {key})
        reason = "opened"
    else:
        if state.phase != "voting":
            return reject("not-voting")
        if proposal != state.proposal:
            return reject("proposal-mismatch")
        if action == "cast":
            if delegate not in DELEGATES or choice not in ("yes", "no"):
                return reject("invalid-vote")
            if any(old_delegate == delegate for old_delegate, _ in state.ballots):
                return reject("delegate-already-voted")
            next_state = State(
                "voting", state.proposal, state.ballots + ((delegate, choice),),
                version + 1, state.event_ids | {key}
            )
            reason = "cast"
        elif action == "finalize":
            if delegate or choice:
                return reject("unexpected-vote")
            if len(state.ballots) < QUORUM:
                return reject("quorum-not-met")
            yes = sum(vote == "yes" for _, vote in state.ballots)
            phase = "approved" if yes >= APPROVAL and yes > len(state.ballots) // 2 else "rejected"
            next_state = State(
                phase, state.proposal, state.ballots, version + 1,
                state.event_ids | {key}
            )
            reason = phase
        elif action == "cancel":
            if delegate or choice:
                return reject("unexpected-vote")
            next_state = State(
                "rejected", state.proposal, state.ballots, version + 1,
                state.event_ids | {key}
            )
            reason = "cancelled"
        else:
            return reject("invalid-phase-action")
    return next_state, Receipt(
        key, True, reason, state.version, next_state.version, next_state.phase
    )


def snapshot(state: State) -> dict[str, Any]:
    if type(state) is not State:
        raise TypeError("state")
    return {
        "schema": SCHEMA, "policy_id": POLICY_ID, "domain": DOMAIN,
        "topic": TOPIC, "phase": state.phase, "proposal": state.proposal,
        "voted": len(state.ballots), "yes": sum(c == "yes" for _, c in state.ballots),
        "no": sum(c == "no" for _, c in state.ballots),
        "quorum": QUORUM, "approval_threshold": APPROVAL,
        "version": state.version, "receipt_count": len(state.event_ids)
    }


def replay(commands: list[dict[str, Any]], initial: State | None = None):
    if type(commands) is not list or len(commands) > MAX_RECEIPTS:
        raise ValueError("batch")
    state = State() if initial is None else initial
    receipts: list[Receipt] = []
    for command in commands:
        state, receipt = decide(state, command)
        receipts.append(receipt)
    return state, tuple(receipts)
