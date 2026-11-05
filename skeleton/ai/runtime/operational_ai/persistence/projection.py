"""Deterministic read-model projection; no authority over the event journal."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from ..authority.canonical import ContractViolation, digest
from .journal import Event, EventJournal


@dataclass(frozen=True,slots=True)
class Projection:
    stream: str
    revision: int
    state: dict[str, Any]
    state_digest: str
    journal_digest: str


def reduce_events(journal: EventJournal, stream: str, reducer: Callable[[dict[str,Any],Event],dict[str,Any]],
                  initial: dict[str,Any] | None=None, *, max_events: int=100_000) -> Projection:
    events = journal.replay(stream)
    if len(events)>max_events:
        raise ContractViolation("projection replay budget exceeded")
    state = dict(initial or {})
    for event in events:
        state = reducer(dict(state),event)
        if not isinstance(state,dict):
            raise ContractViolation("projection reducer returned non-object")
        digest(state)
    rev,head = journal.head(stream)
    if rev!=len(events):
        raise ContractViolation("journal changed during read-model projection")
    return Projection(stream,rev,state,digest(state),head)


def summarize_ai_turns(state: dict[str,Any], event: Event) -> dict[str,Any]:
    """Allowlist only audited AI outcomes, never treat proposals as actions."""
    if event.kind=="ai.turn.committed":
        state["completed_turns"]=state.get("completed_turns",0)+1
        state["last_turn_id"]=event.payload["request_id"]
        state["last_output_digest"]=event.payload["output_digest"]
    elif event.kind=="ai.turn.failed":
        state["failed_turns"]=state.get("failed_turns",0)+1
    return state
