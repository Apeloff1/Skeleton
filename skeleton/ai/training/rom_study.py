"""ROM-wide local inventory and rights-gated *actual* emulator policy training.

Inventory never downloads ROMs, infers rights, executes an image or loads an
untrusted emulator.  Only a separately approved libretro core may execute exact
operator-authorized content inside the existing isolated host.  The existing
Jeeves emulator lab trains a *tabular Q policy*, not speaking model weights.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Callable

INVENTORY_SCHEMA = "skeleton.jeeves.rom_inventory.v1"
APPROVAL_SCHEMA = "skeleton.jeeves.rom_training_approval.v1"
BATCH_SCHEMA = "skeleton.jeeves.rom_training_batch.v1"
MAX_FILES = 100_000
MAX_DIRS = 10_000
MAX_PAGE = 128
MAX_APPROVALS = 20_000
MAX_LOCAL_ROM = 2 * 1024**3
MAX_REVIEW_BYTES = 4 * 1024 * 1024
_SHA = re.compile(r"^[0-9a-f]{64}$")
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,127}$")
_DISC_DESCRIPTORS = {".cue", ".ccd", ".gdi", ".m3u", ".toc", ".mds"}
_AMBIGUOUS = {".bin", ".rom", ".exe", ".com", ".iso", ".img", ".zip"}


class RomStudyError(ValueError):
    """Insufficient identity, review, native readiness or resource authority."""


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _safe_path(path: Path, *, directory: bool = False) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise RomStudyError("operator ROM path must be absolute without traversal")
    if not path.exists() and not path.is_symlink():
        raise RomStudyError("operator ROM path is unavailable")
    for item in (path, *path.parents):
        if item.is_symlink():
            raise RomStudyError("operator ROM path cannot traverse symlinks")
    if directory and not path.is_dir():
        raise RomStudyError("operator ROM collection is not a directory")
    return path


def _regular_identity(path: Path) -> tuple[int, int, int, int, int]:
    path = _safe_path(path)
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= MAX_LOCAL_ROM:
        raise RomStudyError("ROM candidate is not a bounded regular file")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _stream_identity(path: Path, *, expected: str | None = None,
                     include_prefix: bool = False) -> tuple[str, int, bytes]:
    before = _regular_identity(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        if _stat_tuple(os.fstat(fd)) != before:
            raise RomStudyError("ROM identity changed before reading")
        digest, prefix, count = hashlib.sha256(), bytearray(), 0
        with os.fdopen(os.dup(fd), "rb") as reader:
            while chunk := reader.read(1024 * 1024):
                count += len(chunk)
                if count > before[2]:
                    raise RomStudyError("ROM identity changed during hashing")
                digest.update(chunk)
                if include_prefix and len(prefix) < 65536:
                    prefix.extend(chunk[:65536 - len(prefix)])
        if (count != before[2] or _stat_tuple(os.fstat(fd)) != before
                or _regular_identity(path) != before):
            raise RomStudyError("ROM identity changed during hashing")
        actual = digest.hexdigest()
        if expected is not None and actual != expected:
            raise RomStudyError("ROM SHA-256 differs from operator-approved source")
        return actual, count, bytes(prefix)
    finally:
        os.close(fd)


def _stat_tuple(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _recognized_extensions() -> frozenset[str]:
    from skeleton.jeeves.game_emulator_catalog import (
        _CORE_TARGET_GROUPS, emulator_content_extensions,
    )
    extensions = set()
    for core_id in _CORE_TARGET_GROUPS:
        extensions.update(emulator_content_extensions(core_id))
    return frozenset(extensions)


def inventory_page(root: Path, *, cursor: str | None = None,
                   limit: int = 64) -> dict[str, Any]:
    """Deterministic bounded page with a continuation cursor; never reads content into RAM."""
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise RomStudyError("ROM census page size exceeds 1..128")
    root = _safe_path(root, directory=True)
    if cursor is not None and (not isinstance(cursor, str) or not cursor or len(cursor) > 4096
                               or cursor.startswith("/") or ".." in PurePosixPath(cursor).parts):
        raise RomStudyError("invalid ROM inventory continuation cursor")
    extensions = _recognized_extensions()
    candidates: list[str] = []
    dirs = 0

    def failed(exc: OSError) -> None:
        raise RomStudyError("ROM inventory cannot read an operator directory") from exc

    for base, folders, files in os.walk(root, topdown=True, followlinks=False, onerror=failed):
        dirs += 1
        if dirs > MAX_DIRS:
            raise RomStudyError("ROM inventory directory budget exceeded; scan separate roots")
        directory = Path(base)
        _safe_path(directory, directory=True)
        folders[:] = sorted(name for name in folders if not (directory / name).is_symlink())
        for name in files:
            path = directory / name
            if path.is_symlink():
                continue
            if path.suffix.lower() not in extensions:
                continue
            candidates.append(path.relative_to(root).as_posix())
            if len(candidates) > MAX_FILES:
                raise RomStudyError("ROM inventory file ceiling exceeded; partition roots")
    candidates.sort()
    start = 0
    if cursor is not None:
        from bisect import bisect_right
        start = bisect_right(candidates, cursor)
    page = candidates[start:start + limit]
    results = []
    for relative in page:
        path = root / relative
        try:
            digest, size, _ = _stream_identity(path)
            state = ("requires_companion_bundle" if path.suffix.lower() in _DISC_DESCRIPTORS
                     else "requires_explicit_platform" if path.suffix.lower() in _AMBIGUOUS
                     else "requires_operator_approval")
            results.append({
                "relative_path": relative, "file_sha256": digest, "size_bytes": size,
                "extension": path.suffix.lower(), "state": state,
                "authorized_for_training": False, "emulator_execution_checked": False,
            })
        except (OSError, RomStudyError) as exc:
            results.append({
                "relative_path": relative, "state": "identity_unavailable",
                "failure_type": type(exc).__name__, "authorized_for_training": False,
                "emulator_execution_checked": False,
            })
    next_cursor = page[-1] if start + len(page) < len(candidates) and page else None
    return {
        "schema_version": INVENTORY_SCHEMA,
        "root": str(root), "total_candidate_files": len(candidates),
        "candidate_extensions": len(extensions), "cursor": cursor,
        "next_cursor": next_cursor, "rows": results,
        "finished": next_cursor is None,
        "rom_bytes_exported": False, "training_executed": False,
    }


def _load_approvals(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    path = _safe_path(path)
    before = _regular_identity(path)
    if before[2] > MAX_REVIEW_BYTES:
        raise RomStudyError("ROM training approval registry exceeds capacity")
    with path.open("rb") as stream:
        raw = stream.read(MAX_REVIEW_BYTES + 1)
    if len(raw) != before[2] or _regular_identity(path) != before:
        raise RomStudyError("ROM training approval registry changed during load")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RomStudyError("duplicate approval JSON property")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               RomStudyError("nonfinite training approval")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise RomStudyError("invalid ROM training approval JSON") from exc
    if (not isinstance(value, dict) or set(value) != {"schema_version", "roms"}
            or value["schema_version"] != APPROVAL_SCHEMA
            or not isinstance(value["roms"], list) or len(value["roms"]) > MAX_APPROVALS):
        raise RomStudyError("ROM approval schema or entry count invalid")
    approved = {}
    for item in value["roms"]:
        if not isinstance(item, dict) or set(item) != {
            "sha256", "target_id", "core_id", "rights", "content_size_bytes"
        }:
            raise RomStudyError("ROM approval record schema differs")
        identity = item["sha256"]
        if not isinstance(identity, str) or not _SHA.fullmatch(identity) or identity in approved:
            raise RomStudyError("invalid or duplicated ROM approval identity")
        if (type(item["content_size_bytes"]) is not int
                or not 1 <= item["content_size_bytes"] <= MAX_LOCAL_ROM):
            raise RomStudyError("ROM approval needs exact admitted byte count")
        for field in ("target_id", "core_id"):
            if (not isinstance(item[field], str)
                    or not _SAFE_NAME.fullmatch(item[field])):
                raise RomStudyError("ROM approval target/core identity invalid")
        rights = item["rights"]
        if not isinstance(rights, dict) or set(rights) != {
            "rights_holder", "rights_basis", "review_id",
            "training_permitted", "human_reviewed"
        }:
            raise RomStudyError("ROM approval requires exact rights declaration")
        if rights["training_permitted"] is not True or rights["human_reviewed"] is not True:
            raise RomStudyError("unapproved ROMs cannot enter the training approval registry")
        if (any(not isinstance(rights.get(key), str) or len(rights[key].strip()) < 5
                for key in ("rights_holder", "rights_basis", "review_id"))
                or not rights["rights_basis"].startswith(
                    ("license:", "original:", "public-domain:"))):
            raise RomStudyError("ROM training permission needs independently reviewed rights basis")
        approved[identity] = item
    return approved, _hash(raw)


def _private_output(root: Path) -> Path:
    if root.is_symlink() or not root.is_absolute() or not root.is_dir():
        raise RomStudyError("ROM training output must be an existing absolute private directory")
    root = _safe_path(root, directory=True)
    info = root.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RomStudyError("ROM training output requires mode 0700 and current user ownership")
    return root


def _save_new(path: Path, document: dict[str, Any]) -> str:
    raw = _canonical(document) + b"\n"
    if len(raw) > 32 * 1024 * 1024:
        raise RomStudyError("ROM training evidence exceeds the receipt storage limit")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(raw)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return _hash(raw)


def _content_for_training(path: Path, *, sha: str, core: Any) -> Any:
    """Produce a privately materialized canonical content bundle; no source execution."""
    from skeleton.jeeves.game_emulator_catalog import (
        GameContentBundle, GameContentReference, load_game_content_for_core,
    )
    from skeleton.jeeves.game_emulator_host import prepare_emulator_content

    actual, size, prefix = _stream_identity(path, expected=sha, include_prefix=True)
    if size <= 16 * 1024 * 1024:
        # The canonical loader validates ZIP expansion and native core archive handling.
        before = _regular_identity(path)
        content = path.read_bytes()
        if _hash(content) != sha or _regular_identity(path) != before:
            raise RomStudyError("ROM changed before bounded core admission")
        bundle = load_game_content_for_core(core, content, path.name,
                                            expected_source_digest=sha)
        return prepare_emulator_content(bundle)
    if size > MAX_LOCAL_ROM or path.suffix.lower() in {".zip", ".dosz", *_DISC_DESCRIPTORS}:
        raise RomStudyError("large archives and multi-file discs require explicit existing bundle admission")
    reference = GameContentReference(
        path.name, size, sha, "operator-local://rom-training/" + sha, prefix,
    )
    bundle = GameContentBundle(path.name, {path.name: reference}, actual)
    expected = _regular_identity(path)

    def reader(item: Any):
        if item != reference or _regular_identity(path) != expected:
            raise RomStudyError("ROM reference or file changed before streaming")
        digest, count = hashlib.sha256(), 0
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            if _stat_tuple(os.fstat(fd)) != expected:
                raise RomStudyError("ROM identity changed before streaming")
            with os.fdopen(os.dup(fd), "rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    count += len(chunk)
                    digest.update(chunk)
                    if count > expected[2]:
                        raise RomStudyError("ROM grew during streaming")
                    yield chunk
            if (count != expected[2] or digest.hexdigest() != sha
                    or _stat_tuple(os.fstat(fd)) != expected
                    or _regular_identity(path) != expected):
                raise RomStudyError("ROM changed during streaming materialization")
        finally:
            os.close(fd)

    return prepare_emulator_content(bundle, reader=reader)




def _verify_existing_q_receipt(
    path: Path, *, source_sha: str, size: int, grant: dict[str, Any],
    approvals_digest: str, registry_digest: str,
) -> str:
    """Fail closed when an existing receipt is not the exact audited source.

    Existence alone is not a successful training outcome. The candidate's
    underlying policy and source episodes are revalidated before reuse, even
    when neural training was not requested. No ROM or core is reexecuted here.
    """
    from skeleton.jeeves.game_learning import _digest
    from skeleton.jeeves.game_emulator_neural_world import verify_neural_training_sources

    identity = _regular_identity(path)
    if identity[2] > 32 * 1024 * 1024:
        raise RomStudyError("saved ROM training receipt exceeds verification budget")
    with path.open("rb") as stream:
        raw = stream.read(32 * 1024 * 1024 + 1)
    if len(raw) != identity[2] or _regular_identity(path) != identity:
        raise RomStudyError("saved training receipt changed while revalidating")
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RomStudyError("saved ROM receipt is invalid JSON") from exc
    if (type(doc) is not dict
            or raw != _canonical(doc) + b"\\n"
            or doc.get("schema_version") != BATCH_SCHEMA
            or doc.get("training_kind") != "actual_replay_audited_tabular_q_policy"
            or doc.get("source_sha256") != source_sha
            or doc.get("source_size_bytes") != size
            or doc.get("core_id") != grant["core_id"]
            or doc.get("target_id") != grant["target_id"]
            or doc.get("approval_manifest_sha256") != approvals_digest
            or doc.get("registry_digest") != registry_digest
            or doc.get("neural_weights_updated") != 0
            or doc.get("production_weights_modified") is not False
            or doc.get("model_promotion_authorized") is not False):
        raise RomStudyError("existing receipt disagrees with approved training identity")
    report = doc.get("candidate_evidence")
    if type(report) is not dict or type(report.get("policy_snapshot")) is not dict:
        raise RomStudyError("existing policy evidence or learned Q snapshot is missing")
    lineage = report.get("source_lineage")
    if (type(lineage) is not dict
            or lineage.get("rights_acknowledged") is not True
            or lineage.get("source_sha256") != source_sha
            or lineage.get("rights_review_id") != grant["rights"]["review_id"]
            or lineage.get("rights_basis") != grant["rights"]["rights_basis"]
            or lineage.get("approvals_manifest_sha256") != approvals_digest
            or lineage.get("core_id") != grant["core_id"]
            or lineage.get("target_id") != grant["target_id"]):
        raise RomStudyError("saved receipt has different source or rights lineage")
    policy = report["policy_snapshot"]
    evidence = {key: value for key, value in report.items()
                if key != "policy_snapshot"}
    evidence["policy_snapshot_digest"] = policy.get("snapshot_digest")
    evidence["evidence_digest"] = _digest(evidence)
    validated, _, _, _ = verify_neural_training_sources(evidence, policy)
    if (len(validated) != report.get("actual_training_steps")
            or type(report.get("actual_q_table_updates")) is not int
            or report["actual_q_table_updates"] <= 0
            or report.get("actual_neural_parameter_updates") != 0):
        raise RomStudyError("saved Q training episode/update accounting is inconsistent")
    return _hash(raw)


def train_neural_candidate(
    q_receipt_path: Path, output_dir: Path, *,
    seed: int = 0, width: int = 12, epochs: int = 6,
) -> dict[str, Any]:
    """Fit actual *shadow world-model* parameters from audited ROM Q evidence.

    The original ROM and Q receipt are never overwritten. The network
    predicts numerical one-step telemetry, NOT dialogue, game mastery, or
    production Jeeves weights. Actual source replay is verified again before
    the optimizer starts.
    """
    from skeleton.jeeves.game_learning import _digest
    from skeleton.jeeves.game_emulator_neural_world import (
        NeuralWorldConfig, train_neural_world_from_evidence,
        validate_neural_world_checkpoint, verify_neural_training_sources,
    )
    output_dir = _private_output(output_dir)
    q_receipt_path = _safe_path(q_receipt_path)
    if q_receipt_path.parent != output_dir:
        raise RomStudyError("neural source receipt must come from the private training directory")
    before = _regular_identity(q_receipt_path)
    if before[2] > 32 * 1024 * 1024:
        raise RomStudyError("ROM neural source receipt is oversized")
    with q_receipt_path.open("rb") as stream:
        raw = stream.read(32 * 1024 * 1024 + 1)
    if len(raw) != before[2] or _regular_identity(q_receipt_path) != before:
        raise RomStudyError("ROM Q receipt changed during neural intake")
    try:
        document = json.loads(raw)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise RomStudyError("invalid ROM Q evidence JSON") from exc
    if (not isinstance(document, dict) or document.get("schema_version") != BATCH_SCHEMA
            or document.get("training_kind") != "actual_replay_audited_tabular_q_policy"
            or document.get("neural_weights_updated") != 0
            or document.get("production_weights_modified") is not False
            or not isinstance(document.get("candidate_evidence"), dict)):
        raise RomStudyError("neural model requires a genuine source Q training receipt")
    evidence_raw = document["candidate_evidence"]
    policy = evidence_raw.get("policy_snapshot")
    if not isinstance(policy, dict):
        raise RomStudyError("neural model source policy is unavailable")
    evidence = {key: value for key, value in evidence_raw.items()
                if key != "policy_snapshot"}
    evidence["policy_snapshot_digest"] = policy.get("snapshot_digest")
    evidence["evidence_digest"] = _digest(evidence)
    validated, _, _, source_digest = verify_neural_training_sources(evidence, policy)
    if len(validated) != evidence.get("actual_training_steps"):
        raise RomStudyError("neural candidate source and replay episode counts differ")
    config = NeuralWorldConfig(
        seed=seed, holdout_seed=(seed + 1) % (2**63),
        width=width, epochs=epochs, minibatch=8,
        max_samples=512, max_compute_units=8_000_000,
    )
    selection = _hash(_canonical({
        "q_receipt_sha256": _hash(raw), "config": {
            "seed": seed, "width": width, "epochs": epochs,
        }
    }))
    source_sha = document["source_sha256"]
    if not isinstance(source_sha, str) or not _SHA.fullmatch(source_sha):
        raise RomStudyError("neural candidate source identity invalid")
    name = "rom-world-" + source_sha[:16] + "-" + selection[:16] + ".json"
    destination = output_dir / name
    if destination.exists() or destination.is_symlink():
        return {
            "state": "previous_neural_candidate_receipt_exists",
            "candidate_name": name, "neural_training_reexecuted": False,
        }
    model, measurements = train_neural_world_from_evidence(
        evidence, policy, config=config,
    )
    validate_neural_world_checkpoint(model)
    if (measurements["world_model_digest"] != model["model_digest"]
            or model["real_optimizer_steps"] < 1
            or model["actual_neural_parameter_training_executed"] is not True
            or model["production_model_promotion_authorized"] is not False
            or model["not_a_jeeves_transformer_update"] is not True):
        raise RomStudyError("neural optimizer or model custody check failed")
    digest = _save_new(destination, {
        "schema_version": "skeleton.jeeves.rom_neural_candidate.v1",
        "rom_sha256": source_sha, "source_q_receipt_sha256": _hash(raw),
        "source_emulator_report_digest": source_digest,
        "model": model, "heldout_measurements": measurements,
        "production_jeeves_weights_updated": False,
        "candidate_only_no_auto_promotion": True,
    })
    return {
        "state": "shadow_neural_candidate_trained",
        "candidate_name": name, "candidate_sha256": digest,
        "real_neural_optimizer_steps": model["real_optimizer_steps"],
        "heldout_status": measurements["candidate_status"],
        "neural_training_reexecuted": True,
    }


def train_page(
    root: Path, approvals_path: Path, output_dir: Path, *,
    cursor: str | None = None, limit: int = 32,
    runs: int = 12, steps: int = 24, seed: int = 0,
    train_neural: bool = False,
    cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Run every eligible ROM on this page; persist per-ROM results before continuing.

    A page may include blocked/unlicensed/unsupported files. These are audited,
    NEVER silently treated as completed. Reissue with the next_cursor to continue.
    """
    from skeleton.jeeves.game_emulator_catalog import (
        GameEmulatorRegistry, emulator_content_admission,
    )
    from skeleton.jeeves.game_emulator_training_lab import (
        EmulatorLabConfig, run_emulator_training_lab,
    )
    from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest

    if type(train_neural) is not bool:
        raise RomStudyError("neural candidate flag must be a boolean")
    if (type(runs) is not int or not 1 <= runs <= 32
            or type(steps) is not int or not 1 <= steps <= 128
            or type(seed) is not int or not 0 <= seed <= 2**63 - 1):
        raise RomStudyError("bounded ROM training runs/steps/seed required")
    page = inventory_page(root, cursor=cursor, limit=limit)
    approvals, approvals_digest = _load_approvals(approvals_path)
    output_dir = _private_output(output_dir)
    registry = GameEmulatorRegistry.from_environment()
    results: list[dict[str, Any]] = []
    for row in page["rows"]:
        if cancel is not None and cancel():
            raise RomStudyError("ROM training campaign cancelled at a page boundary")
        identity = row.get("file_sha256")
        summary = {"relative_path": row["relative_path"],
                   "source_sha256": identity, "state": "not_admitted"}
        if not identity:
            summary["state"] = "source_identity_unavailable"
            results.append(summary)
            continue
        grant = approvals.get(identity)
        if grant is None:
            summary["state"] = "no_training_rights_review"
            results.append(summary)
            continue
        if grant["content_size_bytes"] != row["size_bytes"]:
            summary["state"] = "approval_content_size_mismatch"
            results.append(summary)
            continue
        if row["extension"] in _DISC_DESCRIPTORS:
            summary["state"] = "explicit_multifile_bundle_required"
            results.append(summary)
            continue
        # File extension hints cannot authorize an emulator without an approved
        # exact core binding. The worker repeats all content and firmware checks.
        try:
            core = registry.resolve_core(grant["core_id"])
            if grant["target_id"] not in core.target_ids:
                raise RomStudyError("ROM approval target not covered by approved core")
            admission = emulator_content_admission(core.core_id)
            if row["extension"] not in admission["admitted_entrypoint_extensions"]:
                raise RomStudyError("ROM extension has no approved core entrypoint")
            run_identity = _hash(_canonical({
                "source_sha256": identity, "grant": grant,
                "approvals_manifest_sha256": approvals_digest,
                "registry_digest": registry.registry_digest,
                "runs": runs, "steps": steps, "seed": seed,
            }))
            filename = "rom-" + identity[:16] + "-" + run_identity[:16] + ".json"
            target = output_dir / filename
            if target.exists() or target.is_symlink():
                summary["receipt_sha256"] = _verify_existing_q_receipt(
                    target, source_sha=identity, size=row["size_bytes"],
                    grant=grant, approvals_digest=approvals_digest,
                    registry_digest=registry.registry_digest,
                )
                summary["state"] = "previous_receipt_exists_not_reexecuted"
                summary["prior_training_receipt_verified"] = True
                summary["receipt_name"] = filename
                if train_neural:
                    try:
                        summary["neural_candidate"] = train_neural_candidate(
                            target, output_dir, seed=seed,
                        )
                    except (ValueError, OSError, RuntimeError) as exc:
                        summary["neural_candidate"] = {
                            "state": "neural_candidate_blocked",
                            "failure_type": type(exc).__name__,
                            "failure_reason": str(exc)[:200],
                        }
                results.append(summary)
                continue
            prepared = _content_for_training(
                _safe_path(Path(page["root"]) / row["relative_path"]),
                sha=identity, core=core,
            )
            try:
                request = GameEnvironmentRequest(
                    kind="libretro", target_id=grant["target_id"],
                    core_id=core.core_id, registry_digest=registry.registry_digest,
                    content=prepared.as_dict(), filename=Path(row["relative_path"]).name,
                    max_steps=steps,
                )
                config = EmulatorLabConfig(
                    max_runs=runs, steps_per_run=steps, stagnation_runs=10, seed=seed,
                )
                evidence = run_emulator_training_lab(
                    request, config=config,
                    policy_id="rom-training-" + identity[:16],
                    source_lineage={
                        "rights_acknowledged": True, "source_sha256": identity,
                        "rights_review_id": grant["rights"]["review_id"],
                        "rights_basis": grant["rights"]["rights_basis"],
                        "core_id": core.core_id, "target_id": grant["target_id"],
                        "approvals_manifest_sha256": approvals_digest,
                    },
                    cancel=cancel,
                )
            finally:
                prepared.close()
            receipt = {
                "schema_version": BATCH_SCHEMA, "source_sha256": identity,
                "source_size_bytes": row["size_bytes"], "target_id": grant["target_id"],
                "core_id": core.core_id, "registry_digest": registry.registry_digest,
                "approval_manifest_sha256": approvals_digest,
                "training_kind": "actual_replay_audited_tabular_q_policy",
                "neural_weights_updated": 0, "production_weights_modified": False,
                "model_promotion_authorized": False,
                "candidate_evidence": evidence,
            }
            receipt_digest = _save_new(target, receipt)
            summary.update({
                "state": "q_policy_trained_with_receipt",
                "actual_q_table_updates": evidence["actual_q_table_updates"],
                "measured_steps": evidence["actual_training_steps"],
                "receipt_name": filename, "receipt_sha256": receipt_digest,
            })
            if train_neural:
                try:
                    summary["neural_candidate"] = train_neural_candidate(
                        target, output_dir, seed=seed,
                    )
                except (ValueError, OSError, RuntimeError) as exc:
                    summary["neural_candidate"] = {
                        "state": "neural_candidate_blocked",
                        "failure_type": type(exc).__name__,
                        "failure_reason": str(exc)[:200],
                    }
        except (ValueError, OSError, RuntimeError, ImportError) as exc:
            summary["state"] = "emulator_training_blocked"
            summary["failure_type"] = type(exc).__name__
            summary["failure_reason"] = str(exc)[:200]
        results.append(summary)
    return {
        "schema_version": BATCH_SCHEMA,
        "inventory_cursor": page["cursor"], "next_cursor": page["next_cursor"],
        "finished_inventory": page["finished"],
        "inventory_candidates": page["total_candidate_files"],
        "approval_manifest_sha256": approvals_digest,
        "page_results": results,
        "q_policy_training_completed": sum(
            row["state"] == "q_policy_trained_with_receipt" for row in results),
        "shadow_neural_candidates_trained": sum(
            row.get("neural_candidate", {}).get("state") ==
            "shadow_neural_candidate_trained" for row in results),
        "blocked_or_unreviewed": sum(
            row["state"] not in ("q_policy_trained_with_receipt",
                                 "previous_receipt_exists_not_reexecuted")
            for row in results),
        "actual_jeeves_weight_training": False,
        "production_weights_modified": False,
        "rom_content_exported": False,
    }
