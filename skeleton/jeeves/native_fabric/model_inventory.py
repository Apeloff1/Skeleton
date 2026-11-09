"""Read-only model identity reconciliation for approved offline GGUF packages.

This layer does NOT parse raw GGUF bytes, attest model rights, or load a native
engine. It cross-checks explicit installer vs live supervisor records, checks
resource budget implications, and marks absent physical evidence unqualified.
It must not be used to fabricate approval or bypass activate_checked.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .contracts import (
    ContractHold, digest, exact_integer, identifier, fingerprint, text,
)


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    model_sha256: str
    tokenizer_sha256: str
    package_sha256: str
    approved_source_sha256: str
    architecture: str
    context_ceiling: int
    output_ceiling: int
    source_rights_approved: bool
    native_loaded: bool
    native_backend_isolated: bool

    def __post_init__(self):
        for value in (
            self.model_sha256, self.tokenizer_sha256, self.package_sha256,
            self.approved_source_sha256,
        ):
            digest(value)
        identifier(self.architecture, "model architecture")
        exact_integer(self.context_ceiling, minimum=128, maximum=131072)
        exact_integer(self.output_ceiling, minimum=1, maximum=8192)
        if self.output_ceiling >= self.context_ceiling:
            raise ContractHold("model output exceeds native context")
        for value in (
            self.source_rights_approved, self.native_loaded,
            self.native_backend_isolated,
        ):
            if type(value) is not bool:
                raise ContractHold("model identity needs verified typed signals")

    @property
    def source_binding(self) -> str:
        return fingerprint({
            "schema": "jeeves.fabric.model_source_binding.v1",
            "model": self.model_sha256,
            "tokenizer": self.tokenizer_sha256,
            "package": self.package_sha256,
            "approved_source": self.approved_source_sha256,
            "architecture": self.architecture,
        })


def reconcile_installed_model(
    installed: ModelIdentity, active: ModelIdentity | None,
    *, requested_context: int, requested_output: int,
) -> dict[str, object]:
    if not isinstance(installed, ModelIdentity):
        raise ContractHold("installed model record required")
    exact_integer(requested_context, minimum=128, maximum=131072)
    exact_integer(requested_output, minimum=1, maximum=8192)
    if active is not None and not isinstance(active, ModelIdentity):
        raise ContractHold("typed live model record required")
    holds = []
    checked = []
    if not installed.source_rights_approved:
        holds.append("installed_source_rights_not_approved")
    else:
        checked.append("installer_rights_receipt")
    if requested_context > installed.context_ceiling:
        holds.append("requested_context_exceeds_installed_model")
    if requested_output >= requested_context or requested_output > installed.output_ceiling:
        holds.append("requested_output_exceeds_native_ceiling")
    if active is None:
        holds.append("no_active_native_model")
    else:
        if installed.source_binding != active.source_binding:
            holds.append("activated_source_identity_mismatch")
        else:
            checked.append("installed_and_active_model_identity")
        if not active.native_loaded:
            holds.append("model_was_not_loaded")
        if not active.native_backend_isolated:
            holds.append("native_backend_is_not_killable")
    return {
        "schema": "jeeves.fabric.model_inventory_reconciliation.v1",
        "installed_binding": installed.source_binding,
        "active_binding": active.source_binding if active else None,
        "checked": tuple(checked),
        "holds": tuple(holds),
        "eligible_for_live_qualification": not holds,
        "real_inference_observed": False,
        "device_qualified": False,
        "release_certified": False,
    }


@dataclass(frozen=True, slots=True)
class ModelQualification:
    source_binding: str
    native_turn_receipt_sha256: str | None
    sqlite_committed: bool
    cold_replayed: bool
    source_approved: bool
    device_pressure_tested: bool
    inflight_cancellation_tested: bool
    clean_install_tested: bool
    observed_platform: str | None

    def __post_init__(self):
        digest(self.source_binding)
        if self.native_turn_receipt_sha256 is not None:
            digest(self.native_turn_receipt_sha256)
        for flag in (
            self.sqlite_committed, self.cold_replayed,
            self.source_approved, self.device_pressure_tested,
            self.inflight_cancellation_tested, self.clean_install_tested,
        ):
            if type(flag) is not bool:
                raise ContractHold("strict model qualification flag required")
        if self.observed_platform is not None:
            text(self.observed_platform, maximum_bytes=128)

    def outstanding(self) -> tuple[str, ...]:
        requirements = (
            ("real_native_turn", self.native_turn_receipt_sha256 is not None),
            ("sqlite_commit", self.sqlite_committed),
            ("cold_replay", self.cold_replayed),
            ("approved_source", self.source_approved),
            ("device_pressure", self.device_pressure_tested),
            ("inflight_cancellation", self.inflight_cancellation_tested),
            ("clean_install", self.clean_install_tested),
            ("observed_platform", self.observed_platform is not None),
        )
        return tuple(label for label, ok in requirements if not ok)

    def to_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.fabric.model_qualification.v1",
            "source_binding": self.source_binding,
            "native_turn_receipt_sha256": self.native_turn_receipt_sha256,
            "outstanding": list(self.outstanding()),
            "production_readiness_demonstrated": not self.outstanding(),
            "independent_license_review_required": True,
            "release_certified": False,
        }


__all__ = ["ModelIdentity", "ModelQualification",
           "reconcile_installed_model"]
