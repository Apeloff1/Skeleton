"""Read-only quarantine triage for interrupted multi-game delivery cohorts.

An occupied name is not evidence of a completed install. Only independently
pinned, reexecuted games qualify as verified. No missing pin is inferred from
the filesystem and no artifact is unlinked, moved, repaired or overwritten.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import (
    _assert_original_root, verify_exported_package,
)
from skeleton.app.offline_archive_install import _parent as install_parent
from skeleton.app.offline_delivery_archive import _parent as archive_parent
from skeleton.app.offline_first_playable_batch import (
    DeliveryJob, _check_jobs, _parse_job, _reverify_original_sources,
    _delivered_custody, _inspect_jobs, _record,
    inspect_first_playable_delivery_batch,
)
from skeleton.app.offline_first_playable_delivery import (
    _preflight, _path, inspect_first_playable_delivery,
)
from skeleton.app.offline_delivery_assurance import _source_identity
from skeleton.app.private_game_save import _parent as private_parent

SCHEMA = "skeleton.app.first_playable_delivery_batch_triage.v1"


class FirstPlayableBatchTriageError(ValueError):
    """The read-only delivery cohort inspection cannot establish safe custody."""


def _entry(path: str | Path, opener, *, directory: bool) -> str:
    """Nofollow inspection relative to an owner-controlled parent descriptor."""
    try:
        target, parent_fd = opener(path)
        try:
            try:
                info = os.stat(
                    target.name, dir_fd=parent_fd, follow_symlinks=False,
                )
            except FileNotFoundError:
                state = "missing"
            else:
                if (info.st_uid != os.geteuid()
                        or info.st_mode & 0o077
                        or (not stat.S_ISDIR(info.st_mode) if directory
                            else not stat.S_ISREG(info.st_mode))
                        or (not directory and (info.st_nlink != 1
                                               or info.st_size <= 0))):
                    state = "unsafe"
                else:
                    state = "present"
            # Even a missing name can become a false 'resume-safe' signal
            # if the parent was replaced after its descriptor was opened.
            _assert_original_root(target.parent, parent_fd)
            return state
        finally:
            os.close(parent_fd)
    except (OSError, ValueError, TypeError):
        return "unsafe"


def _states(job: DeliveryJob) -> dict[str, str]:
    return {
        "archive": _entry(job.archive, archive_parent, directory=False),
        "install": _entry(job.install, install_parent, directory=True),
        "save": _entry(job.save, private_parent, directory=False),
        "receipt": _entry(job.receipt, private_parent, directory=False),
    }


def _pinned(job: DeliveryJob) -> bool:
    return all((job.archive_sha256, job.save_sha256, job.receipt_sha256))


def triage_first_playable_delivery_batch(
    jobs: Sequence[DeliveryJob], summary_receipt: str | Path, *,
    expected_summary_sha256: str | None = None,
    authorized: bool,
) -> dict[str, object]:
    """Inspect live artifacts and determine whether pinned-prefix resume is safe."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    checked = _check_jobs(jobs, summary_receipt, inspect=None)
    statuses: list[dict[str, object]] = []
    for index, job in enumerate(checked):
        entries = _states(job)
        if "unsafe" in entries.values():
            state = "unsafe_custody_quarantine"
        elif all(value == "missing" for value in entries.values()):
            state = "missing_unpublished" if not _pinned(job) else "pinned_but_missing"
        elif not all(value == "present" for value in entries.values()):
            state = "partial_publication_quarantine"
        elif not _pinned(job):
            state = "untrusted_publication_missing_independent_pins"
        else:
            try:
                replay = inspect_first_playable_delivery(
                    job.install, job.archive, job.save, job.receipt,
                    expected_manifest_sha256=job.manifest_sha256,
                    expected_archive_sha256=job.archive_sha256,
                    expected_save_sha256=job.save_sha256,
                    expected_receipt_sha256=job.receipt_sha256,
                    authorized=True,
                )
                source = verify_exported_package(
                    job.source,
                    expected_manifest_sha256=job.manifest_sha256,
                    authorized=True,
                )
                if (replay.get("live_source_and_private_replay_reexecuted")
                        is not True
                        or replay.get("release_certified") is not False
                        or source.get("release_certified") is not False
                        or source.get("offline_gameplay_reexecuted") is not True
                        or source.get("world_digest") != replay.get("world_digest")
                        or source.get("project_id") != replay.get("project_id")
                        or replay.get("action_count") != len(job.moves)):
                    raise FirstPlayableBatchTriageError(
                        "original source or private replay diverged"
                    )
            except (OSError, ValueError, TypeError, KeyError):
                state = "pinned_replay_failed_quarantine"
            else:
                state = "independently_pinned_replay_verified"
        statuses.append({
            "index": index,
            "state": state,
            "artifacts": entries,
            "independent_pins_supplied": _pinned(job),
            "release_certified": False,
        })
    summary_state = _entry(summary_receipt, private_parent, directory=False)
    if summary_state == "present":
        if expected_summary_sha256 is None:
            summary_state = "untrusted_summary_missing_independent_pin"
        elif not all(
            item["state"] == "independently_pinned_replay_verified"
            for item in statuses
        ):
            summary_state = "summary_present_but_cohort_unverified"
        else:
            try:
                inspection = inspect_first_playable_delivery_batch(
                    checked, summary_receipt,
                    expected_summary_sha256=expected_summary_sha256,
                    authorized=True,
                )
                if (inspection.get("all_live_games_reexecuted") is not True
                        or inspection.get("release_certified") is not False):
                    raise FirstPlayableBatchTriageError("cohort replay not verified")
            except (OSError, ValueError, TypeError, KeyError):
                summary_state = "summary_integrity_or_replay_failed_quarantine"
            else:
                summary_state = "independently_pinned_cohort_verified"
    elif summary_state == "missing" and expected_summary_sha256 is not None:
        summary_state = "pinned_summary_missing"
    verified_prefix = 0
    for item in statuses:
        if item["state"] == "independently_pinned_replay_verified":
            verified_prefix += 1
        else:
            break
    can_resume = (
        summary_state == "missing"
        and 0 < verified_prefix < len(checked)
        and all(
            item["state"] == "missing_unpublished"
            for item in statuses[verified_prefix:]
        )
    )
    # A clean published prefix and missing suffix are necessary, not enough.
    # Replay every unpublished source and check every destination *without*
    # reserving it. Otherwise triage could claim resume eligibility when the
    # next game's source is tampered, missing, or a duplicate project.
    source_preflight_verified = False
    if can_resume:
        try:
            # The earlier status snapshot is not a durable reservation. Pin
            # the entire published prefix before replaying the missing suffix;
            # a same-byte inode swap must not produce a resume-safe verdict.
            prefix = checked[:verified_prefix]
            prefix_custody = _delivered_custody(prefix)
            prefix_records = []
            for job in prefix:
                inspected = inspect_first_playable_delivery(
                    job.install, job.archive, job.save, job.receipt,
                    expected_manifest_sha256=job.manifest_sha256,
                    expected_archive_sha256=job.archive_sha256,
                    expected_save_sha256=job.save_sha256,
                    expected_receipt_sha256=job.receipt_sha256,
                    authorized=True,
                )
                prefix_records.append(_record(inspected, job.moves))
            _inspect_jobs(prefix, prefix_records)
            admissions: list[dict[str, object]] = []
            identities: list[tuple[int, ...]] = []
            for index, job in enumerate(checked):
                if index < verified_prefix:
                    observed = verify_exported_package(
                        job.source,
                        expected_manifest_sha256=job.manifest_sha256,
                        authorized=True,
                    )
                else:
                    observed = _preflight(
                        _path(job.source), _path(job.archive), _path(job.install),
                        _path(job.save), _path(job.receipt),
                        expected_manifest_sha256=job.manifest_sha256,
                        authorized=True,
                    )
                if (type(observed.get("project_id")) is not str
                        or not observed["project_id"]
                        or observed.get("offline_gameplay_reexecuted") is not True
                        or observed.get("release_certified") is not False):
                    raise FirstPlayableBatchTriageError(
                        "original source replay admission missing"
                    )
                admissions.append(observed)
                identities.append(_source_identity(job.source))
            if len({item["project_id"] for item in admissions}) != len(admissions):
                raise FirstPlayableBatchTriageError(
                    "duplicate original project in resumable cohort"
                )
            _reverify_original_sources(checked, admissions, identities)
            # A suffix destination or summary may appear while the expensive
            # source replay runs. Recheck every name and every pinned game
            # after the last preflight before reporting resume eligibility.
            _inspect_jobs(prefix, prefix_records)
            if (_delivered_custody(prefix) != prefix_custody
                    or _entry(summary_receipt, private_parent,
                              directory=False) != "missing"
                    or any(any(value != "missing" for value in _states(job).values())
                           for job in checked[verified_prefix:])):
                raise FirstPlayableBatchTriageError(
                    "delivery artifacts changed during resume eligibility replay"
                )
        except (OSError, ValueError, TypeError, KeyError):
            can_resume = False
        else:
            source_preflight_verified = True
    return {
        "schema": SCHEMA,
        "status": "read_only_delivery_cohort_triage_release_blocked",
        "game_count": len(checked),
        "jobs": statuses,
        "summary_state": summary_state,
        "verified_prefix_count": verified_prefix,
        "resume_eligible_with_independent_pins": can_resume,
        "resume_source_preflight_verified": source_preflight_verified,
        "resume_destinations_reserved": False,
        "all_games_verified": all(
            item["state"] == "independently_pinned_replay_verified"
            for item in statuses
        ),
        "read_only": True,
        "artifacts_modified": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "persistent_rollback_protection": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app first-playable-batch-triage",
        description="Read-only inspect interrupted original-game delivery cohort",
    )
    parser.add_argument("--job", action="append", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--expected-summary-sha256")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        if not 2 <= len(args.job) <= 8:
            raise FirstPlayableBatchTriageError("2-8 bounded jobs required")
        result = triage_first_playable_delivery_batch(
            tuple(_parse_job(item) for item in args.job), args.summary,
            expected_summary_sha256=args.expected_summary_sha256,
            authorized=True,
        )
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
