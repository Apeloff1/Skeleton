"""Operator-controlled, restart-safe custody for serial native Jeeves work plans.

The canonical SQLite durable runtime remains the ONLY authoritative execution
record. This module saves the operator's exact original input/task budgets and
unique preallocated work IDs to one *explicitly chosen* private regular file,
then restores it for read-only checkpoint inspection/replay after a cold restart.
It cannot automatically rerun or resume imported tasks, generate new IDs from
a saved plan, authorize model/tool access, or change a SQLite transaction.

All filesystem operations are POSIX descriptor-anchored. The destination
must be under a preexisting owner-private 0700 directory; a new file is
created exclusively with 0600, no symlinks or hardlinks, never overwritten.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
from hashlib import sha256

from .desktop_batch_work import (
    BatchHold, DurableBatchItem, DurableBatchPlan, _canonical,
    MAX_BATCH_ITEMS,
)

SCHEMA = "jeeves.desktop.private-batch-recovery.v1"
MAX_RECOVERY_BYTES = 262144


class BatchRecoveryHold(ValueError):
    """A saved batch or live read-only reconciliation lacks exact authority."""


def _private_path(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)):
        raise BatchRecoveryHold("explicit private batch recovery path required")
    path = Path(value)
    if (
        not path.is_absolute() or ".." in path.parts or "\x00" in str(path)
        or not path.name or path.name in (".", "..")
        or len(path.name.encode("utf-8", "strict")) > 180
    ):
        raise BatchRecoveryHold("noncanonical absolute private recovery file path")
    return path


def _open_root(path: Path) -> int:
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.path_policy import (
        open_private_root,
    )
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import SpineError
    try:
        return open_private_root(path)
    except (OSError, ValueError, SpineError) as exc:
        raise BatchRecoveryHold("operator recovery root must be owned mode 0700") from exc


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )


def _original_root(path: Path, root_fd: int) -> None:
    """Detect directory replacement between operator selection and I/O."""
    try:
        current = os.stat(path.parent, follow_symlinks=False)
        pinned = os.fstat(root_fd)
    except OSError as exc:
        raise BatchRecoveryHold("private batch recovery directory unavailable") from exc
    if (
        not stat.S_ISDIR(current.st_mode)
        or current.st_dev != pinned.st_dev
        or current.st_ino != pinned.st_ino
        or current.st_uid != pinned.st_uid
        or current.st_mode & 0o077
    ):
        raise BatchRecoveryHold("private batch recovery directory replaced")


def _file_stat(info: os.stat_result, *, expected_size: int | None = None) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_mode & 0o077
        or info.st_uid != os.getuid()
        or not 1 <= info.st_size <= MAX_RECOVERY_BYTES
        or (expected_size is not None and info.st_size != expected_size)
    ):
        raise BatchRecoveryHold("recovery file owner, type or bounded size invalid")


def _unique(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise BatchRecoveryHold("ambiguous recovery key")
        seen[key] = value
    return seen


def _invalid_constant(_):
    raise BatchRecoveryHold("nonfinite recovery JSON denied")


def serialize_recovery(plan: DurableBatchPlan) -> bytes:
    if type(plan) is not DurableBatchPlan:
        raise BatchRecoveryHold("typed immutable durable work plan required")
    plan.__post_init__()
    payload = _canonical({
        "schema": SCHEMA,
        "manifest_sha256": plan.manifest_sha256,
        "items": [{
            "title": item.title,
            "task": item.task,
            "run_id": item.run_id,
            "maximum_steps": item.maximum_steps,
            "maximum_model_calls": item.maximum_model_calls,
            "maximum_wall_seconds": item.maximum_wall_seconds,
        } for item in plan.items],
    })
    if not 1 <= len(payload) <= MAX_RECOVERY_BYTES:
        raise BatchRecoveryHold("private source batch exceeds recovery byte budget")
    return payload


def parse_recovery(raw: bytes, *, expected_manifest_sha256: str) -> DurableBatchPlan:
    """Restore EXACT original IDs; never invent new model work on import."""
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_RECOVERY_BYTES:
        raise BatchRecoveryHold("bounded private recovery bytes required")
    if (
        type(expected_manifest_sha256) is not str
        or len(expected_manifest_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in expected_manifest_sha256)
    ):
        raise BatchRecoveryHold("explicit full operator recovery SHA-256 required")
    try:
        data = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_unique, parse_constant=_invalid_constant,
        )
    except (UnicodeError, TypeError, ValueError) as exc:
        raise BatchRecoveryHold("invalid exact recovery JSON") from exc
    if (
        type(data) is not dict
        or set(data) != {"schema", "manifest_sha256", "items"}
        or data["schema"] != SCHEMA
        or data["manifest_sha256"] != expected_manifest_sha256
        or type(data["items"]) is not list
        or not 1 <= len(data["items"]) <= MAX_BATCH_ITEMS
    ):
        raise BatchRecoveryHold("saved source batch or approval digest mismatched")
    restored = []
    fields = {
        "title", "task", "run_id", "maximum_steps",
        "maximum_model_calls", "maximum_wall_seconds",
    }
    for item in data["items"]:
        if type(item) is not dict or set(item) != fields:
            raise BatchRecoveryHold("saved private batch has unapproved task fields")
        try:
            entry = DurableBatchItem(**item)
        except (ValueError, TypeError, BatchHold) as exc:
            raise BatchRecoveryHold("invalid original durable work identity") from exc
        if (
            any(ch not in "0123456789abcdef" for ch in entry.run_id[5:])
            or len(entry.run_id[5:]) != 32
        ):
            raise BatchRecoveryHold("run ID not generated by canonical native owner")
        restored.append(entry)
    exact = tuple(restored)
    plan = DurableBatchPlan(
        manifest_sha256=expected_manifest_sha256,
        items=exact,
        aggregate_prompt_bytes=sum(len(i.task.encode("utf-8", "strict")) for i in exact),
        aggregate_model_calls=sum(i.maximum_model_calls for i in exact),
        aggregate_wall_seconds=sum(i.maximum_wall_seconds for i in exact),
    )
    if serialize_recovery(plan) != raw:
        raise BatchRecoveryHold("saved batch is not canonical exact UTF-8")
    return plan


def save_reviewed_recovery(
    plan: DurableBatchPlan,
    path: str | Path,
    *,
    expected_manifest_sha256: str,
    approve_private_export: bool,
) -> dict[str, object]:
    """Exclusive private-file creation, never overwrite an earlier recovery."""
    if (
        approve_private_export is not True
        or type(expected_manifest_sha256) is not str
        or type(plan) is not DurableBatchPlan
        or expected_manifest_sha256 != plan.manifest_sha256
    ):
        raise BatchRecoveryHold("full reviewed batch digest and private export consent required")
    raw = serialize_recovery(plan)
    target = _private_path(path)
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise BatchRecoveryHold("POSIX/WSL2 descriptor-anchored private recovery only")
    parent_fd = _open_root(target.parent)
    fd = None
    created = None
    try:
        _original_root(target, parent_fd)
        fd = os.open(
            target.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            0o600, dir_fd=parent_fd,
        )
        created = os.fstat(fd)
        if (
            not stat.S_ISREG(created.st_mode)
            or created.st_nlink != 1 or created.st_uid != os.getuid()
            or created.st_mode & 0o077
        ):
            raise BatchRecoveryHold("untrusted new private recovery file")
        used = 0
        while used < len(raw):
            written = os.write(fd, raw[used:used + 8192])
            if type(written) is not int or written <= 0:
                raise BatchRecoveryHold("short private recovery publication")
            used += written
        os.fsync(fd)
        finished = os.fstat(fd)
        _file_stat(finished, expected_size=len(raw))
        current = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if _identity(finished) != _identity(current):
            raise BatchRecoveryHold("private batch path replaced after publication")
        _original_root(target, parent_fd)
        os.fsync(parent_fd)
        return {
            "schema": "jeeves.desktop.private-recovery-written.v1",
            "manifest_sha256": plan.manifest_sha256,
            "task_count": len(plan.items),
            "file_sha256": sha256(raw).hexdigest(),
            "private_bytes": len(raw),
            "owner_private_file": True,
            "automatic_resume": False,
            "native_inference_started": False,
            "release_certified": False,
        }
    except BaseException:
        if created is not None:
            try:
                current = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
                if current.st_dev == created.st_dev and current.st_ino == created.st_ino:
                    os.unlink(target.name, dir_fd=parent_fd)
                    os.fsync(parent_fd)
            except OSError:
                pass
        raise
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent_fd)


def load_private_recovery(
    path: str | Path, *, expected_manifest_sha256: str,
) -> DurableBatchPlan:
    """Read-only cold reopen of the original plan, not execution approval."""
    target = _private_path(path)
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise BatchRecoveryHold("POSIX/WSL2 private recovery source required")
    parent_fd = _open_root(target.parent)
    fd = None
    try:
        _original_root(target, parent_fd)
        fd = os.open(
            target.name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_fd,
        )
        before = os.fstat(fd)
        _file_stat(before)
        raw = bytearray()
        while len(raw) < before.st_size + 1:
            part = os.read(fd, min(8192, before.st_size + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(fd)
        current = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            len(raw) != before.st_size
            or _identity(before) != _identity(after)
            or _identity(after) != _identity(current)
        ):
            raise BatchRecoveryHold("private saved batch changed during exact read")
        _original_root(target, parent_fd)
        return parse_recovery(bytes(raw), expected_manifest_sha256=expected_manifest_sha256)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent_fd)


@dataclass(frozen=True, slots=True)
class RecoveredWorkReceipt:
    manifest_sha256: str
    run_id: str
    action: str
    status: str
    model_sha256: str
    output_sha256: str | None
    native_generation_executed: bool = False
    automatic_retry: bool = False

    def to_public(self):
        return {
            "schema": "jeeves.desktop.private-work-reconciliation.v1",
            "manifest_sha256": self.manifest_sha256,
            "run_id": self.run_id,
            "action": self.action,
            "status": self.status,
            "model_sha256": self.model_sha256,
            "output_sha256": self.output_sha256,
            "native_generation_executed": False,
            "automatic_retry": False,
            "release_certified": False,
        }


def inspect_original_work(
    worker: object,
    plan: DurableBatchPlan,
    *,
    sequence: int,
    action: str,
    expected_manifest_sha256: str,
    approved_run_id: str,
) -> RecoveredWorkReceipt:
    """Explicit inspection or sealed replay via the EXISTING native protocol.

    Imported work orders can NEVER be started/resumed here. The exact model
    identity and SQLite checkpoint authority are checked by the bridge and
    canonical NativeDurableJeevesAgent. This adapter denies any generation
    flag and never publishes the private answer.
    """
    if type(plan) is not DurableBatchPlan:
        raise BatchRecoveryHold("restored immutable plan required")
    plan.__post_init__()
    if (
        type(expected_manifest_sha256) is not str
        or expected_manifest_sha256 != plan.manifest_sha256
        or type(action) is not str or action not in ("inspect", "replay")
        or type(sequence) is not int or not 1 <= sequence <= len(plan.items)
    ):
        raise BatchRecoveryHold("explicit read-only exact work approval required")
    item = plan.items[sequence - 1]
    if type(approved_run_id) is not str or approved_run_id != item.run_id:
        raise BatchRecoveryHold("selected original work ID changed")
    if (
        getattr(worker, "connected", False) is not True
        or not callable(getattr(worker, "request", None))
        or not callable(getattr(worker, "exclusive_batch", None))
    ):
        raise BatchRecoveryHold("live source-fenced native SQLite worker required")

    with worker.exclusive_batch(plan.manifest_sha256):
        result = worker.request(
            "durable", action=action, run_id=item.run_id, prompt=item.task,
            maximum_steps=item.maximum_steps,
            maximum_model_calls=item.maximum_model_calls,
            maximum_wall_seconds=item.maximum_wall_seconds,
        )
    expected = {
        "inspect": ("durable-work-inspected", "inspected"),
        "replay": ("durable-work-replayed", "terminal-replayed"),
    }[action]
    record = result.get("durable") if type(result) is dict else None
    if (
        type(record) is not dict
        or result.get("status") != expected[0]
        or result.get("run_id") != item.run_id
        or record.get("schema") != "jeeves.desktop.durable-work.v1"
        or record.get("action") != action
        or record.get("status") != expected[1]
        or record.get("run_id") != item.run_id
        or record.get("native_generation_executed") is not False
        or record.get("automatic_resume") is not False
        or record.get("release_certified") is not False
        or record.get("device_qualified") is not False
    ):
        raise BatchRecoveryHold("replayed SQLite work identity or source custody absent")
    source = record.get("model_sha256")
    if (
        type(source) is not str
        or len(source) != 64
        or any(ch not in "0123456789abcdef" for ch in source)
    ):
        raise BatchRecoveryHold("exact installed model identity missing")
    receipt_sha = None
    if action == "replay":
        if (
            record.get("success") is not True
            or record.get("replayed_without_native_generation") is not True
            or type(record.get("output_sha256")) is not str
            or len(record["output_sha256"]) != 64
        ):
            raise BatchRecoveryHold("sealed terminal result not replayed without inference")
        receipt_sha = record["output_sha256"]
    return RecoveredWorkReceipt(
        plan.manifest_sha256, item.run_id, action,
        expected[1], source, receipt_sha,
    )


__all__ = [
    "SCHEMA", "BatchRecoveryHold", "RecoveredWorkReceipt",
    "serialize_recovery", "parse_recovery", "save_reviewed_recovery",
    "load_private_recovery", "inspect_original_work",
]
