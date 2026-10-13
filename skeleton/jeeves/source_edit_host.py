"""Opt-in local source editing backend for the Jeeves host.

The code-edit tool is not automatically installed. Trusted application code
must instantiate this owner, select allowed subtrees, inject a separate human/
policy authorization callback into the workbench, and grant the exact HIGH_IMPACT
tool call. The owner performs a single atomic replacement per plan.

The SQLite intent journal is committed *before* touching the source. A crash
after an atomic rename leaves an unresolved intent; the exact operation cannot
be replayed until host-controlled reconciliation inspects the current bytes.
"""
from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import stat
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any

from .source_edit_gateway import (
    EDITABLE_SUFFIXES, MAX_EDIT_FILE, SourceEditPlan,
    SourceEditReceipt, JeevesSourceEditError,
)

_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS jeeves_source_edit (
    plan_digest TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    path TEXT NOT NULL,
    before_sha256 TEXT NOT NULL,
    after_sha256 TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('pending','committed','aborted','conflict')),
    event_digest TEXT NOT NULL,
    observed_at_ns INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS jeeves_source_edit_path ON jeeves_source_edit(path,state);
"""


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _bounded_root(relative: str) -> str:
    if (not isinstance(relative, str) or not relative
            or relative.startswith("/") or "\\" in relative
            or relative.startswith(".")
            or len(relative) > 512 or any(part in {"", ".", ".."} for part in relative.split("/"))):
        raise JeevesSourceEditError("allowed source root must be a canonical subtree")
    return relative.rstrip("/")


class JeevesAtomicSourceEditor:
    """Durable exact-digest editor. Host approval is enforced by its caller."""

    def __init__(
        self, *, repo_root: str | Path, journal_path: str | Path,
        allowed_roots: Sequence[str],
    ) -> None:
        self.root = Path(repo_root).resolve()
        self.path = Path(journal_path)
        if not self.root.is_dir():
            raise JeevesSourceEditError("edit repository is not a directory")
        if not self.path.is_absolute() or self.path.resolve().is_relative_to(self.root):
            raise JeevesSourceEditError("source edit journal must be outside repository")
        if (not isinstance(allowed_roots, (tuple, list))
                or not 1 <= len(allowed_roots) <= 128):
            raise JeevesSourceEditError("source editor needs an explicit allowlist")
        self.allowed_roots = tuple(sorted(set(_bounded_root(root) for root in allowed_roots)))
        self._lock = RLock()
        self._db = sqlite3.connect(
            str(self.path), timeout=10, isolation_level=None,
            check_same_thread=False,
        )
        try:
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.executescript(_SCHEMA)
        except BaseException:
            self._db.close()
            raise

    def _full_path(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or len(relative) > 2048:
            raise JeevesSourceEditError("invalid edit path")
        if (relative.startswith("/") or "\\" in relative or any(
                part in {"", ".", ".."} for part in relative.split("/"))):
            raise JeevesSourceEditError("unsafe relative edit path")
        if not any(relative.startswith(prefix + "/") for prefix in self.allowed_roots):
            raise JeevesSourceEditError("path is outside host source-edit allowlist")
        full = self.root / relative
        if full.suffix.lower() not in EDITABLE_SUFFIXES:
            raise JeevesSourceEditError("source suffix is outside edit allowlist")
        if not full.resolve().is_relative_to(self.root):
            raise JeevesSourceEditError("source path escapes repository")
        parts = Path(relative).parts
        if full.is_symlink() or any(
            (self.root / Path(*parts[:i])).is_symlink()
            for i in range(1, len(parts))
        ):
            raise JeevesSourceEditError("source symlink path is not editable")
        return full

    @staticmethod
    def _read_exact(path: Path) -> tuple[bytes, os.stat_result]:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as source:
                state = os.fstat(source.fileno())
                if not stat.S_ISREG(state.st_mode) or state.st_size > MAX_EDIT_FILE:
                    raise JeevesSourceEditError("source file is not a small regular file")
                data = source.read(MAX_EDIT_FILE + 1)
                if len(data) != state.st_size:
                    raise JeevesSourceEditError("source changed during read")
                after = os.fstat(source.fileno())
                if after.st_size != state.st_size or after.st_mtime_ns != state.st_mtime_ns:
                    raise JeevesSourceEditError("source changed while being read")
                return data, state
        except OSError as exc:
            raise JeevesSourceEditError("host source is not readable") from exc

    @staticmethod
    def _apply(original: bytes, plan: SourceEditPlan) -> bytes:
        try:
            value = original.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise JeevesSourceEditError("source is not canonical UTF-8") from exc
        updated = value
        for patch in plan.replacements:
            if updated.count(patch.before) != 1:
                raise JeevesSourceEditError("replacement does not have exactly one target")
            updated = updated.replace(patch.before, patch.after, 1)
        encoded = updated.encode("utf-8")
        if len(encoded) > MAX_EDIT_FILE:
            raise JeevesSourceEditError("updated source exceeds editor byte budget")
        if sha256(encoded).hexdigest() != plan.after_sha256:
            raise JeevesSourceEditError("edit result differs from approved output hash")
        return encoded

    def _event(self, plan: SourceEditPlan, *, state: str, at_ns: int) -> str:
        return _digest({
            "schema": "jeeves.source_edit_event.v1",
            "plan_digest": plan.digest,
            "project_id": plan.project_id,
            "path": plan.path,
            "before_sha256": plan.before_sha256,
            "after_sha256": plan.after_sha256,
            "state": state,
            "observed_at_ns": at_ns,
        })

    def __call__(self, plan: SourceEditPlan, context: Any) -> SourceEditReceipt:
        """Apply one authorized plan under durable pending/commit states."""
        if not isinstance(plan, SourceEditPlan):
            raise JeevesSourceEditError("source host needs a typed edit plan")
        at_ns = getattr(context, "metadata", {}).get("observed_at_ns")
        if type(at_ns) is not int or at_ns < 0:
            raise JeevesSourceEditError("host edit event time required")
        if plan.before_sha256 == plan.after_sha256:
            raise JeevesSourceEditError("source edit cannot be a no-op")
        full = self._full_path(plan.path)
        with self._lock:
            # Cross-process lease: hold BEGIN IMMEDIATE while checking for
            # competing pending edits and installing the durable intent.
            # No filesystem side effect occurs before COMMIT.
            try:
                self._db.execute("BEGIN IMMEDIATE")
                previous = self._db.execute(
                    "SELECT 1 FROM jeeves_source_edit WHERE plan_digest=?",
                    (plan.digest,),
                ).fetchone()
                if previous is not None:
                    raise JeevesSourceEditError(
                        "source edit was already submitted; reconcile its exact receipt"
                    )
                unresolved = self._db.execute(
                    "SELECT COUNT(*) FROM jeeves_source_edit "
                    "WHERE path=? AND state='pending'",
                    (plan.path,),
                ).fetchone()[0]
                if unresolved:
                    raise JeevesSourceEditError("source has an unresolved prior edit")
                original, source_stat = self._read_exact(full)
                if sha256(original).hexdigest() != plan.before_sha256:
                    raise JeevesSourceEditError("source content changed since proposal")
                updated = self._apply(original, plan)
                event = self._event(plan, state="pending", at_ns=at_ns)
                self._db.execute(
                    "INSERT INTO jeeves_source_edit VALUES (?,?,?,?,?,?,?,?)",
                    (plan.digest, plan.project_id, plan.path, plan.before_sha256,
                     plan.after_sha256, "pending", event, at_ns),
                )
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
            temporary: Path | None = None
            try:
                with NamedTemporaryFile(
                    "wb", dir=full.parent,
                    prefix=".jeeves-edit-", suffix=".tmp", delete=False,
                ) as handle:
                    temporary = Path(handle.name)
                    if hasattr(os, "fchmod"):
                        os.fchmod(handle.fileno(), stat.S_IMODE(source_stat.st_mode))
                    handle.write(updated)
                    handle.flush()
                    os.fsync(handle.fileno())
                # Compare bytes and inode again immediately before the atomic
                # swap; another writer must never be silently overwritten.
                latest, latest_stat = self._read_exact(full)
                if (sha256(latest).hexdigest() != plan.before_sha256
                        or latest_stat.st_ino != source_stat.st_ino
                        or latest_stat.st_mtime_ns != source_stat.st_mtime_ns):
                    raise JeevesSourceEditError("source concurrently changed before atomic swap")
                os.replace(temporary, full)
                temporary = None
                try:
                    directory_fd = os.open(full.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                except OSError:
                    # Windows does not support fsync on all directory handles.
                    pass
                current, _ = self._read_exact(full)
                if sha256(current).hexdigest() != plan.after_sha256:
                    raise JeevesSourceEditError("post-commit content differs from proposal")
                committed = self._event(plan, state="committed", at_ns=at_ns)
                self._db.execute(
                    "UPDATE jeeves_source_edit SET state='committed',event_digest=? "
                    "WHERE plan_digest=? AND state='pending'",
                    (committed, plan.digest),
                )
                return SourceEditReceipt(
                    plan_digest=plan.digest, project_id=plan.project_id,
                    path=plan.path, before_sha256=plan.before_sha256,
                    after_sha256=plan.after_sha256, committed=True,
                    host_event_digest=committed,
                )
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    def reconcile(self, plan: SourceEditPlan, *,
                  observed_at_ns: int) -> str:
        """Inspect unresolved host effects; never replay the pending operation."""
        if type(observed_at_ns) is not int or observed_at_ns < 0:
            raise JeevesSourceEditError("recovery requires host observation time")
        if not isinstance(plan, SourceEditPlan):
            raise JeevesSourceEditError("typed plan required for reconciliation")
        with self._lock:
            row = self._db.execute(
                "SELECT state,project_id,path,before_sha256,after_sha256 "
                "FROM jeeves_source_edit WHERE plan_digest=?",
                (plan.digest,),
            ).fetchone()
            if row is None or row[1:] != (
                    plan.project_id, plan.path, plan.before_sha256, plan.after_sha256):
                raise JeevesSourceEditError("unknown exact host edit intent")
            if row[0] != "pending":
                return row[0]
            full = self._full_path(plan.path)
            content, _ = self._read_exact(full)
            actual = sha256(content).hexdigest()
            outcome = (
                "committed" if actual == plan.after_sha256
                else "aborted" if actual == plan.before_sha256
                else "conflict"
            )
            event = self._event(plan, state=outcome, at_ns=observed_at_ns)
            self._db.execute(
                "UPDATE jeeves_source_edit SET state=?,event_digest=?,observed_at_ns=? "
                "WHERE plan_digest=? AND state='pending'",
                (outcome, event, observed_at_ns, plan.digest),
            )
            return outcome

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "JeevesAtomicSourceEditor":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = ["JeevesAtomicSourceEditor"]
