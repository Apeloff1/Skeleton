"""Read-only multi-game consumer first-run evidence from independently pinned jobs.

This is a source-level acceptance boundary, not native-device, installer,
marketplace, rights, signing, or guarded-local-model certification. It never
publishes artifacts, repairs custody, or modifies a private save.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from skeleton.app.consumer_first_run_readiness import (
    RELEASE_HOLDS, _custody as _consumer_input_custody,
    inspect_consumer_first_run,
)
from skeleton.app.offline_delivery_assurance import _save_identity, _source_identity
from skeleton.app.installed_tree_custody import (
    installed_tree_snapshot_digest, snapshot_installed_tree,
)
from skeleton.app.offline_first_playable_batch import (
    DeliveryJob, _check_jobs, _delivered_custody,
    inspect_first_playable_delivery_batch,
)
from skeleton.app.offline_first_playable_jobfile import (
    _pin, read_pinned_jobs,
)

SCHEMA = "skeleton.app.consumer_first_run_cohort.v1"


class ConsumerFirstRunCohortError(ValueError):
    """A pinned first-run cohort could not be independently reexecuted."""


def _nested_snapshots(
    jobs: tuple[DeliveryJob, ...], *, original_sources: bool = False,
) -> tuple[tuple, ...]:
    """Capture all 2-8 installed trees, including nested directory/file inodes.

    The canonical delivery custody check covers roots and evidence files,
    not every installed asset. Keep a bounded inventory for the *entire*
    cohort across each game's replay and the final cohort verification.
    """
    return tuple(snapshot_installed_tree(
        job.source if original_sources else job.install
    ) for job in jobs)


def _require_nested_custody(
    jobs: tuple[DeliveryJob, ...], expected: tuple[tuple, ...], *,
    original_sources: bool = False,
) -> None:
    if _nested_snapshots(jobs, original_sources=original_sources) != expected:
        label = "original source" if original_sources else "installed game"
        raise ConsumerFirstRunCohortError(
            "nested " + label + " inode changed during cross-game replay"
        )


def inspect_consumer_first_run_cohort(
    jobs: Sequence[DeliveryJob], summary: str | Path, *,
    expected_summary_sha256: str, authorized: bool,
    verify_original_sources: bool = False,
) -> dict[str, object]:
    """Replay all installed games and their cohort receipt across custody barriers.

    All hashes must come from outside the artifacts being inspected. The
    first and final cohort inspections independently reexecute each game;
    each individual consumer inspection also performs two replay passes.
    No filesystem lock, persistent anti-rollback claim, or device evidence
    is produced by this function.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ConsumerFirstRunCohortError("POSIX nofollow custody required")
    if type(verify_original_sources) is not bool:
        raise ConsumerFirstRunCohortError(
            "original source verification flag must be boolean"
        )
    pin = _pin(expected_summary_sha256)
    checked = _check_jobs(jobs, summary, inspect=True)
    before = _delivered_custody(checked)
    summary_before = _save_identity(summary)
    summary_parent_before = _source_identity(Path(summary).expanduser().absolute().parent)
    nested_before = _nested_snapshots(checked)
    nested_digests = tuple(
        installed_tree_snapshot_digest(snapshot) for snapshot in nested_before
    )
    # Source trees are optional: an installed game must remain inspectable
    # after its authoring source is intentionally retired. When explicitly
    # requested, bind every original asset inode across the whole cohort.
    source_nested_before = (
        _nested_snapshots(checked, original_sources=True)
        if verify_original_sources else None
    )
    # A later game may move an earlier game's *same file inode* into a
    # different parent directory. File and root identities alone cannot
    # detect that path-custody substitution across consumer games.
    input_parents_before = tuple(
        _consumer_input_custody(
            job.install, job.archive, job.save, job.receipt,
        ) for job in checked
    )

    def require_all_nested_custody() -> None:
        if _source_identity(
            Path(summary).expanduser().absolute().parent
        ) != summary_parent_before:
            raise ConsumerFirstRunCohortError(
                "cohort summary parent inode changed during cross-game replay"
            )
        if tuple(
            _consumer_input_custody(
                job.install, job.archive, job.save, job.receipt,
            ) for job in checked
        ) != input_parents_before:
            raise ConsumerFirstRunCohortError(
                "consumer evidence parent inode changed during cross-game replay"
            )
        _require_nested_custody(checked, nested_before)
        if source_nested_before is not None:
            _require_nested_custody(
                checked, source_nested_before, original_sources=True,
            )

    first = inspect_first_playable_delivery_batch(
        checked, summary, expected_summary_sha256=pin, authorized=True,
        verify_original_sources=verify_original_sources,
    )
    if (type(first) is not dict
            or first.get("all_live_games_reexecuted") is not True
            or first.get("receipt_integrity_verified") is not True
            or first.get("read_only") is not True
            or first.get("release_certified") is not False
            or first.get("native_device_qualified") is not False
            or first.get("independent_summary_sha256") != pin
            or first.get("original_sources_reverified") is not verify_original_sources
            or type(first.get("games")) is not list
            or len(first["games"]) != len(checked)):
        raise ConsumerFirstRunCohortError("canonical cohort replay evidence invalid")
    if (_delivered_custody(checked) != before
            or _save_identity(summary) != summary_before):
        raise ConsumerFirstRunCohortError("cohort custody changed after first replay")
    require_all_nested_custody()

    games: list[dict[str, object]] = []
    for index, (job, stored) in enumerate(zip(
        checked, first["games"], strict=True,
    )):
        if type(stored) is not dict:
            raise ConsumerFirstRunCohortError("canonical game record invalid")
        observed = inspect_consumer_first_run(
            job.install, job.archive, job.save, job.receipt,
            expected_manifest_sha256=job.manifest_sha256,
            expected_archive_sha256=job.archive_sha256,
            expected_save_sha256=job.save_sha256,
            expected_receipt_sha256=job.receipt_sha256,
            authorized=True,
        )
        if (type(observed) is not dict
                or observed.get("project_id") != stored.get("project_id")
                or observed.get("world_digest") != stored.get("world_digest")
                or observed.get("replay_digest") != stored.get("replay_digest")
                or observed.get("action_count") != len(job.moves)
                or observed.get("action_count") != stored.get("action_count")
                or observed.get("manifest_sha256") != job.manifest_sha256
                or observed.get("archive_sha256") != job.archive_sha256
                or observed.get("save_sha256") != job.save_sha256
                or observed.get("receipt_sha256") != job.receipt_sha256
                or observed.get("source_level_replay_passes") != 2
                or observed.get("all_input_inodes_stable_during_inspection") is not False
                or observed.get("root_and_evidence_inodes_stable_during_inspection") is not True
                or observed.get("nested_asset_inode_inventory_attested") is not True
                or observed.get("nested_asset_inode_snapshots_equal") is not True
                or type(observed.get("installed_tree_snapshot_sha256")) is not str
                or len(observed["installed_tree_snapshot_sha256"]) != 64
                or observed["installed_tree_snapshot_sha256"] != nested_digests[index]
                or observed.get("read_only") is not True
                or observed.get("release_certified") is not False
                or observed.get("native_device_qualified") is not False
                or observed.get("package_signed") is not False
                or observed.get("rights_certified") is not False):
            raise ConsumerFirstRunCohortError(
                "consumer replay diverged from independently pinned cohort"
            )
        games.append({
            "index": index,
            "project_id": observed["project_id"],
            "world_digest": observed["world_digest"],
            "replay_digest": observed["replay_digest"],
            "action_count": observed["action_count"],
            "manifest_sha256": job.manifest_sha256,
            "archive_sha256": job.archive_sha256,
            "save_sha256": job.save_sha256,
            "receipt_sha256": job.receipt_sha256,
            "source_level_replay_passes": 2,
            "installed_tree_snapshot_sha256": nested_digests[index],
            "release_certified": False,
        })
        # Run the specific parent/nested custody checks first so a rejection
        # names the exact substitution; the aggregate check still follows.
        require_all_nested_custody()
        if (_delivered_custody(checked) != before
                or _save_identity(summary) != summary_before):
            raise ConsumerFirstRunCohortError(
                "another installed game or summary changed during replay"
            )

    # Reinspect the complete canonical cohort after the final consumer game;
    # a later replay must not mask tampering with an earlier installed game.
    second = inspect_first_playable_delivery_batch(
        checked, summary, expected_summary_sha256=pin, authorized=True,
        verify_original_sources=verify_original_sources,
    )
    if (second != first
            or _delivered_custody(checked) != before
            or _save_identity(summary) != summary_before
            or len({game["project_id"] for game in games}) != len(games)):
        raise ConsumerFirstRunCohortError(
            "cohort changed across final cross-game replay barrier"
        )
    require_all_nested_custody()
    return {
        "schema": SCHEMA,
        "status": "consumer_source_level_cohort_replayed_release_blocked",
        "game_count": len(games),
        "games": games,
        "independent_summary_sha256": pin,
        "source_level_replay_passes_per_game": 2,
        "canonical_cohort_inspections": 2,
        "original_sources_reverified": verify_original_sources,
        "all_installed_games_and_private_saves_reexecuted": True,
        # Direct in-memory cohort inspection cannot attest a private jobfile,
        # and source-root custody is not a nested asset inode inventory.
        "cohort_and_job_inodes_stable": False,
        "root_and_evidence_inodes_stable": True,
        "nested_asset_inode_inventory_attested": True,
        "nested_asset_inode_snapshots_equal": True,
        "all_games_nested_inodes_checked_after_each_replay": True,
        "all_game_evidence_parent_inodes_checked_after_each_replay": True,
        "summary_parent_inode_checked_after_each_replay": True,
        "original_source_nested_inode_inventory_attested": verify_original_sources,
        "original_source_nested_inode_snapshots_equal": verify_original_sources,
        "private_jobfile_inode_attested": False,
        "read_only": True,
        "files_published": 0,
        "native_device_qualified": False,
        "native_godot_executed": False,
        "windows_laptop_qualified": False,
        "installer_qualified": False,
        "guarded_local_ai_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "persistent_rollback_protection": False,
        "release_certified": False,
        "release_holds": list(RELEASE_HOLDS),
    }


