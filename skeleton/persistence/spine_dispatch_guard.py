"""Identity guard for the runtime dispatcher.

Captures stable callable identity for start_dispatcher without invoking it.
Bound-method identity is represented by the underlying function and owning
instance, avoiding false replacement signals from transient bound-method
wrapper objects.
"""

from __future__ import annotations

from typing import Any


class SpineDispatchGuardError(RuntimeError):
    """Guard rejected its inputs. Not a maturity signal."""


def _callable_identity(callable_obj: Any) -> tuple[str, int, int | None]:
    function = getattr(callable_obj, "__func__", None)
    owner = getattr(callable_obj, "__self__", None)
    if function is not None and owner is not None:
        return ("bound-method", id(function), id(owner))
    return ("callable", id(callable_obj), None)


class SpineDispatchGuard:
    """Prove the dispatcher callable binding was not replaced or rebound."""

    def snapshot(self, runtime: Any) -> dict[str, Any]:
        start = getattr(runtime, "start_dispatcher", None)
        if not callable(start):
            raise SpineDispatchGuardError("runtime has no start_dispatcher")
        binding_kind, callable_id, owner_id = _callable_identity(start)
        return {
            "kind": "spine_dispatch_guard",
            "hit": True,
            "law": "dispatcher-identity-unchanged",
            "citation": "VOL-134",
            "binding_kind": binding_kind,
            "callable_id": callable_id,
            "owner_id": owner_id,
            "start_id": callable_id,
            "called": False,
            "runtime_replaced": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def compare(self, before: dict[str, Any], runtime: Any) -> dict[str, Any]:
        if not isinstance(before, dict) or before.get("kind") != "spine_dispatch_guard":
            raise SpineDispatchGuardError("before must be a dispatch guard card")
        required = ("binding_kind", "callable_id", "owner_id")
        if any(name not in before for name in required):
            raise SpineDispatchGuardError("before dispatch identity is incomplete")

        after = self.snapshot(runtime)
        same = (
            before["binding_kind"] == after["binding_kind"]
            and before["callable_id"] == after["callable_id"]
            and before["owner_id"] == after["owner_id"]
        )
        if not same:
            raise SpineDispatchGuardError("start_dispatcher identity changed")
        after["same"] = True
        after["called"] = False
        return after
