"""Explicit allowed durable work transitions independent from model output."""
from __future__ import annotations
from .errors import deny

TRANSITIONS={
  "pending":frozenset(("running","held","cancelled")),
  "running":frozenset(("completed","failed","held","cancel_requested")),
  "cancel_requested":frozenset(("completed","failed","held")),
  "held":frozenset(("pending","cancelled")),
  "completed":frozenset(),
  "failed":frozenset(),
  "cancelled":frozenset(),
}


def authorize_transition(before:str,after:str,*,operator:bool=False)->None:
    if type(before) is not str or type(after) is not str:
        deny("transition-type")
    if before not in TRANSITIONS or after not in TRANSITIONS[before]:
        deny("transition-forbidden")
    if before=="held" and after=="pending" and operator is not True:
        deny("transition-operator-required")


def terminal(state:str)->bool:
    if type(state) is not str or state not in TRANSITIONS:
        deny("transition-state")
    return state in ("completed","failed","cancelled")


def must_hold_on_unknown_outcome(*,generation_started:bool,
                                authoritative_commit_known:bool)->bool:
    if type(generation_started) is not bool or type(authoritative_commit_known) is not bool:
        deny("outcome-type")
    return generation_started and not authoritative_commit_known
