"""Identity guard for the runtime dispatcher.

Records the identity of start_dispatcher before and after a bind card. Does
not call it. A changed identity fails closed.
"""

from __future__ import annotations

from typing import Any


class SpineDispatchGuardError(RuntimeError):
    """Guard rejected its inputs. Not a maturity signal."""


class SpineDispatchGuard:
    """Prove the dispatcher callable was not replaced."""

    def snapshot(self, runtime: Any) -> dict[str, Any]:
        start = getattr(runtime, "start_dispatcher", None)
        if not callable(start):
            raise SpineDispatchGuardError("runtime has no start_dispatcher")
        return {
            "kind": "spine_dispatch_guard",
            "hit": True,
            "law": "dispatcher-identity-unchanged",
            "citation": "VOL-134",
            "start_id": id(start),
            "called": False,
            "runtime_replaced": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def compare(self, before: dict[str, Any], runtime: Any) -> dict[str, Any]:
        after = self.snapshot(runtime)
        same = before.get("start_id") == after["start_id"]
        if not same:
            raise SpineDispatchGuardError("start_dispatcher identity changed")
        after["same"] = True
        after["called"] = False
        return after
