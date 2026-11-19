"""Composition boundary for evolving runtime admission contracts."""

from dataclasses import dataclass

from .gameforge_admission import Admission, decide
from .gameforge_dependency import DependencyGate
from .gameforge_lifecycle import ServiceLifecycle
from .gameforge_receipt import Receipt


@dataclass
class RuntimeContract:
    lifecycle: ServiceLifecycle
    dependencies: DependencyGate
    version: int = 1
    background_allowed: bool = True

    def __post_init__(self):
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version <= 0:
            raise ValueError("version must be a positive integer")
        if not isinstance(self.background_allowed, bool):
            raise TypeError("background_allowed must be a boolean")

    def admit(self, request_id, *, background=False, active=0, limit=1, read_only=False):
        if not isinstance(request_id, str) or not request_id:
            return Receipt("invalid-request", Admission.SHED.value, "missing_request_id")
        if not isinstance(background, bool) or not isinstance(read_only, bool):
            return Receipt(request_id, Admission.SHED.value, "invalid_flags")
        if (
            not isinstance(active, int)
            or isinstance(active, bool)
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or active < 0
            or limit <= 0
        ):
            return Receipt(request_id, Admission.SHED.value, "invalid_limits")
        if not self.lifecycle.can_accept:
            return Receipt(request_id, Admission.SHED.value, "lifecycle")
        if not self.dependencies.ready:
            return Receipt(request_id, Admission.SHED.value, "dependency")
        decision = decide(
            background_allowed=self.background_allowed,
            read_only=read_only,
            active=active,
            limit=limit,
            background=background,
        )
        return Receipt(request_id, decision.value, decision.value)
