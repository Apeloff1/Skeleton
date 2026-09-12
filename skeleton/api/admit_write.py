"""admit_write — mutating-route admission (gf-server admit_write sibling).

Every write crosses sealed identity (middleware / require_seal), then
AdaptiveGate shed, then ChaosGovernor emergency-read-only. Fail-closed.
"""

from __future__ import annotations

from typing import Any, Optional

from skeleton.kernel.adaptive_gate import AdaptiveGate, Verdict
from skeleton.kernel.chaos import ChaosGovernor
from skeleton.kernel.errors import KernelError


class ShedError(KernelError):
    code = "API.SHED"
    http_status = 429


class EmergencyReadOnlyError(KernelError):
    code = "API.EMERGENCY_READ_ONLY"
    http_status = 503


# Process-wide defaults (tests inject via AdmitWrite / set_defaults).
_default_gate = AdaptiveGate(capacity=256, refill_per_sec=128)
_default_governor = ChaosGovernor()


def set_defaults(
    *,
    gate: Optional[AdaptiveGate] = None,
    governor: Optional[ChaosGovernor] = None,
) -> None:
    global _default_gate, _default_governor
    if gate is not None:
        _default_gate = gate
    if governor is not None:
        _default_governor = governor


def get_default_gate() -> AdaptiveGate:
    return _default_gate


def get_default_governor() -> ChaosGovernor:
    return _default_governor


def admit_write(
    *,
    priority: int = 1,
    gate: Optional[AdaptiveGate] = None,
    governor: Optional[ChaosGovernor] = None,
) -> None:
    """Raise ShedError / EmergencyReadOnlyError when write must not proceed.

    Call after seal verification. Does not mint identity — attester comes
    from RequestSealMiddleware / require_seal.
    """
    g = gate if gate is not None else _default_gate
    gov = governor if governor is not None else _default_governor
    verdict = g.admit(priority)
    if verdict is Verdict.SHED:
        gov.observe(False)
        raise ShedError("shed", context={"error": "shed"})
    if not gov.permits_writes():
        raise EmergencyReadOnlyError(
            "emergency_read_only", context={"error": "emergency_read_only"}
        )


class WriteAdmitMiddleware:
    """ASGI layer: POST/PUT/PATCH/DELETE → admit_write after seal.

    Open routes skipped. Safe methods (GET/HEAD/OPTIONS) skipped.
    Missing attester on protected path → 401 (Auth already enforces).
    """

    _MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    def __init__(
        self,
        app,
        *,
        policy: Any = None,
        gate: Optional[AdaptiveGate] = None,
        governor: Optional[ChaosGovernor] = None,
    ) -> None:
        self.app = app
        if policy is None:
            from skeleton.api.middleware import GatePolicy

            policy = GatePolicy()
        self.policy = policy
        self.gate = gate
        self.governor = governor

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = (scope.get("method") or "GET").upper()
        if method not in self._MUTATING:
            await self.app(scope, receive, send)
            return

        from starlette.requests import Request
        from skeleton.api.middleware import _json_response

        request = Request(scope, receive=receive)
        path = request.url.path
        if self.policy.is_open_route(path):
            await self.app(scope, receive, send)
            return

        try:
            admit_write(priority=1, gate=self.gate, governor=self.governor)
        except ShedError:
            resp = _json_response(429, {"error": "shed"})
            await resp(scope, receive, send)
            return
        except EmergencyReadOnlyError:
            resp = _json_response(503, {"error": "emergency_read_only"})
            await resp(scope, receive, send)
            return
        await self.app(scope, receive, send)
