"""Non-authoritative crash-evidence journal for serial offline Jeeves campaigns.

The ONLY authoritative native-operation ledger remains the existing SQLite
session owner. A new 0600 journal records a durable intent BEFORE a GGUF call
and the already-cold-verified escrow receipt AFTER it. Crash/timeout between
those two entries is permanently uncertain: never auto-retry or adopt an
unverified model outcome. The journal does not grant recovery authority.
"""
from __future__ import annotations

import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

from .desktop_patch_export import _pinned_private_directory, _identical_parent
from .desktop_workspace import _canonical

SCHEMA = "jeeves.desktop.private-native-campaign-journal.v1"
MAX_JOURNAL_BYTES = 196608
MAX_RECORD_BYTES = 8192
MAX_RECORDS = 44
_STATUS = frozenset(("begin", "attempt", "saved", "halt", "complete"))
_FIELDS = frozenset((
    "schema", "sequence", "previous_sha256", "event", "manifest_sha256",
    "task_id", "evidence", "event_sha256",
))
_FLAGS = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
_READ = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)


class NativeCampaignJournalHold(ValueError):
    """Private durable campaign evidence is missing, ambiguous, or changed."""


def _sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def _digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _path(value: object, original_project_root: str) -> Path:
    if (
        type(value) is not str or not value or len(value) > 4096
        or "\x00" in value or not Path(value).is_absolute()
        or ".." in Path(value).parts
        or not value.endswith(".jeeves-campaign.jsonl")
        or not 1 <= len(Path(value).name) <= 128
    ):
        raise NativeCampaignJournalHold("canonical private campaign journal required")
    path = Path(value)
    project = Path(original_project_root)
    if (
        not project.is_absolute() or ".." in project.parts
        or path.is_relative_to(project) or project.is_relative_to(path)
    ):
        raise NativeCampaignJournalHold("private audit must remain outside project")
    return path


def _inode(info: os.stat_result) -> tuple[int, int, int, int]:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or info.st_nlink != 1
    ):
        raise NativeCampaignJournalHold("campaign audit inode no longer private")
    return info.st_dev, info.st_ino, info.st_mode, info.st_nlink


def _same(path: Path, parent: int, fd: int) -> None:
    _identical_parent(path, parent)
    current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
    if _inode(current) != _inode(os.fstat(fd)):
        raise NativeCampaignJournalHold("campaign audit entry was replaced")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise NativeCampaignJournalHold("duplicate audit evidence JSON key")
        result[key] = value
    return result


def _nonfinite(_):
    raise NativeCampaignJournalHold("nonfinite audit evidence")


def _encode_event(
    sequence: int, previous: str, event: str, manifest: str,
    task_id: str | None, evidence: dict,
) -> tuple[bytes, str]:
    if (
        type(sequence) is not int or not 1 <= sequence <= MAX_RECORDS
        or not _sha(previous) or not _sha(manifest)
        or event not in _STATUS
        or (task_id is not None and (
            type(task_id) is not str or not 1 <= len(task_id) <= 48
        ))
        or type(evidence) is not dict
    ):
        raise NativeCampaignJournalHold("noncanonical native campaign event")
    payload = {
        "schema": SCHEMA, "sequence": sequence,
        "previous_sha256": previous, "event": event,
        "manifest_sha256": manifest, "task_id": task_id,
        "evidence": evidence,
    }
    receipt = _digest(_canonical(payload))
    raw = _canonical({**payload, "event_sha256": receipt}) + b"\n"
    if len(raw) > MAX_RECORD_BYTES:
        raise NativeCampaignJournalHold("private journal event exceeds bounded receipt")
    return raw, receipt


