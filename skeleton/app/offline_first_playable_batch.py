"""Bounded multi-game install-to-playable delivery with independently pinned evidence.

Each game is exported, freshly installed, played, saved, restored and verified
through the canonical single-game pipeline. No device, rights or release
qualification follows from these source-level acceptance checks.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import (
    _canonical_bytes, _json, verify_exported_package,
)
from skeleton.ai.game_builder.offline_receipt_publication import (
    preflight_receipt_destination, publish_verified_receipt,
)
from skeleton.app.offline_first_playable_delivery import (
    MAX_ACTIONS, _ACTIONS, _path, _is_within, _preflight,
    inspect_first_playable_delivery, publish_first_playable_delivery,
)
from skeleton.app.offline_delivery_assurance import _source_identity
from skeleton.app.private_game_save import read_private_game_save

SCHEMA = "skeleton.app.first_playable_delivery_batch.v1"
MIN_GAMES = 2
MAX_GAMES = 8
MAX_INPUT_BYTES = 64 * 1024
MAX_SUMMARY_BYTES = 256 * 1024
_PIN = re.compile(r"[0-9a-f]{64}\Z")


class FirstPlayableDeliveryBatchError(ValueError):
    """A bounded original-game delivery cohort failed closed."""


@dataclass(frozen=True, slots=True)
class DeliveryJob:
    source: str | Path
    archive: str | Path
    install: str | Path
    save: str | Path
    receipt: str | Path
    manifest_sha256: str
    moves: tuple[str, ...]
    archive_sha256: str | None = None
    save_sha256: str | None = None
    receipt_sha256: str | None = None


def _check_jobs(jobs: Sequence[DeliveryJob], summary: str | Path, *,
                inspect: bool | None) -> tuple[DeliveryJob, ...]:
    if (type(jobs) not in (tuple, list)
            or not MIN_GAMES <= len(jobs) <= MAX_GAMES
            or any(type(job) is not DeliveryJob for job in jobs)):
        raise FirstPlayableDeliveryBatchError("2-8 typed game delivery jobs required")
    checked = tuple(jobs)
    paths: list[tuple[Path, Path, Path, Path, Path]] = []
    def canonical(value: str | Path) -> Path:
        # Path.absolute preserves '..'; normalize before cross-job checks.
        return Path(os.path.abspath(os.fspath(_path(value))))
    for job in checked:
        # A manifest pin is independent operator authority. Reject malformed
        # values before replay, destination preflight or any output publication.
        if (type(job.manifest_sha256) is not str
                or _PIN.fullmatch(job.manifest_sha256) is None):
            raise FirstPlayableDeliveryBatchError(
                "independent source manifest requires lowercase SHA-256"
            )
        if any(type(value) not in (str, Path) for value in (
            job.source, job.archive, job.install, job.save, job.receipt,
        )):
            raise FirstPlayableDeliveryBatchError(
                "game delivery paths must be strings or pathlib Paths"
            )
        if (type(job.moves) is not tuple
                or not 1 <= len(job.moves) <= MAX_ACTIONS
                or any(type(move) is not str or move not in _ACTIONS
                       for move in job.moves)):
            raise FirstPlayableDeliveryBatchError("invalid bounded player action series")
        if inspect and not all((job.archive_sha256, job.save_sha256,
                                job.receipt_sha256)):
            raise FirstPlayableDeliveryBatchError("independent game pins required")
        pins = (job.archive_sha256, job.save_sha256, job.receipt_sha256)
        if any(pin is not None and (type(pin) is not str
                                    or _PIN.fullmatch(pin) is None)
               for pin in pins):
            raise FirstPlayableDeliveryBatchError(
                "output pins must be complete lowercase SHA-256 digests"
            )
        if inspect is False and any(pin is not None for pin in pins):
            raise FirstPlayableDeliveryBatchError("publication cannot accept output pins")
        if inspect is None and any(pin is not None for pin in pins) and not all(pins):
            raise FirstPlayableDeliveryBatchError("partial game pin triple rejected")
        paths.append(tuple(map(canonical, (
            job.source, job.archive, job.install, job.save, job.receipt,
        ))))
    summary_path = canonical(summary)
    sources = [entry[0] for entry in paths]
    installs = [entry[2] for entry in paths]
    outputs = [path for entry in paths for path in (entry[1], entry[3], entry[4])]
    outputs.append(summary_path)
    if len(set(outputs)) != len(outputs):
        raise FirstPlayableDeliveryBatchError("duplicate delivery output name")
    # A file output must not subsume another output or any game tree.
    for index, output in enumerate(outputs):
        if any(_is_within(output, other) or _is_within(other, output)
               for other in outputs[index + 1:]):
            raise FirstPlayableDeliveryBatchError("nested delivery output names")
    if len(set(sources)) != len(sources):
        raise FirstPlayableDeliveryBatchError("duplicate original source tree")
    if len({job.manifest_sha256 for job in checked}) != len(checked):
        raise FirstPlayableDeliveryBatchError("reused original source manifest pin")
    roots = sources + installs
    for i, root in enumerate(roots):
        if any(_is_within(root, other) or _is_within(other, root)
               for other in roots[i + 1:]):
            raise FirstPlayableDeliveryBatchError("source and install roots overlap")
    if any(_is_within(output, root) or _is_within(root, output)
           for output in outputs for root in roots):
        raise FirstPlayableDeliveryBatchError("delivery evidence inside game tree")
    return checked


def _evidence(result: dict[str, object]) -> dict[str, object]:
    keys = (
        "project_id", "manifest_sha256", "archive_sha256", "save_sha256",
        "independent_receipt_sha256", "world_digest", "replay_digest",
        "action_count",
    )
    if (type(result) is not dict
            or any(key not in result for key in keys)
            or result.get("offline_gameplay_reexecuted") is not True
            or result.get("release_certified") is not False
            or result.get("native_device_qualified") is not False
            or result.get("package_signed") is not False):
        raise FirstPlayableDeliveryBatchError("canonical delivery evidence missing")
    # The canonical single-game result is a trust boundary. Never publish a
    # cohort receipt containing booleans as counts, untyped identities, or
    # malformed hashes even if an upstream adapter returns them as "success".
    for key in ("manifest_sha256", "archive_sha256", "save_sha256",
                "independent_receipt_sha256"):
        if type(result[key]) is not str or _PIN.fullmatch(result[key]) is None:
            raise FirstPlayableDeliveryBatchError(
                "canonical delivery evidence has a noncanonical SHA-256 pin"
            )
    for key in ("project_id", "world_digest", "replay_digest"):
        if type(result[key]) is not str or not result[key]:
            raise FirstPlayableDeliveryBatchError(
                "canonical delivery evidence has an invalid identity"
            )
    if (type(result["action_count"]) is not int
            or not 1 <= result["action_count"] <= MAX_ACTIONS):
        raise FirstPlayableDeliveryBatchError(
            "canonical delivery evidence has an invalid action count"
        )
    return {key: result[key] for key in keys}


def _record(result: dict[str, object], moves: tuple[str, ...]) -> dict[str, object]:
    evidence = _evidence(result)
    if (type(moves) is not tuple
            or not 1 <= len(moves) <= MAX_ACTIONS
            or any(type(move) is not str or move not in _ACTIONS for move in moves)
            or evidence["action_count"] != len(moves)):
        raise FirstPlayableDeliveryBatchError(
            "canonical replay count does not match operator player actions"
        )
    return {
        **evidence,
        "moves_sha256": sha256(_canonical_bytes(list(moves))).hexdigest(),
    }


def _summary(records: list[dict[str, object]]) -> dict[str, object]:
    if len({record["project_id"] for record in records}) != len(records):
        raise FirstPlayableDeliveryBatchError("duplicate original game project ID")
    if len({record["independent_receipt_sha256"] for record in records}) != len(records):
        raise FirstPlayableDeliveryBatchError("reused delivery receipt identity")
    body = {
        "schema": SCHEMA,
        "game_count": len(records),
        "games": records,
        "all_original_games_replayed": True,
        "offline_gameplay_reexecuted": True,
        "independent_pin_distribution_required": True,
        "read_only_source_verification": True,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "persistent_rollback_protection": False,
        "release_certified": False,
    }
    return body


def _inspect_jobs(jobs: tuple[DeliveryJob, ...],
                  records: list[dict[str, object]]) -> None:
    if len(jobs) != len(records):
        raise FirstPlayableDeliveryBatchError("delivery cohort length mismatch")
    for job, record in zip(jobs, records, strict=True):
        inspected = inspect_first_playable_delivery(
            job.install, job.archive, job.save, job.receipt,
            expected_manifest_sha256=job.manifest_sha256,
            expected_archive_sha256=record["archive_sha256"],
            expected_save_sha256=record["save_sha256"],
            expected_receipt_sha256=record["independent_receipt_sha256"],
            authorized=True,
        )
        if (_record(inspected, job.moves) != record
                or inspected.get("live_source_and_private_replay_reexecuted") is not True
                or inspected.get("read_only") is not True):
            raise FirstPlayableDeliveryBatchError(
                "live delivery no longer matches its independently pinned record"
            )


def _reverify_original_sources(
    jobs: tuple[DeliveryJob, ...],
    admissions: Sequence[dict[str, object]],
    identities: Sequence[tuple[int, ...]],
) -> None:
    """Reexecute *every* original source after the last game publishes.

    A single-game delivery checks its own source, but later cohort members
    may take minutes to install and play. A previously admitted source can
    change in that interval. The final cohort receipt must never certify a
    stale original-source inventory. No file is repaired or deleted here.
    """
    if len(jobs) != len(admissions) or len(jobs) != len(identities):
        raise FirstPlayableDeliveryBatchError("source cohort evidence length mismatch")
    for job, admitted, identity in zip(jobs, admissions, identities, strict=True):
        if _source_identity(job.source) != identity:
            raise FirstPlayableDeliveryBatchError(
                "original game source root identity changed"
            )
        replayed = verify_exported_package(
            job.source, expected_manifest_sha256=job.manifest_sha256,
            authorized=True,
        )
        if (replayed != admitted
                or replayed.get("offline_gameplay_reexecuted") is not True
                or replayed.get("release_certified") is not False
                or _source_identity(job.source) != identity):
            raise FirstPlayableDeliveryBatchError(
                "original game source changed during cohort delivery"
            )


def _checkpoint_published_cohort(
    jobs: tuple[DeliveryJob, ...],
    records: list[dict[str, object]],
    admissions: Sequence[dict[str, object]],
    identities: Sequence[tuple[int, ...]],
) -> None:
    """Fail closed after EACH game, before another game's first write.

    A previously installed game, private save, receipt or original source may
    be replaced while the next game is being built. Checking only before the
    first publication and after the last one unnecessarily publishes further
    games from a cohort already known to be untrustworthy. This is a bounded
    observational barrier, not an atomic lock or a rollback mechanism.
    """
    _inspect_jobs(jobs[:len(records)], records)
    _reverify_original_sources(jobs, admissions, identities)


def publish_first_playable_delivery_batch(
    jobs: Sequence[DeliveryJob], summary_destination: str | Path, *,
    authorized: bool,
) -> dict[str, object]:
    """Preflight every original game before any output, then publish one cohort."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    checked = _check_jobs(jobs, summary_destination, inspect=False)
    roots = tuple(path for job in checked for path in (job.source, job.install))
    preflight_receipt_destination(
        summary_destination, protected_roots=roots, authorized=True,
    )
    # Admission is deliberately all-or-nothing, not a reservation. A later
    # failure may leave a prefix of already published, immutable game outputs.
    source_projects: list[str] = []
    admissions: list[dict[str, object]] = []
    identities: list[tuple[int, ...]] = []
    for job in checked:
        admitted = _preflight(
            _path(job.source), _path(job.archive), _path(job.install),
            _path(job.save), _path(job.receipt),
            expected_manifest_sha256=job.manifest_sha256, authorized=True,
        )
        project = admitted.get("project_id")
        if type(project) is not str or not project:
            raise FirstPlayableDeliveryBatchError(
                "canonical original source project identity missing"
            )
        source_projects.append(project)
        admissions.append(admitted)
        identities.append(_source_identity(job.source))
    # The source verifier already knows project identity. Reject duplicate
    # projects before the first ZIP is published; discovering this only when
    # assembling the final receipt would strand an otherwise valid cohort.
    if len(set(source_projects)) != len(source_projects):
        raise FirstPlayableDeliveryBatchError(
            "duplicate original project identity before publication"
        )
    _reverify_original_sources(checked, admissions, identities)
    records: list[dict[str, object]] = []
    for job in checked:
        published = publish_first_playable_delivery(
            job.source, job.archive, job.install, job.save, job.receipt,
            expected_manifest_sha256=job.manifest_sha256,
            moves=job.moves, authorized=True,
        )
        records.append(_record(published, job.moves))
        _checkpoint_published_cohort(checked, records, admissions, identities)
    # Recheck original sources as well as installed games after the last write.
    _inspect_jobs(checked, records)
    _reverify_original_sources(checked, admissions, identities)
    envelope = _summary(records)
    pin = publish_verified_receipt(
        envelope, summary_destination, protected_roots=roots, authorized=True,
    )
    read_back = read_private_game_save(
        summary_destination, expected_sha256=pin, authorized=True,
    )
    if (not hmac.compare_digest(read_back, _canonical_bytes(envelope))
            or sha256(read_back).hexdigest() != pin):
        raise FirstPlayableDeliveryBatchError("published cohort receipt changed")
    _inspect_jobs(checked, records)
    _reverify_original_sources(checked, admissions, identities)
    return {
        **envelope,
        "status": "original_game_delivery_cohort_published_release_blocked",
        "summary_receipt": str(_path(summary_destination)),
        "independent_summary_sha256": pin,
        "read_only": False,
    }


