"""Read-only, fail-closed Jeeves native source readiness.

Do not treat duck-typed worker fields or a self-asserted rights report as a
real installed GGUF. This bridge can become source-ready only if the SAME
canonical inspector used by the laptop first-turn path verifies an active,
isolated GGUF child, checked model archive, capacity lease and principal.

This never infers actual model generation, Windows device qualification,
source-rights independence or release approval from structural checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.laptop_runtime.installed_witness import (
    require_activated_source,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import (
    ExecutionSpine,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import (
    SpineDatabase,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import (
    SessionGate,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import (
    SupervisedAI,
)
from .native_source_fence import valid_source_snapshot


@dataclass(frozen=True, slots=True)
class JeevesNativeReadiness:
    model_bound: bool
    tenant_bound: bool
    sqlite_spine_present: bool
    source_receipt_bound: bool
    real_turn_witnessed: bool
    device_qualified: bool
    release_certified: bool
    holds: tuple[str, ...]

    @property
    def source_bridge_ready(self) -> bool:
        return (
            self.model_bound and self.tenant_bound
            and self.sqlite_spine_present and self.source_receipt_bound
        )

    def to_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.native_readiness.v1",
            "model_bound": self.model_bound,
            "tenant_bound": self.tenant_bound,
            "sqlite_spine_present": self.sqlite_spine_present,
            "source_receipt_bound": self.source_receipt_bound,
            "real_turn_witnessed": self.real_turn_witnessed,
            "device_qualified": self.device_qualified,
            "release_certified": self.release_certified,
            "source_bridge_ready": self.source_bridge_ready,
            "holds": list(self.holds),
        }


def inspect_native_jeeves(
    worker: Any, installed_receipt: Any | None = None,
) -> JeevesNativeReadiness:
    """Inspect installed source without making any model or SQLite writes.

    Any missing/uncertain private source evidence is a negative readiness
    verdict. Do not propagate native exception text or host file paths.
    """
    holds: list[str] = []
    model_bound = False
    tenant_bound = False
    identity = None
    try:
        identity = ActiveModel.from_supervisor(worker)
        model_bound = True
        tenant_bound = bool(identity.tenant and identity.subject)
    except Exception:
        holds.append("active GGUF model/tokenizer/principal unavailable")

    spine = getattr(worker, "spine", None)
    sqlite_spine_present = (
        type(worker) is SupervisedAI
        and type(spine) is ExecutionSpine
        and type(getattr(spine, "db", None)) is SpineDatabase
        and type(getattr(spine, "session_gate", None)) is SessionGate
        and callable(getattr(spine, "replay", None))
        and callable(getattr(spine, "turn", None))
    )
    if not sqlite_spine_present:
        holds.append("canonical descriptor-backed SQLite spine unavailable")

    source_receipt_bound = False
    if model_bound and tenant_bound and sqlite_spine_present and installed_receipt is not None:
        try:
            installed = require_activated_source(worker, installed_receipt)
            source_receipt_bound = valid_source_snapshot(installed, identity)
        except Exception:
            # A native child may fail health checking, expire its capacity
            # lease, lose source custody or become unreachable during read.
            # The failure is always a hold; never echo arbitrary error text.
            source_receipt_bound = False
    if not source_receipt_bound:
        holds.append("installed source, rights or live isolated GGUF not verified")
    holds.extend((
        "real native GGUF generation not witnessed by this inspection",
        "clean Windows 11/WSL2 and pressure qualification outstanding",
        "exact-head security, dependency and release gates outstanding",
    ))
    return JeevesNativeReadiness(
        model_bound, tenant_bound, sqlite_spine_present,
        source_receipt_bound, False, False, False, tuple(holds),
    )


__all__ = ["JeevesNativeReadiness", "inspect_native_jeeves"]
