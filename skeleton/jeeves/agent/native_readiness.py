"""Read-only readiness distinctions for a Jeeves native source bridge.

Structural checks here deliberately do not become a physical laptop or a
verified model-generation claim. Source identity, real installation receipts
and independently witnessed native execution have separate evidence levels.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel


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
        return (self.model_bound and self.tenant_bound and
                self.sqlite_spine_present and self.source_receipt_bound)

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


def inspect_native_jeeves(worker: Any, installed_receipt: Any | None = None) -> JeevesNativeReadiness:
    holds: list[str] = []
    try:
        identity = ActiveModel.from_supervisor(worker)
        model_bound = True
        tenant_bound = bool(identity.tenant and identity.subject)
    except (ValueError, AttributeError):
        model_bound = False
        tenant_bound = False
        holds.append("actual GGUF model/tokenizer/principal mismatch")
    sqlite_spine_present = (
        hasattr(getattr(worker, "spine", None), "db")
        and callable(getattr(getattr(worker, "spine", None), "replay", None))
        and callable(getattr(getattr(worker, "spine", None), "turn", None))
    )
    if not sqlite_spine_present:
        holds.append("authoritative execution spine unavailable")
    source_receipt_bound = (
        installed_receipt is not None
        and getattr(installed_receipt, "content_verified", False) is True
        and getattr(installed_receipt, "rights_approved", False) is True
        and bool(getattr(installed_receipt, "source_sha", None))
        and bool(getattr(installed_receipt, "archive_sha256", None))
        and model_bound
        and getattr(installed_receipt, "model_sha256", None) == identity.model_sha256
    )
    if not source_receipt_bound:
        holds.append("source-bound model installer receipt absent or invalid")
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