def resume_first_playable_delivery_batch(
    jobs: Sequence[DeliveryJob], summary_destination: str | Path, *,
    authorized: bool,
) -> dict[str, object]:
    """Resume only a fully pinned, contiguous prefix of immutable deliveries.

    A failed batch cannot infer its own missing independent pins. The operator
    must provide all three output digests for each already published game.
    The source and live installed game are replay-verified before the first
    new write. Nothing from the completed prefix is replaced or removed.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    checked = _check_jobs(jobs, summary_destination, inspect=None)
    completed = 0
    for job in checked:
        if all((job.archive_sha256, job.save_sha256, job.receipt_sha256)):
            completed += 1
        else:
            break
    if not 0 < completed < len(checked) or any(
        any((job.archive_sha256, job.save_sha256, job.receipt_sha256))
        for job in checked[completed:]
    ):
        raise FirstPlayableDeliveryBatchError(
            "resume requires contiguous independently pinned published prefix"
        )
    roots = tuple(path for job in checked for path in (job.source, job.install))
    preflight_receipt_destination(
        summary_destination, protected_roots=roots, authorized=True,
    )
    records: list[dict[str, object]] = []
    admissions: list[dict[str, object]] = []
    identities: list[tuple[int, ...]] = []
    for job in checked[:completed]:
        inspected = inspect_first_playable_delivery(
            job.install, job.archive, job.save, job.receipt,
            expected_manifest_sha256=job.manifest_sha256,
            expected_archive_sha256=job.archive_sha256,
            expected_save_sha256=job.save_sha256,
            expected_receipt_sha256=job.receipt_sha256,
            authorized=True,
        )
        source = verify_exported_package(
            job.source, expected_manifest_sha256=job.manifest_sha256,
            authorized=True,
        )
        if (source.get("project_id") != inspected.get("project_id")
                or source.get("world_digest") != inspected.get("world_digest")
                or source.get("offline_gameplay_reexecuted") is not True
                or source.get("release_certified") is not False):
            raise FirstPlayableDeliveryBatchError(
                "pinned prior delivery diverged from original game source"
            )
        records.append(_record(inspected, job.moves))
        admissions.append(source)
        identities.append(_source_identity(job.source))
    _inspect_jobs(checked[:completed], records)
    source_projects = [record["project_id"] for record in records]
    for job in checked[completed:]:
        admitted = _preflight(
            _path(job.source), _path(job.archive), _path(job.install),
            _path(job.save), _path(job.receipt),
            expected_manifest_sha256=job.manifest_sha256, authorized=True,
        )
        project = admitted.get("project_id")
        if type(project) is not str or not project:
            raise FirstPlayableDeliveryBatchError(
                "canonical original source project identity missing"
            )
        source_projects.append(project)
        admissions.append(admitted)
        identities.append(_source_identity(job.source))
    if len(set(source_projects)) != len(source_projects):
        raise FirstPlayableDeliveryBatchError(
            "duplicate original project identity before resumed publication"
        )
    _reverify_original_sources(checked, admissions, identities)
    for job in checked[completed:]:
        published = publish_first_playable_delivery(
            job.source, job.archive, job.install, job.save, job.receipt,
            expected_manifest_sha256=job.manifest_sha256,
            moves=job.moves, authorized=True,
        )
        records.append(_record(published, job.moves))
        _checkpoint_published_cohort(checked, records, admissions, identities)
    _inspect_jobs(checked, records)
    _reverify_original_sources(checked, admissions, identities)
    envelope = _summary(records)
    pin = publish_verified_receipt(
        envelope, summary_destination, protected_roots=roots, authorized=True,
    )
    raw = read_private_game_save(
        summary_destination, expected_sha256=pin, authorized=True,
    )
    if not hmac.compare_digest(raw, _canonical_bytes(envelope)):
        raise FirstPlayableDeliveryBatchError("resumed cohort receipt changed")
    _inspect_jobs(checked, records)
    _reverify_original_sources(checked, admissions, identities)
    return {
        **envelope,
        "status": "original_game_delivery_cohort_resumed_release_blocked",
        "previously_published_games": completed,
        "newly_published_games": len(checked) - completed,
        "summary_receipt": str(_path(summary_destination)),
        "independent_summary_sha256": pin,
        "read_only": False,
    }


def inspect_first_playable_delivery_batch(
    jobs: Sequence[DeliveryJob], summary_receipt: str | Path, *,
    expected_summary_sha256: str, authorized: bool,
) -> dict[str, object]:
    """Reexecute each delivered game with four independent pins per game."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    checked = _check_jobs(jobs, summary_receipt, inspect=True)
    raw = read_private_game_save(
        summary_receipt, expected_sha256=expected_summary_sha256,
        authorized=True,
    )
    if not 0 < len(raw) <= MAX_SUMMARY_BYTES:
        raise FirstPlayableDeliveryBatchError("cohort receipt byte budget exceeded")
    stored = _json(raw, MAX_SUMMARY_BYTES)
    if (type(stored) is not dict or stored.get("schema") != SCHEMA
            or not hmac.compare_digest(raw, _canonical_bytes(stored))
            or type(stored.get("games")) is not list
            or len(stored["games"]) != len(checked)):
        raise FirstPlayableDeliveryBatchError("invalid canonical cohort receipt")
    records = [
        {
            "project_id": record["project_id"],
            "manifest_sha256": job.manifest_sha256,
            "archive_sha256": job.archive_sha256,
            "save_sha256": job.save_sha256,
            "independent_receipt_sha256": job.receipt_sha256,
            "world_digest": record["world_digest"],
            "replay_digest": record["replay_digest"],
            "action_count": len(job.moves),
            "moves_sha256": sha256(_canonical_bytes(list(job.moves))).hexdigest(),
        }
        for job, record in zip(checked, stored["games"], strict=True)
    ]
    if stored != _summary(records):
        raise FirstPlayableDeliveryBatchError("cohort pins or release holds diverged")
    _inspect_jobs(checked, records)
    again = read_private_game_save(
        summary_receipt, expected_sha256=expected_summary_sha256,
        authorized=True,
    )
    if not hmac.compare_digest(raw, again):
        raise FirstPlayableDeliveryBatchError("cohort receipt changed during replay")
    _inspect_jobs(checked, records)
    return {
        **stored,
        "status": "original_game_delivery_cohort_reverified_release_blocked",
        "independent_summary_sha256": expected_summary_sha256,
        "receipt_integrity_verified": True,
        "all_live_games_reexecuted": True,
        "read_only": True,
    }


