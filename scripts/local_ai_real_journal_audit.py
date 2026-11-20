"""Read-only physical backend + Jeeves engine Mongo journal census.

Uses only the canonical, existing local Docker services, their already
authenticated private Mongo clients and strict no-write source probes.
A separate process can prove service connection capability; it cannot
prove that the long-running application process currently holds a writer
epoch, has migrated all actors or excludes external application writers.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from scripts import local_ai_docker as host
from scripts.local_ai_runtime_attestation import attest_runtime


SCHEMA = "skeleton.local-ai.docker.dual-service-real-journal-audit.v1"
SOURCE = "skeleton.local-ai.mongo-real-dual-writer-journal-probe.v1"
FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z")
REPLICA = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
REQUIRED = frozenset({
    "schema", "ok", "role", "status", "replica_set",
    "primary_fingerprint_sha256",
    "configured_members", "data_bearing_voters", "healthy_data_bearing_voters",
    "exact_config_and_status_members_verified",
    "primary_identity_stable_across_probe",
    "linearizable_read_before_and_after", "explicit_majority_default",
    "explicit_majority_journal_policy",
    "database_documents_read", "database_writes_performed",
    "docker_state_modified", "production_writers_enrolled",
    "external_writer_registry_qualified", "actor_migration_qualified",
    "protected_chat_qualified", "release_authorized",
})
TRUE_FIELDS = frozenset({
    "ok", "exact_config_and_status_members_verified",
    "primary_identity_stable_across_probe", "linearizable_read_before_and_after",
    "explicit_majority_default", "explicit_majority_journal_policy",
})
FALSE_FIELDS = frozenset({
    "database_documents_read", "database_writes_performed",
    "docker_state_modified", "production_writers_enrolled",
    "external_writer_registry_qualified", "actor_migration_qualified",
    "protected_chat_qualified", "release_authorized",
})


class RealJournalAuditError(host.LocalDockerError):
    """Real Docker writer-journal capability cannot be safely qualified."""


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise RealJournalAuditError("duplicate physical Mongo receipt field")
        out[key] = value
    return out


def _invalid_constant(value: str) -> None:
    raise RealJournalAuditError("nonfinite physical Mongo receipt field")


def decode_role_receipt(raw: object, role: str) -> dict[str, Any]:
    if (role not in ("backend", "engine")
            or not isinstance(raw, str) or not 0 < len(raw) <= 8192):
        raise RealJournalAuditError("bounded physical journal evidence missing")
    try:
        record = json.loads(raw, object_pairs_hook=_unique,
                            parse_constant=_invalid_constant)
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise RealJournalAuditError("physical journal JSON invalid") from None
    if (not isinstance(record, dict) or set(record) != REQUIRED
            or record.get("schema") != SOURCE
            or record.get("role") != role
            or record.get("status") !=
                "real_dual_service_read_only_journal_not_writer_custody"
            or any(record.get(field) is not True for field in TRUE_FIELDS)
            or any(record.get(field) is not False for field in FALSE_FIELDS)
            or not isinstance(record.get("replica_set"), str)
            or not REPLICA.fullmatch(record["replica_set"])
            or not isinstance(record.get("primary_fingerprint_sha256"), str)
            or not FINGERPRINT.fullmatch(record["primary_fingerprint_sha256"])):
        raise RealJournalAuditError(
            "physical Mongo journal evidence violates fixed schema"
        )
    n, voters, healthy = (record.get(name) for name in (
        "configured_members", "data_bearing_voters",
        "healthy_data_bearing_voters",
    ))
    if (any(type(x) is not int for x in (n, voters, healthy))
            or not 3 <= voters <= n <= 31
            or not voters // 2 + 1 <= healthy <= voters):
        raise RealJournalAuditError("physical Mongo healthy quorum invalid")
    return record


def audit_real_writer_journal(
    mode: str, *, root: Path = host.ROOT,
) -> dict[str, object]:
    """Run separate real read-only probes inside both existing services."""
    try:
        # The canonical read-only runtime gate is a prerequisite; this command
        # does NOT create containers, write volumes, enable flags or pull images.
        attest_runtime(mode, root)
        first = host.attest_shared_epoch_capability(mode, root)
        if (first.get("writer_epoch_bound") is not False
                or first.get("actor_migration_complete") is not False
                or first.get("guarded_chat_qualified") is not False):
            raise RealJournalAuditError("source capability promoted into writer custody")
        prefix = host.compose_command(mode, root)
        rows: dict[str, dict[str, Any]] = {}
        for role, service in (("engine", "skeleton"), ("backend", "backend")):
            raw = host._run([
                *prefix, "exec", "-T", service, "python", "-m",
                "skeleton.persistence.docker_epoch_writer_probe",
                "--role", role,
            ], root=root, capture=True)
            rows[role] = decode_role_receipt(raw, role)
        engine, backend = rows["engine"], rows["backend"]
        if (engine["replica_set"] != backend["replica_set"]
                or engine["primary_fingerprint_sha256"]
                    != backend["primary_fingerprint_sha256"]
                or engine["configured_members"] != backend["configured_members"]
                or engine["data_bearing_voters"] != backend["data_bearing_voters"]
                or engine["primary_fingerprint_sha256"]
                    != first.get("primary_fingerprint_sha256")
                or engine["replica_set"] != first.get("replica_set")):
            raise RealJournalAuditError(
                "backend and engine do not share same admitted replica"
            )
        second = host.attest_shared_epoch_capability(mode, root)
        if first != second:
            raise RealJournalAuditError(
                "physical Docker epoch primary changed during writer audit"
            )
        attest_runtime(mode, root)
        return {
            "schema": SCHEMA,
            "status": "physical_read_only_two_service_journal_not_writer_fenced",
            "mode": mode,
            "primary_fingerprint_sha256":
                engine["primary_fingerprint_sha256"],
            "replica_set": engine["replica_set"],
            "configured_members": engine["configured_members"],
            "data_bearing_voters": engine["data_bearing_voters"],
            "minimum_healthy_voters": min(
                engine["healthy_data_bearing_voters"],
                backend["healthy_data_bearing_voters"],
            ),
            "backend_service_authenticated_policy": True,
            "engine_service_authenticated_policy": True,
            "same_primary_verified_before_and_after": True,
            "separate_linearizable_reads_observed": True,
            "explicit_journaled_majority_policy_observed": True,
            "production_writer_epoch_bound": False,
            "external_writer_registry_qualified": False,
            "actor_migration_complete": False,
            "production_database_writes_performed": False,
            "docker_state_modified": False,
            "protected_chat_qualified": False,
            "coherent_cross_store_recovery_qualified": False,
            "release_authorized": False,
        }
    except RealJournalAuditError:
        raise
    except Exception:
        raise RealJournalAuditError(
            "actual two-service Mongo journal read-only audit unavailable"
        ) from None


__all__ = [
    "RealJournalAuditError", "decode_role_receipt", "audit_real_writer_journal",
]
