#!/usr/bin/env python3
"""Fail-closed, read-only on-host readiness matrix for offline Jeeves Docker.

Each gate runs its canonical independent validator. This cannot endorse a
release: protected chat authority, database-level recovery, real GPU
inference and independently signed release evidence require separate
qualified instruments not implemented by this source-only planner.
No secrets, raw Docker inspect/Compose JSON or model-generated text emitted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts import local_ai_docker as host
from scripts import local_ai_offline_compose as compose
from scripts import local_ai_offline_launch as launch
from scripts import local_ai_device_admission as device
from scripts import local_ai_data_rehydration as restore
from scripts import local_ai_mongo_majority as mongo

SCHEMA = "skeleton.local-ai.docker.readiness-matrix.v1"
GATES = (
    "offline_image_archive_and_compose",
    "physical_device_inventory",
    "real_running_container_isolation",
    "local_backend_provider_readiness_observation",
    "independent_byte_restore_rehearsal",
    "read_only_mongo_majority_capability",
    "licensed_native_gguf_turn",
    "active_gguf_tokenizer",
    "independent_bounded_reviewer",
    "protected_chat_request_response",
    "shared_mongo_writer_epoch_and_migration",
    "coherent_database_recovery",
    "physical_gpu_or_cpu_inference_pressure",
    "windows_wsl2_and_restart",
    "independent_signed_release_provenance",
)


class ReadinessError(host.LocalDockerError):
    """A local proof did not meet a required independent admission gate."""


def audit_readiness(mode: str, archive: Path, overlay_directory: Path, *,
                    expected_receipt_sha256: str,
                    restore_source: Path | None = None,
                    restored_directory: Path | None = None,
                    expected_restore_sha256: str | None = None,
                    root: Path = host.ROOT) -> dict[str, Any]:
    """No Docker creation, network request, file write or model execution."""
    if (restore_source is None) != (restored_directory is None):
        raise ReadinessError("restore source and destination must be paired")
    if (restore_source is None) != (expected_restore_sha256 is None):
        raise ReadinessError("independent restore receipt SHA must be paired")
    results: dict[str, dict[str, Any]] = {}

    def check(name: str, callback):
        try:
            result = callback()
            if not isinstance(result, dict):
                raise ReadinessError("independent verifier returned no structured receipt")
        except (host.LocalDockerError, ValueError, TypeError, OSError,
                KeyError, RuntimeError):
            results[name] = {"observed": False, "status": "unverified"}
        else:
            results[name] = {"observed": True, "status": "verified_for_stated_scope"}
        return results[name]["observed"]

    def binding():
        record = compose.verify_binding(
            mode, archive, overlay_directory,
            expected_receipt_sha256=expected_receipt_sha256, root=root,
        )
        if (record.get("actual_overlay_render_verified") is not True
                or record.get("all_four_image_ids_installed") is not True
                or record.get("guarded_chat_qualified") is not False):
            raise ReadinessError("offline image binding is not physically attested")
        return record

    admitted = check(GATES[0], binding)
    if admitted:
        check(GATES[1], lambda: device.preflight_device(mode, root=root))
        check(GATES[2], lambda: launch.attest_running_offline(
            mode, archive, overlay_directory,
            expected_receipt_sha256=expected_receipt_sha256, root=root,
        ))

        def backend():
            record = host.live_ai_status(mode, root)
            if record.get("observed") is not True:
                raise ReadinessError("backend local-only provider response unavailable")
            return record

        # Observation is useful but not a protected-chat security receipt.
        check(GATES[3], backend)
    else:
        for gate in GATES[1:4]:
            results[gate] = {"observed": False, "status": "prerequisite_unverified"}
    if restore_source is None:
        results[GATES[4]] = {"observed": False, "status": "no_restore_artifact_supplied"}
    else:
        def rehydrated():
            record = restore.verify_rehydration(
                restore_source, restored_directory,
                expected_receipt_sha256=expected_restore_sha256,
            )
            if (record.get("application_restore_qualified") is not False
                    or record.get("cross_store_snapshot_atomic") is not False):
                raise ReadinessError("byte-only rehearsal unexpectedly escalated recovery")
            return record
        check(GATES[4], rehydrated)
    # Majority journaling needs a real live backend and exact Docker
    # identities. It is an observation only: actor/writer fencing and
    # committed epochs must be independently proven at a later gate.
    if admitted and results[GATES[2]]["observed"] is True:
        check(GATES[5], lambda: mongo.inspect_mongo_majority(
            mode, archive, overlay_directory,
            expected_receipt_sha256=expected_receipt_sha256, root=root,
        ))
    else:
        results[GATES[5]] = {
            "observed": False, "status": "prerequisite_unverified",
        }
    # These gates require independent signers, real model/hardware and
    # authoritative in-app instrumentation. No mock, static test, process
    # availability or self-hashed JSON can confer that authority.
    for gate in GATES[6:]:
        results[gate] = {"observed": False,
                         "status": "requires_independent_physical_or_authority_evidence"}
    if set(results) != set(GATES):
        raise ReadinessError("offline readiness gate inventory incomplete")
    admitted_count = sum(
        1 for gate in GATES[:6] if results[gate]["observed"] is True
    )
    return {
        "schema": SCHEMA,
        "status": "deployment_readiness_blocked_not_release_authorized",
        "mode": mode,
        "gate_count": len(GATES),
        "bounded_local_observation_count": admitted_count,
        "gates": results,
        "source_tests_are_not_physical_evidence": True,
        "docker_daemon_state_mutated": False,
        "model_inference_executed_by_audit": False,
        "protected_chat_qualified": False,
        "database_recovery_qualified": False,
        "physical_gpu_offload_qualified": False,
        "release_authorized": False,
        "merge_authorized": False,
    }


__all__ = ["audit_readiness"]
