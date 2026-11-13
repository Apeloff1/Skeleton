"""Closed operator API over the work queue; never pass model text as an instruction."""
from __future__ import annotations
from .contracts import refuse
ACTIONS=frozenset(("configure_budget","submit","inspect","list",
                   "claim","dispatch","reconcile","hold_unknown",
                   "abandon_before_dispatch","pending_events",
                   "ack_event","audit"))
def action(value):
    if type(value) is not str or value not in ACTIONS:
        refuse("unknown or high-risk work-order operation")
    return value