def inspect_pinned_consumer_cohort(
    jobs_file: str | Path, *, expected_jobs_sha256: str,
    summary: str | Path, expected_summary_sha256: str,
    authorized: bool, verify_original_sources: bool = False,
) -> dict[str, object]:
    """Bind the read-only acceptance run to a separately pinned private jobfile."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    jobs, identity = read_pinned_jobs(
        jobs_file, expected_sha256=expected_jobs_sha256,
        summary=summary, mode="inspect", authorized=True,
    )
    try:
        result = inspect_consumer_first_run_cohort(
            jobs, summary, expected_summary_sha256=expected_summary_sha256,
            authorized=True,
            verify_original_sources=verify_original_sources,
        )
    finally:
        again, final_identity = read_pinned_jobs(
            jobs_file, expected_sha256=expected_jobs_sha256,
            summary=summary, mode="inspect", authorized=True,
        )
        if jobs != again or identity != final_identity:
            raise ConsumerFirstRunCohortError(
                "private jobfile inode or bytes changed during consumer replay"
            )
    return {
        **result,
        "independent_jobs_sha256": _pin(expected_jobs_sha256),
        "private_jobfile_inode_attested": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app consumer-first-run-cohort",
        description="Read-only pinned 2-8 game first-run acceptance; release blocked",
    )
    parser.add_argument("--jobs-file", required=True)
    parser.add_argument("--expected-jobs-sha256", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--expected-summary-sha256", required=True)
    parser.add_argument("--verify-original-sources", action="store_true",
                        help="also replay and bind each original authoring source")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = inspect_pinned_consumer_cohort(
            args.jobs_file, expected_jobs_sha256=args.expected_jobs_sha256,
            summary=args.summary,
            expected_summary_sha256=args.expected_summary_sha256,
            authorized=args.trusted_local_operator,
            verify_original_sources=args.verify_original_sources,
        )
    except (PermissionError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__,
            "native_device_qualified": False, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                     allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "ConsumerFirstRunCohortError",
    "inspect_consumer_first_run_cohort", "inspect_pinned_consumer_cohort",
    "main",
]
