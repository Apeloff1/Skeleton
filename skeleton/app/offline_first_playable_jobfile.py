"""Owner-private pinned job-file bridge for canonical first-playable cohorts.

The manifest is a transport for operator-held input, not an authority to sign,
approve, repair, overwrite, or certify a game. All gameplay and delivery
verification stays in the canonical batch and triage implementations.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import (
    _assert_original_root, _read, _root_fd,
)
from skeleton.app.offline_delivery_assurance import _save_identity, _source_identity
from skeleton.app.offline_first_playable_batch import (
    DeliveryJob, _check_jobs, _parse_job,
    inspect_first_playable_delivery_batch, publish_first_playable_delivery_batch,
    resume_first_playable_delivery_batch,
)
from skeleton.app.offline_first_playable_batch_triage import (
    triage_first_playable_delivery_batch,
)
from skeleton.app.offline_first_playable_delivery import _preflight, _path
from skeleton.ai.game_builder.offline_receipt_publication import (
    preflight_receipt_destination,
)

SCHEMA = "skeleton.app.first_playable_jobfile.v1"
MAX_JOBFILE_BYTES = 512 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class FirstPlayableJobFileError(ValueError):
    """An untrusted job-file input or custody fence failed closed."""


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FirstPlayableJobFileError("duplicate job-file JSON key")
        result[key] = value
    return result


def _no_constant(value: str) -> object:
    raise FirstPlayableJobFileError("nonfinite job-file JSON constant")


def _pin(value: str | None) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise FirstPlayableJobFileError("independently held lowercase SHA-256 required")
    return value


def _absolute(value: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(Path(value).expanduser())))


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _disjoint_input(
    input_path: Path, jobs: tuple[DeliveryJob, ...], summary: str | Path,
) -> None:
    """Do not let a delivery write into, replace, or subsume its own input."""
    destinations = [_absolute(summary)]
    roots: list[Path] = []
    for job in jobs:
        roots.extend((_absolute(job.source), _absolute(job.install)))
        destinations.extend((
            _absolute(job.archive), _absolute(job.save),
            _absolute(job.receipt),
        ))
    if any(_within(input_path, root) or _within(root, input_path)
           for root in roots):
        raise FirstPlayableJobFileError("job file overlaps a game tree")
    if any(_within(input_path, target) or _within(target, input_path)
           for target in destinations):
        raise FirstPlayableJobFileError("job file overlaps delivery output")


def _parse_jobs(raw: bytes) -> tuple[DeliveryJob, ...]:
    if not 0 < len(raw) <= MAX_JOBFILE_BYTES:
        raise FirstPlayableJobFileError("job-file byte budget exceeded")
    try:
        payload = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_unique_pairs, parse_constant=_no_constant,
        )
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        # Deeply nested, otherwise small JSON must fail as a typed input
        # rejection rather than escaping the CLI's fail-closed error boundary.
        raise FirstPlayableJobFileError("invalid strict UTF-8 job-file JSON") from exc
    if (type(payload) is not dict
            or set(payload) != {"schema", "jobs"}
            or payload["schema"] != SCHEMA
            or type(payload["jobs"]) is not list
            or not 2 <= len(payload["jobs"]) <= 8):
        raise FirstPlayableJobFileError("expected 2-8 bounded typed jobs")
    jobs: list[DeliveryJob] = []
    for item in payload["jobs"]:
        if type(item) is not dict:
            raise FirstPlayableJobFileError("job must be a JSON object")
        if any(key in item and type(item[key]) is not str
               for key in ("archive_sha256", "save_sha256", "receipt_sha256")):
            raise FirstPlayableJobFileError("output pins must be strings")
        try:
            job = _parse_job(json.dumps(
                item, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ))
        except (ValueError, TypeError) as exc:
            raise FirstPlayableJobFileError("invalid typed job") from exc
        jobs.append(job)
    return tuple(jobs)


def read_pinned_jobs(
    filename: str | Path, *, expected_sha256: str, summary: str | Path,
    mode: str, authorized: bool,
) -> tuple[tuple[DeliveryJob, ...], tuple[int, ...]]:
    """Double-read an owner-private POSIX file with an independent digest.

    The input's own JSON cannot declare its trusted digest. The digest must
    arrive separately from the operator. Identity and bytes are rechecked
    after the canonical operation, including when it published an output.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise FirstPlayableJobFileError("POSIX nofollow input required")
    if mode not in {"publish", "resume", "inspect", "triage", "preflight"}:
        raise FirstPlayableJobFileError("unsupported delivery mode")
    digest = _pin(expected_sha256)
    path = _absolute(filename)
    before = _save_identity(path)
    parent_fd = _root_fd(path.parent)
    try:
        first = _read(parent_fd, path.name, MAX_JOBFILE_BYTES, owner_controlled=True)
        second = _read(parent_fd, path.name, MAX_JOBFILE_BYTES, owner_controlled=True)
        _assert_original_root(path.parent, parent_fd)
    finally:
        os.close(parent_fd)
    if (not hmac.compare_digest(first, second)
            or before != _save_identity(path)
            or not hmac.compare_digest(sha256(first).hexdigest(), digest)):
        raise FirstPlayableJobFileError("job-file digest or inode changed")
    jobs = _parse_jobs(first)
    _check_jobs(
        jobs, summary,
        inspect={"publish": False, "resume": None,
                 "inspect": True, "triage": None, "preflight": False}[mode],
    )
    _disjoint_input(path, jobs, summary)
    return jobs, before