class CampaignJournalWriter:
    """One no-clobber file owner; fsync each intent before native effects."""

    def __init__(self, path: str, *, project_root: str, manifest_sha256: str):
        if not _sha(manifest_sha256):
            raise NativeCampaignJournalHold("original campaign digest missing")
        self.path = _path(path, project_root)
        self.manifest_sha256 = manifest_sha256
        self.parent = None
        self.fd = None
        self.sequence = 0
        self.previous = "0" * 64
        self.written = 0

    def __enter__(self):
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            raise NativeCampaignJournalHold("POSIX/WSL2 private journal required")
        parent = _pinned_private_directory(self.path)
        fd = None
        try:
            _identical_parent(self.path, parent)
            fd = os.open(self.path.name, _FLAGS, 0o600, dir_fd=parent)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _same(self.path, parent, fd)
            os.fsync(parent)
            self.parent, self.fd = parent, fd
            return self
        except BaseException:
            if fd is not None:
                os.close(fd)
            os.close(parent)
            raise

    def append(self, event: str, *, task_id: str | None = None,
               evidence: dict | None = None) -> str:
        if self.fd is None or self.parent is None:
            raise NativeCampaignJournalHold("closed native campaign audit cannot write")
        content, digest = _encode_event(
            self.sequence + 1, self.previous, event,
            self.manifest_sha256, task_id, evidence if evidence is not None else {},
        )
        if self.written + len(content) > MAX_JOURNAL_BYTES:
            raise NativeCampaignJournalHold("journal aggregate limit reached")
        _same(self.path, self.parent, self.fd)
        # Append-only by owned descriptor. A short write is fatal and never
        # followed by a model retry.
        pos = 0
        while pos < len(content):
            count = os.write(self.fd, content[pos:])
            if type(count) is not int or count < 1:
                raise NativeCampaignJournalHold("short private campaign journal write")
            pos += count
        os.fsync(self.fd)
        _same(self.path, self.parent, self.fd)
        self.previous = digest
        self.sequence += 1
        self.written += len(content)
        return digest

    def __exit__(self, _kind, _value, _traceback):
        if self.fd is not None:
            os.close(self.fd)
        if self.parent is not None:
            os.close(self.parent)
        self.fd = self.parent = None


