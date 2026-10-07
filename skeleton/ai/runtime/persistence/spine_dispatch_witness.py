"""Witness that the runtime dispatcher was not started.

Reads dispatcher_running when present. Does not call start_dispatcher.
A running dispatcher fails closed.
"""

from __future__ import annotations

from typing import Any


class SpineDispatchWitnessError(RuntimeError):
    """Dispatch witness rejected its inputs. Not a maturity signal."""


class SpineDispatchWitness:
    """Record that the dispatcher is dark."""

    def card(self, runtime: Any) -> dict[str, Any]:
        start = getattr(runtime, "start_dispatcher", None)
        if not callable(start):
            raise SpineDispatchWitnessError("runtime has no start_dispatcher")
        running = getattr(runtime, "dispatcher_running", None)
        if callable(running) and running():
            raise SpineDispatchWitnessError("dispatcher is running")
        return {
            "kind": "spine_dispatch_witness",
            "hit": False,
            "law": "dispatcher-not-started",
            "citation": "VOL-134",
            "start_id": id(start),
            "called": False,
            "dispatcher_running": False,
            "runtime_replaced": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
