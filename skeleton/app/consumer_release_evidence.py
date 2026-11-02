"""Fail-closed consumer first-run release hold across real offline game replay.

This is a live source-level integration gate, not a self-signed release report.
The caller must provide independent artifact pins. The gate replays the
installed game and its private save, or the pinned multi-game cohort, before
returning an explicitly blocked consumer release decision. No file is written.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import re
import sys
from pathlib import Path
from typing import Sequence

from skeleton.app.consumer_first_run_readiness import (
    RELEASE_HOLDS, inspect_consumer_first_run,
)
from skeleton.app.consumer_first_run_cohort import inspect_pinned_consumer_cohort

SCHEMA = "skeleton.app.consumer_release_evidence.v1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_PROJECT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_REQUIRED_FALSE = (
    "release_certified", "native_device_qualified", "native_godot_executed",
    "windows_laptop_qualified", "installer_qualified",
    "guarded_local_ai_qualified", "package_signed", "rights_certified",
    "persistent_rollback_protection",
)
_REQUIRED_TRUE = (
    "read_only", "root_and_evidence_inodes_stable",
    "nested_asset_inode_inventory_attested",
    "nested_asset_inode_snapshots_equal",
)


class ConsumerReleaseEvidenceError(ValueError):
    """Canonical replay evidence was incomplete, contradictory or untrusted."""


def _sha(value: object, label: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ConsumerReleaseEvidenceError(
            "independent " + label + " SHA-256 pin must be canonical"
        )
    return value


def _validate_evidence(evidence: object, *, cohort: bool) -> dict[str, object]:
    if type(evidence) is not dict:
        raise ConsumerReleaseEvidenceError("canonical replay evidence is not a record")
    schema = (
        "skeleton.app.consumer_first_run_cohort.v1" if cohort
        else "skeleton.app.consumer_first_run_evidence.v1"
    )
    if evidence.get("schema") != schema:
        raise ConsumerReleaseEvidenceError("canonical replay schema mismatch")
    if (any(evidence.get(key) is not False for key in _REQUIRED_FALSE)
            or any(evidence.get(key) is not True for key in _REQUIRED_TRUE)
            or type(evidence.get("files_published")) is not int
            or evidence["files_published"] != 0
            or type(evidence.get("release_holds")) is not list
            or evidence["release_holds"] != list(RELEASE_HOLDS)):
        raise ConsumerReleaseEvidenceError(
            "canonical replay cannot authorize a consumer release"
        )
    if cohort:
        games = evidence.get("games")
        count = evidence.get("game_count")
        if (type(count) is not int or not 2 <= count <= 8
                or type(games) is not list or len(games) != count
                or evidence.get("private_jobfile_inode_attested") is not True
                or evidence.get("all_installed_games_and_private_saves_reexecuted") is not True
                or type(evidence.get("canonical_cohort_inspections")) is not int
                or evidence["canonical_cohort_inspections"] != 2
                or type(evidence.get("source_level_replay_passes_per_game")) is not int
                or evidence["source_level_replay_passes_per_game"] != 2):
            raise ConsumerReleaseEvidenceError("pinned consumer cohort replay incomplete")
        project_ids: set[str] = set()
        for index, game in enumerate(games):
            if (type(game) is not dict or game.get("index") != index
                    or type(game.get("project_id")) is not str
                    or _PROJECT.fullmatch(game["project_id"]) is None
                    or game["project_id"] in project_ids
                    or type(game.get("source_level_replay_passes")) is not int
                    or game["source_level_replay_passes"] != 2
                    or game.get("release_certified") is not False):
                raise ConsumerReleaseEvidenceError("consumer cohort game identity invalid")
            for key in (
                "world_digest", "replay_digest", "manifest_sha256",
                "archive_sha256", "save_sha256", "receipt_sha256",
                "installed_tree_snapshot_sha256",
            ):
                _sha(game.get(key), key)
            project_ids.add(game["project_id"])
        _sha(evidence.get("independent_jobs_sha256"), "jobs")
        _sha(evidence.get("independent_summary_sha256"), "summary")
    else:
        if (type(evidence.get("source_level_replay_passes")) is not int
                or evidence["source_level_replay_passes"] != 2
                or evidence.get("installed_game_and_private_save_reexecuted") is not True
                or type(evidence.get("project_id")) is not str
                or _PROJECT.fullmatch(evidence["project_id"]) is None
                or type(evidence.get("action_count")) is not int
                or not 1 <= evidence["action_count"] <= 64):
            raise ConsumerReleaseEvidenceError("single-game source replay incomplete")
        for key in (
            "world_digest", "replay_digest", "manifest_sha256",
            "archive_sha256", "save_sha256", "receipt_sha256",
            "installed_tree_snapshot_sha256",
        ):
            _sha(evidence.get(key), key)
    return evidence


def _report(evidence: dict[str, object], *, mode: str) -> dict[str, object]:
    """Digest only verified in-memory evidence; never call this a signature."""
    raw = json.dumps(
        evidence, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    if len(raw) > 256 * 1024:
        raise ConsumerReleaseEvidenceError("consumer evidence size budget exceeded")
    return {
        "schema": SCHEMA,
        "mode": mode,
        "status": "consumer_release_blocked_source_replay_observed",
        "source_level_evidence_sha256": sha256(raw).hexdigest(),
        "source_level_evidence": evidence,
        "independent_pin_required": True,
        "files_published": 0,
        "read_only": True,
        "device_evidence_verified": False,
        "installer_evidence_verified": False,
        "signed_package_chain_verified": False,
        "rights_evidence_verified": False,
        "guarded_local_ai_verified": False,
        "security_gates_verified": False,
        "release_certified": False,
        "release_holds": list(RELEASE_HOLDS),
    }


def inspect_single_consumer_release_hold(
    installed: str | Path, archive: str | Path,
    save: str | Path, receipt: str | Path, *,
    expected_manifest_sha256: str, expected_archive_sha256: str,
    expected_save_sha256: str, expected_receipt_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Reexecute an installed playable game and retain all release holds."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    pins = {
        "expected_manifest_sha256": _sha(expected_manifest_sha256, "manifest"),
        "expected_archive_sha256": _sha(expected_archive_sha256, "archive"),
        "expected_save_sha256": _sha(expected_save_sha256, "save"),
        "expected_receipt_sha256": _sha(expected_receipt_sha256, "receipt"),
    }
    evidence = inspect_consumer_first_run(
        installed, archive, save, receipt, authorized=True, **pins,
    )
    return _report(_validate_evidence(evidence, cohort=False), mode="single")


def inspect_cohort_consumer_release_hold(
    jobs_file: str | Path, summary: str | Path, *,
    expected_jobs_sha256: str, expected_summary_sha256: str,
    authorized: bool, verify_original_sources: bool = False,
) -> dict[str, object]:
    """Replay 2-8 original games under private pinned jobfile custody."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if type(verify_original_sources) is not bool:
        raise ConsumerReleaseEvidenceError("source verification flag must be boolean")
    evidence = inspect_pinned_consumer_cohort(
        jobs_file, expected_jobs_sha256=_sha(expected_jobs_sha256, "jobs"),
        summary=summary,
        expected_summary_sha256=_sha(expected_summary_sha256, "summary"),
        authorized=True, verify_original_sources=verify_original_sources,
    )
    return _report(_validate_evidence(evidence, cohort=True), mode="cohort")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app consumer-release-evidence",
        description="Live source-level first-run replay; never release approval",
    )
    parser.add_argument("--mode", choices=("single", "cohort"), required=True)
    for name in (
        "installed", "archive", "save", "receipt",
        "expected-manifest-sha256", "expected-archive-sha256",
        "expected-save-sha256", "expected-receipt-sha256",
        "jobs-file", "summary", "expected-jobs-sha256",
        "expected-summary-sha256",
    ):
        parser.add_argument("--" + name)
    parser.add_argument("--verify-original-sources", action="store_true")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    single = (
        args.installed, args.archive, args.save, args.receipt,
        args.expected_manifest_sha256, args.expected_archive_sha256,
        args.expected_save_sha256, args.expected_receipt_sha256,
    )
    cohort = (
        args.jobs_file, args.summary, args.expected_jobs_sha256,
        args.expected_summary_sha256,
    )
    try:
        if args.mode == "single":
            if (any(x is None for x in single)
                    or any(x is not None for x in cohort)
                    or args.verify_original_sources):
                raise ConsumerReleaseEvidenceError("single mode requires exactly four paths and four pins")
            report = inspect_single_consumer_release_hold(
                args.installed, args.archive, args.save, args.receipt,
                expected_manifest_sha256=args.expected_manifest_sha256,
                expected_archive_sha256=args.expected_archive_sha256,
                expected_save_sha256=args.expected_save_sha256,
                expected_receipt_sha256=args.expected_receipt_sha256,
                authorized=args.trusted_local_operator,
            )
        else:
            if any(x is None for x in cohort) or any(x is not None for x in single):
                raise ConsumerReleaseEvidenceError("cohort mode requires only jobfile, summary and pins")
            report = inspect_cohort_consumer_release_hold(
                args.jobs_file, args.summary,
                expected_jobs_sha256=args.expected_jobs_sha256,
                expected_summary_sha256=args.expected_summary_sha256,
                authorized=args.trusted_local_operator,
                verify_original_sources=args.verify_original_sources,
            )
    except (PermissionError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "ConsumerReleaseEvidenceError",
    "inspect_single_consumer_release_hold",
    "inspect_cohort_consumer_release_hold", "main",
]