def _read(path: Path) -> bytes:
    parent = _pinned_private_directory(path)
    fd = None
    try:
        _identical_parent(path, parent)
        fd = os.open(path.name, _READ, dir_fd=parent)
        _same(path, parent, fd)
        before = os.fstat(fd)
        if not 1 <= before.st_size <= MAX_JOURNAL_BYTES:
            raise NativeCampaignJournalHold("journal not a bounded nonempty private file")
        buf = bytearray()
        while len(buf) <= MAX_JOURNAL_BYTES:
            block = os.read(fd, min(8192, MAX_JOURNAL_BYTES + 1 - len(buf)))
            if not block:
                break
            buf.extend(block)
        after = os.fstat(fd)
        _same(path, parent, fd)
        if (
            len(buf) != before.st_size
            or len(buf) > MAX_JOURNAL_BYTES
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise NativeCampaignJournalHold("private campaign journal changed during read")
        return bytes(buf)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def parse_campaign_journal(raw: bytes, *, expected_manifest_sha256: str,
                           task_ids: tuple[str, ...]) -> dict[str, object]:
    """Validate complete hash chain; audit UNKNOWN attempts conservatively."""
    if (
        not _sha(expected_manifest_sha256)
        or type(task_ids) is not tuple or not 1 <= len(task_ids) <= 12
        or len(set(task_ids)) != len(task_ids)
        or type(raw) is not bytes or not 1 <= len(raw) <= MAX_JOURNAL_BYTES
        or not raw.endswith(b"\n")
    ):
        raise NativeCampaignJournalHold("finite complete campaign audit required")
    frames = raw.splitlines(keepends=True)
    if not 1 <= len(frames) <= MAX_RECORDS:
        raise NativeCampaignJournalHold("unexpected number of campaign events")
    previous = "0" * 64
    attempts: list[str] = []
    saved: list[str] = []
    receipts: dict[str, dict] = {}
    halted = False
    complete = False
    for sequence, frame in enumerate(frames, 1):
        if not frame.endswith(b"\n") or not 1 <= len(frame) <= MAX_RECORD_BYTES:
            raise NativeCampaignJournalHold("truncated or oversized campaign event")
        try:
            record = json.loads(
                frame[:-1].decode("utf-8", "strict"),
                object_pairs_hook=_pairs, parse_constant=_nonfinite,
            )
        except (ValueError, UnicodeError, RecursionError, TypeError) as exc:
            raise NativeCampaignJournalHold("corrupt private campaign event") from exc
        if type(record) is not dict or set(record) != _FIELDS:
            raise NativeCampaignJournalHold("unexpected private journal event fields")
        digest = record["event_sha256"]
        body = {k: v for k, v in record.items() if k != "event_sha256"}
        if (
            not _sha(digest) or _digest(_canonical(body)) != digest
            or _canonical(record) + b"\n" != frame
            or record["schema"] != SCHEMA
            or record["sequence"] != sequence
            or record["previous_sha256"] != previous
            or record["manifest_sha256"] != expected_manifest_sha256
            or type(record["evidence"]) is not dict
        ):
            raise NativeCampaignJournalHold("noncanonical or broken audit hash chain")
        event, task, evidence = record["event"], record["task_id"], record["evidence"]
        if event not in _STATUS or (halted or complete):
            raise NativeCampaignJournalHold("extra or invalid terminal campaign event")
        if sequence == 1:
            if event != "begin" or task is not None or evidence != {}:
                raise NativeCampaignJournalHold("private audit must start with BEGIN")
        elif event == "attempt":
            if (
                type(task) is not str or task not in task_ids
                or task in attempts or len(attempts) >= len(task_ids)
                or task != task_ids[len(attempts)]
                or (attempts and attempts[-1] not in saved)
                or evidence != {"job_sha256": evidence.get("job_sha256")}
                or not _sha(evidence.get("job_sha256"))
            ):
                raise NativeCampaignJournalHold("unapproved, duplicate or out-of-order attempt")
            attempts.append(task)
        elif event == "saved":
            required = {
                "job_sha256", "private_file_sha256",
                "private_file_bytes", "model_sha256", "session_id",
                "source_manifest_sha256", "source_patch_sha256",
            }
            if (
                type(task) is not str or not attempts
                or attempts[-1] != task or task in saved
                or set(evidence) != required
                or any(not _sha(evidence[k]) for k in (
                    "job_sha256", "private_file_sha256", "model_sha256",
                    "source_manifest_sha256", "source_patch_sha256",
                ))
                or type(evidence["private_file_bytes"]) is not int
                or not 1 <= evidence["private_file_bytes"] <= 32768
                or type(evidence["session_id"]) is not str
                or not evidence["session_id"]
            ):
                raise NativeCampaignJournalHold("saved source lacks typed exact native evidence")
            # Bind this saved result to the previously approved attempt.
            if evidence["job_sha256"] != _attempt_job(frames, task, sequence):
                raise NativeCampaignJournalHold("saved model result differs from attempted task")
            saved.append(task)
            receipts[task] = evidence
        elif event == "halt":
            if task is not None or set(evidence) != {"reason"} or evidence["reason"] not in (
                "native-uncertain", "native-result-held", "private-custody-held",
                "journal-append-held",
            ):
                raise NativeCampaignJournalHold("private campaign halt reason untrusted")
            halted = True
        elif event == "complete":
            if task is not None or evidence != {} or tuple(saved) != task_ids:
                raise NativeCampaignJournalHold("completion cannot precede all source receipts")
            complete = True
        else:
            raise NativeCampaignJournalHold("unexpected secondary BEGIN")
        previous = digest
    uncertain = tuple(task for task in attempts if task not in saved)
    return {
        "schema": SCHEMA,
        "status": (
            "complete-cold-audit-receipts" if complete
            else "uncertain-native-attempt-no-retry" if uncertain
            else "stopped-before-all-source-escrows"
        ),
        "manifest_sha256": expected_manifest_sha256,
        "last_event_sha256": previous,
        "event_count": len(frames),
        "attempted_task_count": len(attempts),
        "saved_task_count": len(saved),
        "saved_task_ids": tuple(saved),
        "uncertain_task_ids": uncertain,
        "saved_receipts": receipts,
        "all_tasks_completed": complete,
        "automatic_native_retry_permitted": False,
        "authoritative_sqlite_replay_verified": False,
        "release_certified": False,
    }


def _attempt_job(frames: list[bytes], task_id: str, before_sequence: int) -> str:
    # Frame bytes have already been hash-chain validated by the caller's
    # sequential parser, and task count is at most 12.
    for frame in reversed(frames[:before_sequence - 1]):
        obj = json.loads(frame)
        if obj["event"] == "attempt" and obj["task_id"] == task_id:
            return obj["evidence"]["job_sha256"]
    raise NativeCampaignJournalHold("saved result without matching native intent")


def inspect_campaign_journal(path: str, *, project_root: str,
                             manifest_sha256: str,
                             task_ids: tuple[str, ...]) -> dict[str, object]:
    return parse_campaign_journal(
        _read(_path(path, project_root)),
        expected_manifest_sha256=manifest_sha256, task_ids=task_ids,
    )


__all__ = [
    "SCHEMA", "NativeCampaignJournalHold", "CampaignJournalWriter",
    "parse_campaign_journal", "inspect_campaign_journal",
]
