"""Audit that a bind card did not start the runtime dispatcher.

Reads dispatcher_running when present. Does not call start_dispatcher.
"""

from __future__ import annotations

from typing import Any


class SpineBindAuditError(RuntimeError):
    """Audit rejected its inputs. Not a maturity signal."""


class SpineBindAudit:
    """Fail closed if a bind card claims the runtime was replaced."""

    def audit(self, runtime: Any, bind_card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(bind_card, dict):
            raise SpineBindAuditError("bind_card must be a dict")
        if bind_card.get("runtime_replaced") is True:
            raise SpineBindAuditError("bind card claims the runtime was replaced")
        running = getattr(runtime, "dispatcher_running", None)
        if callable(running) and running():
            raise SpineBindAuditError("dispatcher is running")
        return {
            "kind": "spine_bind_audit",
            "hit": True,
            "law": "bind-does-not-start-dispatcher",
            "citation": "VOL-134",
            "runtime_replaced": False,
            "dispatcher_running": False,
            "live_motor": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
