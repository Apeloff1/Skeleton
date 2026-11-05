"""Laptop-first, read-only operational readiness inspection for Jeeves.

This command is intentionally usable when the native GGUF model cannot load:
it inspects the source-bound installation receipt, private SQLite custody,
and locally observable Linux memory/disk. It never creates a native worker,
executes a model, installs weights, guesses device telemetry or repairs
unknown effects. Presence of model shards is not a license review; actual
model inference, tokenizer attestation and Windows 11/WSL2 acceptance remain
separate release holds.
"""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from skeleton.ai.runtime.operational_ai.deployment.install.doctor import (
    inspect_installed_model, InstalledModelReport,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.device_observer import inspect_device
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase

from .cold_doctor import inspect_native_operations, NativeColdFabricHold
from .contracts import ContractHold, digest, exact_integer, fingerprint, identifier


class NativeLaptopHold(ContractHold):
    """Laptop installed bytes, protected state or operator identity not safe."""


@dataclass(frozen=True, slots=True)
class LaptopInspection:
    tenant: str
    subject: str
    expected_model_sha256: str
    expected_tokenizer_sha256: str
    installed_model_sha256: str | None
    archive_sha256: str | None
    model_bytes: int | None
    installation_source_verified: bool
    operator_rights_receipt: bool
    protected_runtime_state_verified: bool
    observed_available_ram_bytes: int | None
    observed_available_disk_bytes: int | None
    memory_floor_met: bool
    disk_floor_met: bool
    cold_native_custody_sha256: str | None
    unresolved_native_effects: bool | None
    holds: tuple[str, ...]

    def __post_init__(self):
        identifier(self.tenant,"tenant")
        identifier(self.subject,"subject")
        digest(self.expected_model_sha256)
        digest(self.expected_tokenizer_sha256)
        if self.installed_model_sha256 is not None:
            digest(self.installed_model_sha256)
        if self.archive_sha256 is not None:
            digest(self.archive_sha256)
        if self.cold_native_custody_sha256 is not None:
            digest(self.cold_native_custody_sha256)
        for field in ("model_bytes","observed_available_ram_bytes",
                      "observed_available_disk_bytes"):
            if getattr(self,field) is not None:
                exact_integer(getattr(self,field),maximum=2**53-1)
        for field in (
            "installation_source_verified","operator_rights_receipt",
            "protected_runtime_state_verified","memory_floor_met",
            "disk_floor_met",
        ):
            if type(getattr(self,field)) is not bool:
                raise NativeLaptopHold("readiness assertion must be strict boolean")
        if self.unresolved_native_effects is not None and type(
            self.unresolved_native_effects
        ) is not bool:
            raise NativeLaptopHold("uncertainty state must be tri-valued")
        if len(self.holds)>32 or len(set(self.holds))!=len(self.holds):
            raise NativeLaptopHold("bounded unique readiness holds required")
        for value in self.holds:
            identifier(value,"hold code")

    @property
    def eligible_for_manual_native_acceptance(self)->bool:
        return not self.holds

    def to_public_record(self)->dict[str,object]:
        """Never include a private source path, prompt, shard or token."""
        return {
            "schema":"jeeves.native_laptop_readonly_inspection.v1",
            "principal_sha256":fingerprint({
                "tenant":self.tenant,"subject":self.subject,
                "model":self.expected_model_sha256,
                "tokenizer":self.expected_tokenizer_sha256,
            }),
            "expected_model_sha256":self.expected_model_sha256,
            "expected_tokenizer_sha256":self.expected_tokenizer_sha256,
            "installed_model_sha256":self.installed_model_sha256,
            "archive_sha256":self.archive_sha256,
            "model_bytes":self.model_bytes,
            "installation_source_verified":self.installation_source_verified,
            "operator_rights_receipt":self.operator_rights_receipt,
            "protected_runtime_state_verified":self.protected_runtime_state_verified,
            "observed_available_ram_bytes":self.observed_available_ram_bytes,
            "observed_available_disk_bytes":self.observed_available_disk_bytes,
            "memory_floor_met":self.memory_floor_met,
            "disk_floor_met":self.disk_floor_met,
            "cold_native_custody_sha256":self.cold_native_custody_sha256,
            "unresolved_native_effects":self.unresolved_native_effects,
            "holds":list(self.holds),
            "eligible_for_manual_native_acceptance":self.eligible_for_manual_native_acceptance,
            "actual_native_model_loaded":False,
            "physical_forward_pass_witnessed":False,
            "real_device_pressure_qualified":False,
            "windows_11_wsl2_clean_install_qualified":False,
            "independent_model_license_review":False,
            "native_cancellation_qualified":False,
            "all_release_gates_passed":False,
            "release_certified":False,
        }


def inspect_laptop(
    *,model_root:Path|None,
    state_dir:Path,
    tenant:str,subject:str,
    model_sha256:str,tokenizer_sha256:str,
    minimum_available_ram_bytes:int=2147483648,
    minimum_available_disk_bytes:int=1073741824,
)->LaptopInspection:
    """Fail closed per subsystem and preserve a complete set of next holds."""
    for label,path in (("private state",state_dir),("model root",model_root)):
        if path is not None and (
            not isinstance(path,Path) or not path.is_absolute()
            or ".." in path.parts
        ):
            raise NativeLaptopHold("absolute canonical "+label+" required")
    if state_dir is None:
        raise NativeLaptopHold("explicit state root required")
    identifier(tenant,"tenant");identifier(subject,"subject")
    digest(model_sha256);digest(tokenizer_sha256)
    for label, floor in (
        ("available memory floor", minimum_available_ram_bytes),
        ("state disk floor", minimum_available_disk_bytes),
    ):
        if type(floor) is not int or not 1 <= floor <= 2**53 - 1:
            raise NativeLaptopHold("invalid bounded " + label)
    # Typed identity is checked before any private model or state read.
    Identity(tenant,subject,model_sha256,tokenizer_sha256)
    holds=[]
    installed=None
    if model_root is None:
        holds.append("installed_model_unavailable")
    else:
        try:
            candidate=inspect_installed_model(model_root)
            if not isinstance(candidate,InstalledModelReport):
                raise NativeLaptopHold("installed model doctor returned untyped proof")
            installed=candidate
        except Exception:
            # All failures are admission holds, including unknown source
            # and path errors. Never disclose private installer exceptions.
            holds.append("installed_source_verification_failed")
    source_ok=bool(
        installed is not None
        and installed.content_verified is True
        and installed.archive_sha256
        and installed.source_sha
    )
    rights_ok=bool(installed is not None and installed.rights_approved is True)
    if not source_ok and "installed_source_verification_failed" not in holds:
        holds.append("installed_source_unverified")
    if not rights_ok:
        holds.append("source_rights_not_approved")
    if installed is not None and installed.model_sha256!=model_sha256:
        holds.append("installed_model_digest_mismatch")
    state=None
    try:
        state=inspect_native_operations(
            state_dir=state_dir,tenant=tenant,subject=subject,
            model_sha256=model_sha256,tokenizer_sha256=tokenizer_sha256,
        )
        if type(state) is not dict or state.get("status")!="readonly-inspected-not-native-activated":
            raise NativeLaptopHold("protected custody doctor has wrong contract")
        if state.get("holds"):
            holds.append("unresolved_native_custody")
    except Exception:
        holds.append("protected_native_state_unavailable")
        state=None
    available_mem=None
    available_disk=None
    mem_floor=False
    disk_floor=False
    try:
        observed=inspect_device(state_dir)
        if (type(observed) is not dict
            or observed.get("measurement_only") is not True
            or observed.get("qualified_device") is not False):
            raise NativeLaptopHold("device observer invented a qualification")
        available_mem=observed.get("memory_available_bytes")
        available_disk=observed.get("state_storage_available_bytes")
        exact_integer(available_mem,maximum=2**53-1)
        exact_integer(available_disk,maximum=2**53-1)
        mem_floor=available_mem>=minimum_available_ram_bytes
        disk_floor=available_disk>=minimum_available_disk_bytes
        if not mem_floor:
            holds.append("insufficient_observed_memory")
        if not disk_floor:
            holds.append("insufficient_observed_disk")
    except Exception:
        holds.append("device_memory_or_disk_unknown")
    # Source-only evaluation of the installed tokenizer bytes is absent.
    # Only an activated native worker can prove this exact identity; leave
    # a separate explicit hold even if other observations are healthy.
    holds.append("active_tokenizer_identity_unverified")
    holds.append("physical_native_inference_unverified")
    holds.append("independent_model_rights_review_outstanding")
    holds.append("device_pressure_and_cancellation_unqualified")
    holds.append("consumer_windows_install_unqualified")
    return LaptopInspection(
        tenant=tenant,subject=subject,
        expected_model_sha256=model_sha256,
        expected_tokenizer_sha256=tokenizer_sha256,
        installed_model_sha256=(
            installed.model_sha256 if installed is not None else None
        ),
        archive_sha256=(
            installed.archive_sha256 if installed is not None else None
        ),
        model_bytes=(
            installed.model_bytes if installed is not None else None
        ),
        installation_source_verified=source_ok,
        operator_rights_receipt=rights_ok,
        protected_runtime_state_verified=state is not None,
        observed_available_ram_bytes=available_mem,
        observed_available_disk_bytes=available_disk,
        memory_floor_met=mem_floor,disk_floor_met=disk_floor,
        cold_native_custody_sha256=(
            fingerprint(state) if state is not None else None
        ),
        unresolved_native_effects=(
            None if state is None else not state["unknown_effects_clear"]
        ),
        holds=tuple(dict.fromkeys(holds)),
    )


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description="Read-only laptop first-use Jeeves native source and SQLite doctor",
    )
    parser.add_argument("--model-root",type=Path)
    parser.add_argument("--state-dir",type=Path,required=True)
    parser.add_argument("--tenant",required=True)
    parser.add_argument("--subject",required=True)
    parser.add_argument("--model-sha256",required=True)
    parser.add_argument("--tokenizer-sha256",required=True)
    parser.add_argument("--minimum-ram-bytes",type=int,default=2147483648)
    parser.add_argument("--minimum-disk-bytes",type=int,default=1073741824)
    args=parser.parse_args(argv)
    try:
        report=inspect_laptop(
            model_root=args.model_root,state_dir=args.state_dir,
            tenant=args.tenant,subject=args.subject,
            model_sha256=args.model_sha256,
            tokenizer_sha256=args.tokenizer_sha256,
            minimum_available_ram_bytes=args.minimum_ram_bytes,
            minimum_available_disk_bytes=args.minimum_disk_bytes,
        )
        sys.stdout.write(json.dumps(
            report.to_public_record(),
            sort_keys=True,ensure_ascii=False,allow_nan=False,
            separators=(",",":"),
        )+"\n")
        return 3 if report.holds else 0
    except (Exception,KeyboardInterrupt) as exc:
        sys.stderr.write(json.dumps({
            "schema":"jeeves.native_laptop_readonly_inspection.v1",
            "status":"held",
            "error_class":type(exc).__name__,
            "model_activated":False,
            "release_certified":False,
        },sort_keys=True)+"\n")
        return 2


if __name__=="__main__":
    raise SystemExit(main())


__all__=["NativeLaptopHold","LaptopInspection","inspect_laptop","main"]
