"""Source-bound studio qualification ledger for actual multi-console campaigns.

This is a read-side assurance projection over the canonical campaign receipts,
plus a deliberately separate, explicit operator-only native ROM build action.
It does not grant Jeeves shell/toolchain execution, emulate cartridges, assess
IP rights, approve publication, or treat Dragon notes as model improvements.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .contracts import canonical_digest
from .studio_build_qualification import (
    NativeBuildQualificationError,
    _BUILD_ADAPTERS, _header, _regular, _verify_source, qualify_native_build,
)
from .studio_campaign import (
    CampaignOrder, StudioCampaignError,
    _atomic_json, _inspect_campaign_unlocked, _load_json, _verify_target,
)
from .studio_campaign_lock import campaign_lock

SCHEMA = "skeleton.game_builder.production_assurance.v1"
QUALIFICATION_SCHEMA = "skeleton.game_builder.campaign_rom_evidence.v1"
GATES = (
    "original_world_source",
    "replay_proof_source",
    "indexed_sprites_and_descriptors",
    "browser_engine_source",
    "godot_engine_source",
    "native_platform_source",
    "exact_source_attestation",
    "native_rom_compiled",
    "cartridge_structure_checked",
    "emulator_playthrough_executed",
    "controller_response_verified",
    "visual_and_audio_runtime_qualified",
    "rights_and_license_review_approved",
    "dragon_knowledge_review_approved",
    "extended_recovery_endurance_qualified",
    "release_signoff",
)
SOURCE_GATES = frozenset(GATES[:7])
NATIVE_GATES = frozenset(GATES[7:9])


class StudioAssuranceError(ValueError):
    """A production claim lacks matching exact-source or executable evidence."""


def _relative_rom(root: Path, target: str) -> Path:
    return root / "qualifications" / target / "qualified.rom"


def _qualification_receipt(root: Path, target: str, source_identity: str) -> dict | None:
    directory = root / "qualifications" / target
    record_file = directory / "qualification.json"
    if not record_file.exists():
        if _relative_rom(root, target).exists():
            raise StudioAssuranceError("binary exists without authoritative build receipt")
        return None
    if directory.is_symlink() or record_file.is_symlink():
        raise StudioAssuranceError("qualification symlink is not acceptable evidence")
    record = _load_json(record_file)
    if (record.get("schema") != QUALIFICATION_SCHEMA or
            record.get("target") != target or
            record.get("source_identity") != source_identity):
        raise StudioAssuranceError("compiled cartridge is not bound to current project")
    if canonical_digest({k: v for k, v in record.items()
                         if k != "evidence_digest"}) != record.get("evidence_digest"):
        raise StudioAssuranceError("qualified binary record has changed")
    evidence = record.get("build")
    if (not isinstance(evidence, dict) or evidence.get("target") != target
            or evidence.get("binary_built") is not True
            or evidence.get("rom_header_verified") is not True
            or evidence.get("tools_invoked") is not True):
        raise StudioAssuranceError("claimed compilation lacks executed native build receipt")
    if canonical_digest({k: v for k, v in evidence.items()
                         if k != "receipt_digest"}) != evidence.get("receipt_digest"):
        raise StudioAssuranceError("toolchain result digest mismatch")
    source = root / "targets" / target
    try:
        _, actual_source = _verify_source(source, target)
    except (NativeBuildQualificationError, OSError) as exc:
        raise StudioAssuranceError("native source changed after compilation") from exc
    if actual_source != evidence.get("source_digest"):
        raise StudioAssuranceError("compiled binary is bound to a different source revision")
    artifact = _relative_rom(root, target)
    if artifact.is_symlink():
        raise StudioAssuranceError("compiled ROM must not be a symlink")
    try:
        body = _regular(artifact, 8 * 1024 * 1024)
        _header(_BUILD_ADAPTERS[target][4], body)
    except (NativeBuildQualificationError, OSError) as exc:
        raise StudioAssuranceError("compiled ROM bytes or header are invalid") from exc
    if (sha256(body).hexdigest() != evidence.get("binary_sha256")
            or len(body) != evidence.get("binary_size")):
        raise StudioAssuranceError("ROM differs from the recorded toolchain output")
    return record


def qualify_campaign_target(
    order: CampaignOrder, root: str | Path, target: str, *,
    authorized: bool, execute: bool, timeout_seconds: int = 45,
) -> dict:
    """Compile exactly one completed target with an operator-authorized toolchain.

    Successful ROMs and evidence live outside the immutable source bundle;
    qualified, denied, unsupported and missing-toolchain states are distinct.
    """
    if authorized is not True:
        raise PermissionError("native compilation must have local operator authorization")
    if execute is not True:
        raise StudioAssuranceError("compilation requires an explicit execute opt-in")
    if not isinstance(order, CampaignOrder) or target not in order.targets:
        raise StudioAssuranceError("target does not belong to typed campaign")
    if target not in _BUILD_ADAPTERS:
        raise StudioAssuranceError("no bounded toolchain adapter for this console")
    base = Path(root)
    with campaign_lock(base):
        state = _inspect_campaign_unlocked(order, base)
        if target not in state["completed_targets"]:
            raise StudioAssuranceError("source stage must have exact verified completion")
        identity = state["identity"]
        previous = _qualification_receipt(base, target, identity)
        if previous is not None:
            return {
                "target": target, "native_rom_compiled": True,
                "already_qualified": True,
                "evidence_digest": previous["evidence_digest"],
                "source_identity": identity,
            }
        target_dir = base / "qualifications" / target
        if target_dir.is_symlink():
            raise StudioAssuranceError("native output cannot be a symlink")
        target_dir.mkdir(parents=True, exist_ok=True)
        output = _relative_rom(base, target)
        if output.exists() or output.is_symlink():
            raise StudioAssuranceError("unreceipted native ROM may not be overwritten")
        result = qualify_native_build(
            base / "targets" / target, target, authorized=True,
            execute=True, output=output, timeout_seconds=timeout_seconds,
        )
        receipt = result.as_receipt()
        if not result.binary_built or not result.rom_header_verified:
            return {
                "target": target, "native_rom_compiled": False,
                "already_qualified": False,
                "blocker": result.blocker,
                "toolchain_available": result.toolchain_available,
                "tools_invoked": result.tools_invoked,
                "source_identity": identity,
                "model_training_performed": False,
            }
        body = {
            "schema": QUALIFICATION_SCHEMA, "target": target,
            "source_identity": identity,
            "build": receipt,
            "emulator_playthrough_verified": False,
            "hardware_controller_qualified": False,
            "publication_authorized": False,
        }
        record = {**body, "evidence_digest": canonical_digest(body)}
        _atomic_json(target_dir / "qualification.json", record)
        _qualification_receipt(base, target, identity)
        return {
            "target": target, "native_rom_compiled": True,
            "already_qualified": False,
            "binary_sha256": receipt["binary_sha256"],
            "evidence_digest": record["evidence_digest"],
            "source_identity": identity,
            "emulator_playthrough_verified": False,
            "hardware_controller_qualified": False,
            "publication_authorized": False,
        }


def inspect_production_assurance(order: CampaignOrder, root: str | Path) -> dict:
    """Recheck real on-disk campaign artifacts and exact qualified binaries.

    Missing E2E, learning, permission, and release evidence always fails
    closed; a developer may not simply pass an 'all gates passed' dictionary.
    """
    if not isinstance(order, CampaignOrder):
        raise StudioAssuranceError("typed canonical campaign order required")
    base = Path(root)
    with campaign_lock(base):
        campaign = _inspect_campaign_unlocked(order, base)
        by_target = []
        passed = 0
        for target in order.targets:
            source = base / "targets" / target
            source_receipt = None
            if target in campaign["completed_targets"]:
                source_receipt = _verify_target(
                    source, order.project_id, target, campaign["identity"],
                )
            binary = None
            if source_receipt is not None and target in _BUILD_ADAPTERS:
                binary = _qualification_receipt(base, target, campaign["identity"])
            gates = {}
            for gate in GATES:
                if gate in SOURCE_GATES and source_receipt is not None:
                    status, reason = "artifact_integrity_checked", None
                elif gate in NATIVE_GATES and binary is not None:
                    status, reason = "binary_structure_checked", None
                elif gate in NATIVE_GATES and target not in _BUILD_ADAPTERS:
                    status, reason = "adapter_unavailable", "approved_native_toolchain_missing"
                else:
                    status, reason = "not_qualified", (
                        "source_not_generated" if source_receipt is None
                        else "independent_runtime_or_approval_evidence_required"
                    )
                gates[gate] = {"status": status, "blocker": reason}
                if status in {"artifact_integrity_checked", "binary_structure_checked"}:
                    passed += 1
            by_target.append({
                "target": target,
                "source_receipt_digest": (
                    source_receipt["receipt_digest"] if source_receipt else None
                ),
                "native_binary_evidence_digest": (
                    binary["evidence_digest"] if binary else None
                ),
                "gates": gates,
                "release_ready": False,
                "dragon_auto_training_approved": False,
            })
        count = len(order.targets) * len(GATES)
        body = {
            "schema": SCHEMA,
            "campaign_identity": campaign["identity"],
            "project_id": order.project_id,
            "total_targets": len(order.targets),
            "targets_with_exact_source": campaign["targets_with_verified_source"],
            "native_roms_structurally_verified": sum(
                row["native_binary_evidence_digest"] is not None for row in by_target
            ),
            "checked_gates": passed,
            "total_gates": count,
            "evidence_gate_coverage_percent": round(100 * passed / count, 2),
            "release_qualification_percent": 0,
            "all_targets_release_ready": False,
            "rights_approval_inferred": False,
            "dragon_training_or_weight_promotion_performed": False,
            "targets": by_target,
        }
        return {**body, "report_digest": canonical_digest(body)}


__all__ = [
    "StudioAssuranceError", "GATES", "qualify_campaign_target",
    "inspect_production_assurance",
]
