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
from skeleton.app.offline_delivery_assurance import _save_identity
from skeleton.app.offline_first_playable_batch import (
    DeliveryJob, _check_jobs, _parse_job,
    inspect_first_playable_delivery_batch, publish_first_playable_delivery_batch,
    resume_first_playable_delivery_batch,
)
from skeleton.app.offline_first_playable_batch_triage import (
    triage_first_playable_delivery_batch,
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
    except (UnicodeError, ValueError, TypeError) as exc:
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
    if mode not in {"publish", "resume", "inspect", "triage"}:
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
                 "inspect": True, "triage": None}[mode],
    )
    _disjoint_input(path, jobs, summary)
    return jobs, before


def execute_pinned_jobfile(
    filename: str | Path, *, expected_jobs_sha256: str,
    summary: str | Path, mode: str,
    expected_summary_sha256: str | None = None, authorized: bool,
) -> dict[str, object]:
    """Run the canonical delivery/triage path, then revalidate input custody."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if mode == "inspect":
        _pin(expected_summary_sha256)
    elif mode == "triage" and expected_summary_sha256 is not None:
        _pin(expected_summary_sha256)
    elif mode in {"publish", "resume"} and expected_summary_sha256 is not None:
        raise FirstPlayableJobFileError("summary pin is inspection-only")
    jobs, identity = read_pinned_jobs(
        filename, expected_sha256=expected_jobs_sha256,
        summary=summary, mode=mode, authorized=True,
    )
    if mode == "publish":
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
            authorized=True,
        )
    elif mode == "triage":
        result = triage_first_playable_delivery_batch(
            jobs, summary, expected_summary_sha256=expected_summary_sha256,
            authorized=True,
        )
    else:
        raise FirstPlayableJobFileError("unsupported delivery mode")
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
                        choices=("publish", "resume", "inspect", "triage"))
    parser.add_argument("--expected-summary-sha256")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = execute_pinned_jobfile(
            args.jobs_file, expected_jobs_sha256=args.expected_jobs_sha256,
            summary=args.summary, mode=args.mode,
            expected_summary_sha256=args.expected_summary_sha256,
            authorized=args.trusted_local_operator,
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
    "execute_pinned_jobfile", "main",
]
