#!/usr/bin/env python3
"""Build exact-head evidence candidates for the first production gap batch.

This engine does not mutate EVID-04 bindings or masterplan gaps. It proves a
bounded set of release gaps against explicit contract markers plus focused
regression files, and emits digest-bound candidate EvidenceRef payloads that
may be reviewed for later governed binding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reconcile_p1_risk_evidence import (  # noqa: E402
    ADVERSARIAL,
    MASTER,
    P1_MAP,
    POLICY,
    REGISTRY,
    ROOT,
    RiskKind,
    derive_obligations,
)


_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
CATEGORY = "release_gap_closure"

COVERAGE: dict[tuple[str, str], dict[str, Any]] = {
    (
        "VOL-047",
        "bind installer to release provenance",
    ): {
        "sources": ["skeleton/release/lifecycle.py"],
        "tests": ["skeleton/testing/test_installer_lifecycle.py"],
        "markers": [
            "release_qualification_digest",
            "release-qualification-mismatch",
        ],
    },
    (
        "VOL-047",
        "materialize interruption checkpoints",
    ): {
        "sources": ["skeleton/release/lifecycle.py"],
        "tests": ["skeleton/testing/test_installer_lifecycle.py"],
        "markers": [
            "rollback_snapshot_digest",
            "preupdate-state-not-restored",
        ],
    },
    (
        "VOL-048",
        "define update compatibility graph",
    ): {
        "sources": ["skeleton/release/migration.py"],
        "tests": [
            "skeleton/testing/test_migration_rollback_compatibility.py",
        ],
        "markers": [
            "class MigrationPlan",
            "rollback_window_digest",
            "backward_read_succeeded",
        ],
    },
    (
        "VOL-048",
        "bind migrations to restore/rollback proof",
    ): {
        "sources": [
            "skeleton/release/migration.py",
            "skeleton/release/restore.py",
        ],
        "tests": [
            "skeleton/testing/test_migration_rollback_compatibility.py",
            "skeleton/testing/test_backup_restore_qualification.py",
        ],
        "markers": [
            "lifecycle_qualification_digest",
            "migration_compatibility_digest",
            "authoritative_state_digest",
        ],
    },
    (
        "VOL-050",
        "define ownership manifest from installer receipts",
    ): {
        "sources": ["skeleton/release/lifecycle.py"],
        "tests": ["skeleton/testing/test_installer_lifecycle.py"],
        "markers": [
            "ownership_policy_digest",
            "ownership-policy-drift",
        ],
    },
    (
        "VOL-050",
        "materialize residual scanner",
    ): {
        "sources": ["skeleton/release/lifecycle.py"],
        "tests": ["skeleton/testing/test_installer_lifecycle.py"],
        "markers": [
            "application_owned_residual_count",
            "unowned_critical_count",
        ],
    },
    (
        "VOL-060",
        "define release evidence bundle schema",
    ): {
        "sources": ["skeleton/release/qualification.py"],
        "tests": ["skeleton/testing/test_release_qualification.py"],
        "markers": [
            "class ReleaseQualificationDecision",
            "release_evidence_digest",
            "provenance_digest",
            "lifecycle_receipt_digests",
        ],
    },
    (
        "VOL-060",
        "bind installer/updater artifacts to release digest",
    ): {
        "sources": [
            "skeleton/release/qualification.py",
            "skeleton/release/lifecycle.py",
            "skeleton/release/migration.py",
        ],
        "tests": [
            "skeleton/testing/test_release_qualification.py",
            "skeleton/testing/test_installer_lifecycle.py",
            "skeleton/testing/test_migration_rollback_compatibility.py",
        ],
        "markers": [
            "installer_metadata_digest",
            "release_qualification_digest",
            "lifecycle_qualification_digest",
        ],
    },
    (
        "VOL-064",
        "define backup coverage manifest",
    ): {
        "sources": ["skeleton/release/restore.py"],
        "tests": [
            "skeleton/testing/test_backup_restore_qualification.py",
            "skeleton/testing/test_backup_restore_integration.py",
        ],
        "markers": [
            "class BackupManifest",
            "authoritative_state_digest",
            "backup_artifact_digest",
            "rebuild_recipe_digest",
        ],
    },
    (
        "VOL-065",
        "materialize full DR evidence bundle",
    ): {
        "sources": ["skeleton/release/disaster_recovery.py"],
        "tests": [
            "skeleton/testing/test_disaster_recovery_qualification.py",
        ],
        "markers": [
            "class DisasterRecoveryQualificationDecision",
            "backup_restore_qualification_digest",
            "failure_knowledge_qualification_digest",
            "drill_receipt_digests",
            "corrective_action_digests",
        ],
    },
    (
        "VOL-066",
        "bind postmortem actions into gap/risk ledgers",
    ): {
        "sources": ["skeleton/release/disaster_recovery.py"],
        "tests": [
            "skeleton/testing/test_disaster_recovery_qualification.py",
        ],
        "markers": [
            "class IncidentCorrectiveAction",
            "risk_obligation_id",
            "risk_obligation_digest",
            "failure_knowledge_ledger_digest",
            "failure_record_digest",
        ],
    },
    (
        "VOL-409",
        "generate release notices",
    ): {
        "sources": ["skeleton/release/attribution.py"],
        "tests": [
            "skeleton/testing/test_release_attribution.py",
            "tests/test_p1_release_attribution.py",
        ],
        "markers": [
            "render_release_notice",
            "notice_digest",
            "license_digest",
        ],
    },
}


class ReleaseGapEvidenceError(RuntimeError):
    """Release gap evidence inputs are malformed or incomplete."""


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseGapEvidenceError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise ReleaseGapEvidenceError(f"{path} must contain an object")
    return payload


def _digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return _digest_bytes(raw)


def build_release_gap_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise ReleaseGapEvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    paths = {
        "master_plan": root / MASTER,
        "p1_execution_map": root / P1_MAP,
        "adversarial_closure": root / ADVERSARIAL,
        "risk_policy": root / POLICY,
        "risk_registry": root / REGISTRY,
    }
    before = {name: _digest_file(path) for name, path in paths.items()}

    master = _load(paths["master_plan"])
    p1_map = _load(paths["p1_execution_map"])
    adversarial = _load(paths["adversarial_closure"])
    policy = _load(paths["risk_policy"])
    registry = _load(paths["risk_registry"])

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    gap_by_identity = {
        (
            obligation.source_ref.split(":", 1)[0],
            obligation.statement,
        ): obligation
        for obligation in obligations
        if obligation.kind is RiskKind.GAP
    }

    registry_rows = registry.get("records")
    if not isinstance(registry_rows, list):
        raise ReleaseGapEvidenceError("risk registry records must be a list")
    bound_ids = {
        str(row.get("obligation_id"))
        for row in registry_rows
        if isinstance(row, dict) and row.get("obligation_id")
    }

    rows: list[dict[str, Any]] = []
    for identity in sorted(COVERAGE):
        volume_key, statement = identity
        obligation = gap_by_identity.get(identity)
        if obligation is None:
            raise ReleaseGapEvidenceError(
                f"missing canonical gap obligation: {volume_key}: {statement}"
            )
        spec = COVERAGE[identity]
        source_paths = [root / item for item in spec["sources"]]
        test_paths = [root / item for item in spec["tests"]]
        for path in source_paths + test_paths:
            if not path.is_file():
                raise ReleaseGapEvidenceError(
                    f"evidence path is missing: {path.relative_to(root)}"
                )

        combined_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in source_paths
        )
        missing_markers = [
            marker
            for marker in spec["markers"]
            if marker not in combined_source
        ]
        if missing_markers:
            raise ReleaseGapEvidenceError(
                f"{volume_key}: missing contract markers: "
                + ",".join(missing_markers)
            )

        source_digests = {
            str(path.relative_to(root)): _digest_file(path)
            for path in source_paths
        }
        test_digests = {
            str(path.relative_to(root)): _digest_file(path)
            for path in test_paths
        }
        packet = {
            "volume_key": volume_key,
            "statement": statement,
            "obligation_id": obligation.obligation_id,
            "obligation_digest": obligation.obligation_digest,
            "source_ref": obligation.source_ref,
            "expected_head": expected_head,
            "source_digests": source_digests,
            "test_digests": test_digests,
            "verified_contract_markers": list(spec["markers"]),
            "binding_present": obligation.obligation_id in bound_ids,
            "non_authoritative": True,
            "creates_binding": False,
            "clears_masterplan_gap": False,
        }
        packet["packet_digest"] = _canonical_digest(packet)
        packet["candidate_evidence_ref"] = {
            "source": (
                "p1:release-gap-batch1:"
                f"{obligation.obligation_id}:{expected_head}"
            ),
            "digest": packet["packet_digest"],
            "category": CATEGORY,
        }
        rows.append(packet)

    ids = [row["obligation_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ReleaseGapEvidenceError("duplicate covered obligation identity")
    if len(rows) != 12:
        raise ReleaseGapEvidenceError(
            f"expected 12 covered gaps, got {len(rows)}"
        )

    after = {name: _digest_file(path) for name, path in paths.items()}
    if before != after:
        raise ReleaseGapEvidenceError(
            "canonical risk/masterplan sources changed during evidence build"
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-release-gap-evidence-batch1-v1",
        "expected_head": expected_head,
        "category": CATEGORY,
        "covered_gap_count": len(rows),
        "covered_volume_count": len(
            {row["volume_key"] for row in rows}
        ),
        "already_bound_count": sum(
            1 for row in rows if row["binding_present"]
        ),
        "candidate_binding_count": sum(
            1 for row in rows if not row["binding_present"]
        ),
        "non_authoritative": True,
        "creates_bindings": False,
        "clears_masterplan_gaps": False,
        "source_digests": before,
        "records": rows,
    }
    report["report_digest"] = _canonical_digest(report)
    return report


def _canonical_text(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_release_gap_evidence(
            ROOT,
            expected_head=args.expected_head,
        )
    except ReleaseGapEvidenceError as exc:
        print(
            f"P1 release gap evidence: rejected: {exc}",
            file=sys.stderr,
        )
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_canonical_text(report), encoding="utf-8")

    if args.print_summary:
        print(
            json.dumps(
                {
                    "expected_head": report["expected_head"],
                    "covered_gap_count": report["covered_gap_count"],
                    "covered_volume_count": report["covered_volume_count"],
                    "already_bound_count": report["already_bound_count"],
                    "candidate_binding_count": report["candidate_binding_count"],
                    "report_digest": report["report_digest"],
                },
                indent=2,
                sort_keys=True,
            )
        )

    print(
        "P1 release gap evidence: OK "
        f"({report['covered_gap_count']} gaps across "
        f"{report['covered_volume_count']} volumes; "
        f"{report['candidate_binding_count']} binding candidates)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