def preflight_pinned_cohort(
    jobs: tuple[DeliveryJob, ...], summary: str | Path, *,
    authorized: bool,
) -> dict[str, object]:
    """Dry-run canonical source replay and destination admission for all games.

    This is explicitly not a reservation, installer run, native-device test,
    or permission to publish. Every source is reverified after all others.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    checked = _check_jobs(jobs, summary, inspect=False)
    roots = tuple(path for job in checked for path in (job.source, job.install))
    preflight_receipt_destination(
        summary, protected_roots=roots, authorized=True,
    )
    # Capture every original source root before replay. A replacement root
    # with identical package bytes must not pass as uninterrupted custody.
    # This is observational: no directory is locked, reserved or modified.
    source_identities = tuple(_source_identity(job.source) for job in checked)
    records: list[dict[str, object]] = []

    def verify(job: DeliveryJob, identity: tuple[int, ...]) -> dict[str, object]:
        if _source_identity(job.source) != identity:
            raise FirstPlayableJobFileError(
                "original source root changed before cohort preflight"
            )
        observed = _preflight(
            _path(job.source), _path(job.archive), _path(job.install),
            _path(job.save), _path(job.receipt),
            expected_manifest_sha256=job.manifest_sha256, authorized=True,
        )
        if _source_identity(job.source) != identity:
            raise FirstPlayableJobFileError(
                "original source root changed during cohort preflight"
            )
        if (type(observed.get("project_id")) is not str
                or not observed["project_id"]
                or type(observed.get("world_digest")) is not str
                or observed.get("offline_gameplay_reexecuted") is not True
                or observed.get("release_certified") is not False):
            raise FirstPlayableJobFileError(
                "original source admission contract missing"
            )
        return {
            "project_id": observed["project_id"],
            "world_digest": observed["world_digest"],
            "manifest_sha256": job.manifest_sha256,
            "source_replay_verified": True,
        }

    for job, identity in zip(checked, source_identities, strict=True):
        records.append(verify(job, identity))
    if len({record["project_id"] for record in records}) != len(records):
        raise FirstPlayableJobFileError(
            "duplicate original game project ID in admission cohort"
        )
    for job, original, identity in zip(
        checked, records, source_identities, strict=True,
    ):
        if verify(job, identity) != original:
            raise FirstPlayableJobFileError(
                "original source changed during admission"
            )
    # The last replay of a later game must not mask an earlier source swap.
    if any(_source_identity(job.source) != identity
           for job, identity in zip(checked, source_identities, strict=True)):
        raise FirstPlayableJobFileError(
            "original source root changed after cohort preflight"
        )
    return {
        "schema": "skeleton.app.first_playable_jobfile_preflight.v1",
        "status": "original_game_cohort_admitted_not_reserved_release_blocked",
        "game_count": len(checked),
        "games": records,
        "all_original_sources_replayed": True,
        "source_root_inodes_stable": True,
        "destinations_reserved": False,
        "outputs_published": False,
        "read_only": True,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "persistent_rollback_protection": False,
        "release_certified": False,
    }

def execute_pinned_jobfile(
    filename: str | Path, *, expected_jobs_sha256: str,
    summary: str | Path, mode: str,
    expected_summary_sha256: str | None = None, authorized: bool,
    verify_original_sources: bool = False,
) -> dict[str, object]:
    """Run the canonical delivery/triage path, then revalidate input custody.

    Source replay during inspection is explicit: archived games remain
    inspectable when their original authoring directory no longer exists.
    The stronger source-provenance check cannot authorize publication.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if type(verify_original_sources) is not bool or (verify_original_sources and mode != "inspect"):
        raise FirstPlayableJobFileError(
            "original-source replay is an inspection-only boolean option"
        )
    if mode == "inspect":
        _pin(expected_summary_sha256)
    elif mode == "triage" and expected_summary_sha256 is not None:
        _pin(expected_summary_sha256)
    elif mode in {"publish", "resume", "preflight"} and expected_summary_sha256 is not None:
        raise FirstPlayableJobFileError("summary pin is inspection-only")
    jobs, identity = read_pinned_jobs(
        filename, expected_sha256=expected_jobs_sha256,
        summary=summary, mode=mode, authorized=True,
    )
    # Even a failed/partial publisher may have consumed an input that was
    # concurrently replaced. Verify custody on BOTH success and exception;
    # never let an exception skip the final independently pinned read.
    try:
        if mode == "preflight":
            result = preflight_pinned_cohort(jobs, summary, authorized=True)
        elif mode == "publish":
            result = publish_first_playable_delivery_batch(
                jobs, summary, authorized=True,
            )
        elif mode == "resume":
            result = resume_first_playable_delivery_batch(
                jobs, summary, authorized=True,
            )
        elif mode == "inspect":
            result = inspect_first_playable_delivery_batch(
                jobs, summary, expected_summary_sha256=expected_summary_sha256,
                authorized=True, verify_original_sources=verify_original_sources,
            )
        elif mode == "triage":
            result = triage_first_playable_delivery_batch(
                jobs, summary, expected_summary_sha256=expected_summary_sha256,
                authorized=True,
            )
        else:
            raise FirstPlayableJobFileError("unsupported delivery mode")
    finally:
        again, final_identity = read_pinned_jobs(
            filename, expected_sha256=expected_jobs_sha256,
            summary=summary, mode=mode, authorized=True,
        )
        if jobs != again or identity != final_identity:
            raise FirstPlayableJobFileError(
                "job-file inode or content changed during delivery"
            )
    if result.get("release_certified") is not False:
        raise FirstPlayableJobFileError("canonical result made release claim")
    return {
        **result,
        "input_manifest_sha256": expected_jobs_sha256,
        "input_manifest_unchanged": True,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app first-playable-jobfile",
        description="Run bounded original-game delivery from a pinned private job file",
    )
    parser.add_argument("--jobs-file", required=True)
    parser.add_argument("--expected-jobs-sha256", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--mode", required=True,
                        choices=("preflight", "publish", "resume", "inspect", "triage"))
    parser.add_argument("--expected-summary-sha256")
    parser.add_argument(
        "--verify-original-sources", action="store_true",
        help="during read-only inspect, reexecute and bind every original source",
    )
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = execute_pinned_jobfile(
            args.jobs_file, expected_jobs_sha256=args.expected_jobs_sha256,
            summary=args.summary, mode=args.mode,
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
    print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                     allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "FirstPlayableJobFileError", "read_pinned_jobs",
    "preflight_pinned_cohort", "execute_pinned_jobfile", "main",
]
