"""No-execution readiness and content provenance audit for comparative libretro.

Inspects up to thirty source-pinned study games, core registries, 169-target
controller legends, multi-file source presence, and live ten-lane disk budgets.
Deep file hashing is explicit (potentially many gigabytes). It does not load or
run game executables, fetch ROMs, certify rights or claim game playability.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping
from typing import Any

from .game_comparison_schema import ComparativeStudyError, digest, plan_study, validate_study
from .game_comparison_controllers import controller_layout_for_target, supported_controller_layout_catalog
from .game_comparison_media import LocalComparativeMedia, _open_no_symlink
from .game_comparison_studio import _storage_waves
from .game_emulator_catalog import GameEmulatorRegistry

SCHEMA="skeleton.game.comparative_operator_readiness.v1"
MAX_INLINE_BYTES=16*1024*1024
CHUNK=1*1024*1024


class ComparisonReadinessError(ValueError):
    """Study readiness cannot be determined from the approved local authority."""


def _source_file_audit(game: Mapping[str,Any], *, deep_hash: bool) -> dict[str,Any]:
    """Check no symlink ancestor, exact file type/size/hash; never load into RAM."""
    path=game["source_path"]
    fd=_open_no_symlink(path)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or not 1<=st.st_size<=MAX_INLINE_BYTES:
            raise ComparisonReadinessError("Single-file source exceeds inline ROM bounds")
        first=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)
        stream_sha=hashlib.sha256()
        total=0
        while True:
            chunk=os.read(fd,CHUNK)
            if not chunk:break
            total+=len(chunk)
            if total>MAX_INLINE_BYTES:
                raise ComparisonReadinessError("Game source grew beyond bounded inline size")
            stream_sha.update(chunk)
        after=os.fstat(fd)
        if first!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
            raise ComparisonReadinessError("Source file changed during readiness scan")
        if total!=st.st_size or stream_sha.hexdigest()!=game["source_sha256"]:
            raise ComparisonReadinessError("Actual source bytes differ from pinned SHA-256")
        return {
            "admitted_source_kind":"exact_single_file_rom",
            "source_bytes":total,
            "pinned_media_sha256":game["source_sha256"],
            "all_file_hashes_verified":True,
            "source_is_regular_and_symlink_free":True,
        }
    finally:
        os.close(fd)


def _bundle_file_audit(game: Mapping[str,Any], *, deep_hash: bool) -> dict[str,Any]:
    manifest=game["content_bundle"]
    media=LocalComparativeMedia(manifest)
    file_rows=manifest["files"]
    if deep_hash:
        for row in file_rows:
            ref=media.bundle.files[row["name"]]
            actual=hashlib.sha256()
            total=0
            for chunk in media.reader(ref):
                total+=len(chunk)
                actual.update(chunk)
            if total!=ref.size_bytes or actual.hexdigest()!=ref.sha256:
                raise ComparisonReadinessError("Actual disc file SHA-256 differs from pinned manifest")
    return {
        "admitted_source_kind":"operator_owned_governed_multifile",
        "source_bytes":sum(row["size_bytes"] for row in file_rows),
        "file_count":len(file_rows),
        "pinned_media_sha256":media.bundle_digest,
        "all_file_hashes_verified":deep_hash,
        "source_is_regular_and_symlink_free":True,
        "remaining_gate":None if deep_hash else "Large disc full-file SHA-256 check deferred until native materialization or --deep-hash",
    }


def inspect_game_comparison_readiness(
    study: Mapping[str,Any], *,
    deep_hash: bool = False,
    probe_sandbox: bool = False,
    registry: GameEmulatorRegistry | None = None,
    free_temp_bytes: int | None = None,
) -> dict[str,Any]:
    """Report precise build/install blockers without launching a libretro core."""
    if type(deep_hash) is not bool or type(probe_sandbox) is not bool:
        raise ComparisonReadinessError("Host and media probes must be exact booleans")
    from .game_comparison_host_preflight import inspect_native_host_runtime

    host=inspect_native_host_runtime(probe_sandbox=probe_sandbox)
    model=validate_study(dict(study))
    plan=plan_study(model)
    installed=registry if registry is not None else GameEmulatorRegistry.from_environment()
    if free_temp_bytes is None:
        free_temp_bytes=shutil.disk_usage(tempfile.gettempdir()).free
    if type(free_temp_bytes) is not int or free_temp_bytes<0:
        raise ComparisonReadinessError("Host temporary disk capacity must be an exact nonnegative integer")
    games={}
    for row in model["games"]:
        blockers=[]
        try:
            core=installed.resolve_core(row["core_id"])
            if row["target_id"] not in core.target_ids:
                raise ComparisonReadinessError("Approved core does not declare this exact target")
            core_status="approved_core_registry_metadata_resolved_not_gameplay_tested"
        except (ValueError,OSError,RuntimeError) as exc:
            blockers.append("core:"+type(exc).__name__)
            core_status="installed_or_approved_core_unavailable"
        layout=controller_layout_for_target(row["target_id"],row["controller_devices"])
        try:
            source=(_bundle_file_audit(row,deep_hash=deep_hash)
                    if row.get("content_bundle") else _source_file_audit(row,deep_hash=deep_hash))
        except (ValueError,OSError,RuntimeError) as exc:
            blockers.append("source:"+type(exc).__name__)
            source={"source_status":"local_media_unavailable_or_changed",
                    "all_file_hashes_verified":False,"pinned_media_sha256":None}
        if row["rights_evidence_digest"] is None:
            blockers.append("source_rights_record_missing_for_opt_in_learning")
        ready=not any(x.startswith("core:") or x.startswith("source:") for x in blockers)
        games[row["id"]]={
            "game_id":row["id"],"target_id":row["target_id"],"core_id":row["core_id"],
            "release_phase":row["series_phase"],
            "core_status":core_status,
            "source":source,
            "controller_profile_name":layout["profile_name"],
            "controller_mapping_generic":layout["generic_fallback"],
            "controller_device_ports":[item["device"] for item in layout["ports"]],
            "actual_core_input_device_support_qualified":False,
            "operator_rights_record_present":row["rights_evidence_digest"] is not None,
            "rights_independently_verified":False,
            "source_and_registry_preflight_passed":ready,
            "blockers":blockers,
        }
    cohorts=[]
    by_id={g["id"]:g for g in model["games"]}
    for batch in plan["batches"]:
        selected=[by_id[x] for x in batch["game_ids"]]
        try:
            waves,budget=_storage_waves(
                selected,requested_slots=model["max_active"],
                free_temp_bytes=free_temp_bytes,
            )
            concurrency=[len(wave) for wave in waves]
            disk_error=None
        except ComparativeStudyError:
            budget=min(16*1024**3,free_temp_bytes//3)
            concurrency=[]
            disk_error="A game in this cohort exceeds the bounded temporary disk plan"
        cohorts.append({
            "batch_index":batch["batch_index"],
            "game_ids":batch["game_ids"],
            "requested_max_live_sessions":model["max_active"],
            "resource_limited_wave_sizes":concurrency,
            "requires_multiple_waves":len(concurrency)>1,
            "supports_simultaneous_live_desk_without_reduction":len(concurrency)==1,
            "source_and_core_admitted":all(games[id]["source_and_registry_preflight_passed"] for id in batch["game_ids"]),
            "temporary_disk_budget_bytes":budget,
            "disk_issue":disk_error,
            "host_runtime_prerequisites_passed":host["native_launch_preflight_passed"],
            "ready_for_simultaneous_live_desk":(
                len(concurrency)==1 and disk_error is None
                and host["native_launch_preflight_passed"]
                and all(games[identity]["source_and_registry_preflight_passed"] for identity in batch["game_ids"])
            ),
        })
    compact=sorted(games)
    report={
        "schema_version":SCHEMA,
        "study_id":model["study_id"],
        "source_manifest_sha256":digest(model),
        "approved_registry_sha256":installed.registry_digest,
        "game_count":len(model["games"]),
        "maximum_simultaneous_games":model["max_active"],
        "pair_count":len(model["pairs"]),
        "available_temporary_disk_bytes_at_preflight":free_temp_bytes,
        "host_runtime":host,
        "ready_for_all_live_study_cohorts":all(c["ready_for_simultaneous_live_desk"] for c in cohorts),
        "game_preflight_pass_count":sum(x["source_and_registry_preflight_passed"] for x in games.values()),
        "core_input_hardware_qualified_count":0,
        "full_media_hash_checks_performed":deep_hash,
        "games":{key:games[key] for key in compact},
        "cohorts":cohorts,
        "canonical_controller_target_summary":{
            "declared_targets":supported_controller_layout_catalog()["target_count"],
            "accurate_physical_hardware_controllers_certified":0,
        },
        "runtime_correctness_guaranteed":False,
        "rom_and_bios_legal_rights_independently_verified":False,
        "native_emulation_executed_by_doctor":False,
        "production_model_weights_modified":False,
    }
    report["readiness_sha256"]=digest(report)
    return report
