"""Read-only, dual-service Docker writer policy; never activates writers.

Inspect the same exact Docker Compose deployment from the backend and Jeeves
engine. An authenticated local Mongo primary and real, explicit journaled
majority policy must agree with independently checked read-only epoch
preflight fingerprint. Receipt fields are strictly bounded and allowlisted.

This observation does not start containers, grant actor epochs, reconcile
writers, execute queries against user collections, or authorize protected chat.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts import local_ai_docker as host
from scripts.local_ai_runtime_attestation import attest_runtime

SCHEMA = "skeleton.local-ai.docker.dual-writer-journal-policy.v1"
SERVER_SCHEMA = "skeleton.local-ai.mongo-writer-journal-policy.v1"
SERVER_STATUS = "real_readonly_majority_journal_capability_not_writer_registry"
_FIELDS = {
    "ok", "role", "schema", "status", "primary_fingerprint_sha256",
    "configured_members", "data_bearing_voters",
    "healthy_data_bearing_voters",
    "exact_config_and_status_members_verified",
    "single_primary_verified", "primary_identity_stable_across_probe",
    "explicit_majority_default", "explicit_majority_journal_policy",
    "database_documents_read", "database_writes_performed",
    "production_writer_registry_complete", "actor_migration_qualified",
    "protected_chat_qualified", "release_authorized",
}
_TRUE = {
    "ok", "exact_config_and_status_members_verified",
    "single_primary_verified", "primary_identity_stable_across_probe",
    "explicit_majority_default", "explicit_majority_journal_policy",
}
_FALSE = {
    "database_documents_read", "database_writes_performed",
    "production_writer_registry_complete", "actor_migration_qualified",
    "protected_chat_qualified", "release_authorized",
}
_COUNTERS = ("configured_members", "data_bearing_voters",
             "healthy_data_bearing_voters")


class DualWriterPolicyError(host.LocalDockerError):
    """Real Docker cross-process Mongo journal policy unavailable."""


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    found = {}
    for key, value in pairs:
        if key in found:
            raise DualWriterPolicyError("duplicate Docker writer policy field")
        found[key] = value
    return found


def _nonfinite(_: str) -> None:
    raise DualWriterPolicyError("nonfinite Docker writer policy field")


def _receipt(raw: object, role: str, primary_sha256: str) -> dict[str, object]:
    """Never reflect untrusted or raw Mongo data back to a user."""
    if (role not in ("backend", "engine")
            or not isinstance(primary_sha256, str)
            or re.fullmatch(r"[a-f0-9]{64}", primary_sha256) is None
            or not isinstance(raw, str)
            or not 0 < len(raw) <= 4096):
        raise DualWriterPolicyError("bounded writer policy receipt unavailable")
    try:
        response = json.loads(raw, object_pairs_hook=_unique,
                              parse_constant=_nonfinite)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise DualWriterPolicyError("writer policy receipt is not valid JSON") from None
    if (not isinstance(response, dict)
            or set(response) != _FIELDS
            or response.get("schema") != SERVER_SCHEMA
            or response.get("status") != SERVER_STATUS
            or response.get("role") != role
            or response.get("primary_fingerprint_sha256") != primary_sha256
            or any(response.get(k) is not True for k in _TRUE)
            or any(response.get(k) is not False for k in _FALSE)):
        raise DualWriterPolicyError("writer policy contract or shared primary invalid")
    values = [response.get(k) for k in _COUNTERS]
    if (any(type(n) is not int for n in values)
            or not 3 <= values[1] <= values[0] <= 31
            or not values[1] // 2 + 1 <= values[2] <= values[1]):
        raise DualWriterPolicyError("writer policy voting counts invalid")
    # Only fields needed for the operator summary; never echo raw replies.
    return {
        "role": role,
        "configured_members": values[0],
        "data_bearing_voters": values[1],
        "healthy_data_bearing_voters": values[2],
        "policy_verified": True,
    }


def inspect_dual_writer_policy(mode: str, root: Path = host.ROOT) -> dict[str, object]:
    """Examine both actual running Docker services without any state changes."""
    try:
        attest_runtime(mode, root)
        primary = host.attest_shared_epoch_capability(mode, root)
        if (primary.get("engine_read") is not True
                or primary.get("backend_read") is not True
                or primary.get("writer_epoch_bound") is not False
                or primary.get("actor_migration_complete") is not False
                or primary.get("guarded_chat_qualified") is not False):
            raise DualWriterPolicyError("independent Mongo epoch preflight incomplete")
        fingerprint = primary.get("primary_fingerprint_sha256")
        if (not isinstance(fingerprint, str)
                or not re.fullmatch(r"[a-f0-9]{64}", fingerprint)):
            raise DualWriterPolicyError("independent primary fingerprint unavailable")
        prefix = host.compose_command(mode, root)
        proofs = {}
        for role, service in (("engine", "skeleton"), ("backend", "backend")):
            raw = host._run([
                *prefix, "exec", "-T", service, "python", "-m",
                "skeleton.persistence.docker_epoch_writer_policy",
                "--role", role,
            ], root=root, capture=True)
            proofs[role] = _receipt(raw, role, fingerprint)
        if (proofs["engine"]["configured_members"]
                != proofs["backend"]["configured_members"]
                or proofs["engine"]["data_bearing_voters"]
                != proofs["backend"]["data_bearing_voters"]):
            raise DualWriterPolicyError("backend/engine Mongo voter configuration drift")
        return {
            "schema": SCHEMA,
            "status": "read_only_writer_policy_both_services_not_epoch_enrollment",
            "mode": mode,
            "primary_fingerprint_sha256": fingerprint,
            "engine_policy_verified": True,
            "backend_policy_verified": True,
            "configured_members": proofs["engine"]["configured_members"],
            "data_bearing_voters": proofs["engine"]["data_bearing_voters"],
            "minimum_healthy_voters_observed": min(
                proofs["engine"]["healthy_data_bearing_voters"],
                proofs["backend"]["healthy_data_bearing_voters"],
            ),
            "real_database_documents_read": False,
            "real_database_writes": False,
            "backend_epoch_bound": False,
            "engine_epoch_bound": False,
            "external_writer_quiescence_verified": False,
            "actor_migration_qualified": False,
            "protected_jeeves_chat_qualified": False,
            "coherent_application_recovery_qualified": False,
            "merge_authorized": False,
            "release_authorized": False,
        }
    except DualWriterPolicyError:
        raise
    except Exception:
        # Docker and PyMongo exceptions may include private connection details.
        raise DualWriterPolicyError(
            "live dual-service Mongo writer policy unavailable"
        ) from None


__all__ = ["DualWriterPolicyError", "_receipt", "inspect_dual_writer_policy"]