def _parse_job(raw: str) -> DeliveryJob:
    if type(raw) is not str or not 0 < len(raw.encode("utf-8")) <= MAX_INPUT_BYTES:
        raise FirstPlayableDeliveryBatchError("job JSON byte budget exceeded")
    def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise FirstPlayableDeliveryBatchError("duplicate job JSON key")
            value[key] = item
        return value

    def no_constant(value: str) -> object:
        raise FirstPlayableDeliveryBatchError("nonfinite job JSON constant")

    value = json.loads(raw, object_pairs_hook=unique_pairs,
                       parse_constant=no_constant)
    mandatory = {
        "source", "archive", "install", "save", "receipt",
        "manifest_sha256", "moves",
    }
    optional = {"archive_sha256", "save_sha256", "receipt_sha256"}
    if (type(value) is not dict or not mandatory <= value.keys()
            or not value.keys() <= mandatory | optional
            or any(type(value[key]) is not str for key in mandatory - {"moves"})
            or type(value["moves"]) is not list
            or any(key in value and type(value[key]) is not str
                   for key in optional)):
        raise FirstPlayableDeliveryBatchError("invalid bounded delivery job schema")
    return DeliveryJob(
        source=value["source"], archive=value["archive"],
        install=value["install"], save=value["save"], receipt=value["receipt"],
        manifest_sha256=value["manifest_sha256"],
        moves=tuple(value["moves"]),
        archive_sha256=value.get("archive_sha256"),
        save_sha256=value.get("save_sha256"),
        receipt_sha256=value.get("receipt_sha256"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app first-playable-batch",
        description="Publish or reverify 2-8 independently pinned original games",
    )
    parser.add_argument("--job", action="append", required=True,
                        help="bounded JSON job; repeat for each original game")
    parser.add_argument("--summary", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--resume", action="store_true")
    parser.add_argument("--expected-summary-sha256")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("trusted local operator acknowledgement required")
        if not MIN_GAMES <= len(args.job) <= MAX_GAMES:
            raise FirstPlayableDeliveryBatchError("2-8 original game jobs required")
        jobs = tuple(_parse_job(raw) for raw in args.job)
        if args.inspect:
            if args.expected_summary_sha256 is None:
                raise FirstPlayableDeliveryBatchError("independent cohort pin required")
            result = inspect_first_playable_delivery_batch(
                jobs, args.summary,
                expected_summary_sha256=args.expected_summary_sha256,
                authorized=True,
            )
        else:
            if args.expected_summary_sha256 is not None:
                raise FirstPlayableDeliveryBatchError("output pin is inspection-only")
            if args.resume:
                result = resume_first_playable_delivery_batch(
                    jobs, args.summary, authorized=True,
                )
            else:
                result = publish_first_playable_delivery_batch(
                    jobs, args.summary, authorized=True,
                )
    except (PermissionError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
