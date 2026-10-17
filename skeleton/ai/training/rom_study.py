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


def verified_rom_receipt(path: Path, *, expected_source_sha256: str,
                         expected_run_identity: str | None = None) -> dict[str, Any]:
    """Read a previously committed receipt; never treat filename as evidence."""
    source = _safe_path(path)
    before = _regular_identity(source)
    if before[2] > 32 * 1024 * 1024:
        raise RomStudyError("ROM training receipt exceeds maximum size")
    fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        if _stat_tuple(os.fstat(fd)) != before:
            raise RomStudyError("training receipt identity changed")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(32 * 1024 * 1024 + 1)
        if len(raw) != before[2] or _stat_tuple(os.fstat(fd)) != before:
            raise RomStudyError("training receipt changed during read")
    finally:
        os.close(fd)
    if _regular_identity(source) != before:
        raise RomStudyError("training receipt changed after read")
    def no_duplicates(items):
        found = {}
        for key, value in items:
            if key in found:
                raise RomStudyError("duplicate ROM receipt property")
            found[key] = value
        return found
    try:
        row = json.loads(raw, object_pairs_hook=no_duplicates,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             RomStudyError("nonfinite ROM receipt value")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise RomStudyError("invalid ROM training receipt JSON") from exc
    if (not isinstance(row, dict)
            or row.get("schema_version") != BATCH_SCHEMA
            or row.get("source_sha256") != expected_source_sha256
            or row.get("production_weights_modified") is not False
            or row.get("model_promotion_authorized") is not False
            or row.get("neural_weights_updated") != 0):
        raise RomStudyError("ROM receipt disagrees with source and learning boundary")
    if expected_run_identity is not None and row.get("run_identity") != expected_run_identity:
        raise RomStudyError("ROM receipt is from a different training configuration")
    evidence = row.get("candidate_evidence")
    neural = row.get("neural_world", {"status": "not_requested"})
    if not isinstance(neural, dict) or neural.get("production_jeeves_weight_updates") not in (0, None):
        raise RomStudyError("ROM receipt contains unauthorized production neural updates")
    if neural.get("status") == "candidate_trained_requires_independent_review":
        from skeleton.jeeves.game_emulator_neural_world import validate_neural_world_checkpoint
        model = neural.get("neural_model")
        if not isinstance(model, dict) or model.get("model_digest") != neural.get("candidate_model_sha256"):
            raise RomStudyError("ROM receipt neural candidate identity changed")
        try:
            validate_neural_world_checkpoint(model)
        except ValueError as exc:
            raise RomStudyError("ROM receipt neural checkpoint validation failed") from exc
    from skeleton.jeeves.game_learning import _digest
    if (not isinstance(evidence, dict)
            or evidence.get("report_digest") != _digest({
                k: v for k, v in evidence.items() if k != "report_digest"
            })
            or evidence.get("actual_neural_parameter_updates") != 0
            or type(evidence.get("actual_q_table_updates")) is not int
            or evidence["actual_q_table_updates"] < 0):
        raise RomStudyError("ROM receipt lacks authentic replay-lab evidence structure")
    return {
        "source_sha256": row["source_sha256"],
        "run_identity": row.get("run_identity"),
        "receipt_sha256": _hash(raw),
        "actual_q_table_updates": evidence["actual_q_table_updates"],
        "actual_training_steps": evidence.get("actual_training_steps"),
        "neural_weights_updated": 0,
        "model_promotion_authorized": False,
    }


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


def train_page(
    root: Path, approvals_path: Path, output_dir: Path, *,
    cursor: str | None = None, limit: int = 32,
    runs: int = 12, steps: int = 24, seed: int = 0,
    neural_world: bool = False, neural_epochs: int = 4, neural_width: int = 8,
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

    if (type(runs) is not int or not 1 <= runs <= 32
            or type(steps) is not int or not 1 <= steps <= 128
            or type(seed) is not int or not 0 <= seed <= 2**63 - 1
            or type(neural_world) is not bool
            or type(neural_epochs) is not int or not 1 <= neural_epochs <= 16
            or type(neural_width) is not int or not 4 <= neural_width <= 32):
        raise RomStudyError("bounded ROM Q/neural training configuration required")
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
                "neural_world": neural_world,
                "neural_epochs": neural_epochs, "neural_width": neural_width,
            }))
            filename = "rom-" + identity[:16] + "-" + run_identity[:16] + ".json"
            target = output_dir / filename
            if target.exists() or target.is_symlink():
                verified = verified_rom_receipt(
                    target, expected_source_sha256=identity,
                    expected_run_identity=run_identity,
                )
                summary["state"] = "previous_verified_receipt_no_reexecution"
                summary["receipt_name"] = filename
                summary["receipt_sha256"] = verified["receipt_sha256"]
                summary["actual_q_table_updates"] = verified["actual_q_table_updates"]
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
            neural = {
                "status": "not_requested",
                "actual_candidate_optimizer_steps": 0,
                "production_jeeves_weight_updates": 0,
            }
            if neural_world:
                # Only replay-verified, independently episode-split candidate
                # examples can reach this existing neural optimizer.
                from skeleton.jeeves.game_emulator_neural_world import (
                    NeuralWorldConfig, train_neural_world_from_evidence,
                    validate_neural_world_checkpoint,
                )
                from skeleton.jeeves.game_learning import _digest
                parent = evidence["policy_snapshot"]
                source = {k: value for k, value in evidence.items()
                          if k != "policy_snapshot"}
                source["policy_snapshot_digest"] = parent["snapshot_digest"]
                source["evidence_digest"] = _digest(source)
                try:
                    neural_model, neural_report = train_neural_world_from_evidence(
                        source, parent,
                        config=NeuralWorldConfig(
                            seed=seed, holdout_seed=(seed + 1) % (2**63),
                            width=neural_width, epochs=neural_epochs,
                            minibatch=8, max_samples=512,
                            max_compute_units=8_000_000,
                        ),
                        cancel=cancel,
                    )
                    validate_neural_world_checkpoint(neural_model)
                    neural = {
                        "status": "candidate_trained_requires_independent_review",
                        "actual_candidate_optimizer_steps": neural_model["real_optimizer_steps"],
                        "candidate_model_sha256": neural_model["model_digest"],
                        "heldout_gain_measured": (
                            neural_report["candidate_status"] == "candidate_predictive_gain_measured"
                        ),
                        "neural_model": neural_model, "training_report": neural_report,
                        "production_jeeves_weight_updates": 0,
                        "production_model_promotion_authorized": False,
                    }
                except (ValueError, RuntimeError) as exc:
                    # Q learning remains measured. Neural qualification is a
                    # separate status, not silently marked as successful.
                    neural = {
                        "status": "candidate_training_blocked",
                        "failure_type": type(exc).__name__,
                        "failure_reason": str(exc)[:200],
                        "actual_candidate_optimizer_steps": 0,
                        "production_jeeves_weight_updates": 0,
                        "production_model_promotion_authorized": False,
                    }
            receipt = {
                "schema_version": BATCH_SCHEMA,
                "run_identity": run_identity,
                "source_sha256": identity,
                "source_size_bytes": row["size_bytes"], "target_id": grant["target_id"],
                "core_id": core.core_id, "registry_digest": registry.registry_digest,
                "approval_manifest_sha256": approvals_digest,
                "training_kind": "actual_replay_audited_tabular_q_policy",
                "neural_weights_updated": 0, "production_weights_modified": False,
                "model_promotion_authorized": False,
                "neural_world": neural, "candidate_evidence": evidence,
            }
            receipt_digest = _save_new(target, receipt)
            summary.update({
                "state": ("q_policy_updated_with_receipt"
                          if evidence["actual_q_table_updates"] > 0
                          else "q_policy_executed_no_updates"),
                "actual_q_table_updates": evidence["actual_q_table_updates"],
                "measured_steps": evidence["actual_training_steps"],
                "receipt_name": filename, "receipt_sha256": receipt_digest,
                "neural_world_status": neural["status"],
                "neural_candidate_optimizer_steps": neural["actual_candidate_optimizer_steps"],
            })
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
            row["state"] == "q_policy_updated_with_receipt" for row in results),
        "q_policy_runs_without_updates": sum(
            row["state"] == "q_policy_executed_no_updates" for row in results),
        "blocked_or_unreviewed": sum(
            row["state"] not in ("q_policy_updated_with_receipt",
                                 "q_policy_executed_no_updates",
                                 "previous_verified_receipt_no_reexecution")
            for row in results),
        "neural_candidate_training_completed": sum(
            row.get("neural_world_status") == "candidate_trained_requires_independent_review"
            for row in results),
        "actual_jeeves_weight_training": False,
        "production_weights_modified": False,
        "rom_content_exported": False,
    }
