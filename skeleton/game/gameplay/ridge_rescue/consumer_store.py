"""Consumer-owned Cinder Ridge save slots with transactional, replay-checked CAS.

This is a portable local persistence adapter, not a network service. Every
mutation is serialized by SQLite BEGIN IMMEDIATE, and no action is accepted
without replaying the canonical campaign session. The SQLite file lives in an
application-owned user data directory; arbitrary save paths are not accepted.
"""
from __future__ import annotations

import json
import os
from contextlib import closing
from pathlib import Path
import re
import secrets
import sqlite3
import stat

from .campaign import (
    open_campaign, parse_campaign, verify_campaign, step_campaign,
    retry_campaign, export_campaign, verify_export,
)
from .custody import canonical, digest

SLOT = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
MAX_EXPORT_BYTES = 1_000_000
MAX_DATABASE_BYTES = 16_000_000
MAX_SAVE_SLOTS = 32
SCHEMA = "ridge.rescue.consumer.store.v1"


class StoreError(ValueError):
    """A save slot, local custody or transactional revision was rejected."""


def default_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        if base.startswith("\\\\"):
            raise StoreError("network save directories are unsupported")
        return Path(base) / "CinderRidge" / "Rescue"
    base = os.environ.get("XDG_DATA_HOME")
    if not base or not Path(base).is_absolute():
        base = str(Path.home() / ".local" / "share")
    return Path(base) / "cinder-ridge" / "rescue"


def _slot(value: str) -> str:
    if not isinstance(value, str) or not SLOT.fullmatch(value):
        raise StoreError("invalid save slot name")
    return value


def _safe_directory(path: Path) -> Path:
    """Build only private app-owned directories, rejecting links at each level.

    No arbitrary save path is accepted by the consumer CLI. Device-level
    hostile same-user races still require native Windows qualification.
    """
    if not path.is_absolute() or ".." in path.parts:
        raise StoreError("save directory must be absolute and normalized")
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor = cursor / part
        try:
            info = os.lstat(cursor)
        except FileNotFoundError:
            try:
                os.mkdir(cursor, mode=0o700)
            except FileExistsError:
                pass
            info = os.lstat(cursor)
        reparse = bool(getattr(info, "st_file_attributes", 0) & 0x400)
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or reparse:
            raise StoreError("save directory must not be a link")
    info = os.lstat(path)
    if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise StoreError("save directory is not private")
    return path


def _source() -> bytes:
    from importlib.resources import files
    data = files(__package__).joinpath("cinder_ridge_campaign.json").read_bytes()
    if len(data) > 96_000:
        raise StoreError("bundled campaign exceeds source budget")
    return data


def _check_session(data: bytes, stored_head: str) -> dict:
    if not isinstance(data, bytes) or len(data) > MAX_EXPORT_BYTES:
        raise StoreError("invalid persisted session")
    try:
        verified = verify_campaign(data)
        original = parse_campaign(_source())
    except (ValueError, TypeError, KeyError) as exc:
        raise StoreError("persisted campaign replay rejected") from exc
    if verified["head"] != stored_head:
        raise StoreError("save head does not match replay")
    if verified["session"]["source_sha256"] != digest(original):
        raise StoreError("save is not bound to the bundled original campaign")
    return verified


class SlotStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = _safe_directory(root if root is not None else default_root())
        self.database = self.root / "slots.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        try:
            if self.database.is_symlink():
                raise StoreError("linked save database refused")
            if self.database.exists():
                mode = os.lstat(self.database).st_mode
                if not stat.S_ISREG(mode):
                    raise StoreError("save database must be a regular file")
                if os.lstat(self.database).st_size > MAX_DATABASE_BYTES:
                    raise StoreError("save database exceeds bounded storage")
            connection = sqlite3.connect(str(self.database), timeout=5, isolation_level=None)
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS slots ("
                "name TEXT PRIMARY KEY, head TEXT NOT NULL, session BLOB NOT NULL,"
                "revision INTEGER NOT NULL CHECK(revision >= 0))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS actions ("
                "slot TEXT NOT NULL, revision INTEGER NOT NULL,"
                "prior_head TEXT NOT NULL, next_head TEXT NOT NULL,"
                "action BLOB NOT NULL, PRIMARY KEY(slot, revision),"
                "FOREIGN KEY(slot) REFERENCES slots(name))"
            )
            connection.execute("PRAGMA foreign_keys=ON")
            if self.database.is_symlink():
                connection.close()
                raise StoreError("save database became a link")
            return connection
        except sqlite3.Error as exc:
            raise StoreError("save database unavailable or corrupt") from exc

    @staticmethod
    def _read(conn: sqlite3.Connection, name: str) -> tuple[dict, int]:
        row = conn.execute("SELECT head, session, revision FROM slots WHERE name=?", (name,)).fetchone()
        if row is None:
            raise StoreError("save slot does not exist")
        head, raw, revision = row
        if type(head) is not str or type(revision) is not int or revision < 0:
            raise StoreError("invalid persisted revision")
        return _check_session(raw, head), revision

    def new(self, name: str) -> dict:
        name = _slot(name)
        session = open_campaign(_source())
        with closing(self._connect()) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                count = conn.execute("SELECT COUNT(*) FROM slots").fetchone()[0]
                if count >= MAX_SAVE_SLOTS:
                    raise StoreError("save slot capacity exhausted")
                conn.execute("INSERT INTO slots VALUES(?,?,?,?)",
                             (name, session["head"], canonical(session), 0))
                conn.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK")
                raise StoreError("save slot already exists") from exc
            except sqlite3.Error as exc:
                conn.execute("ROLLBACK")
                raise StoreError("save transaction refused") from exc
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        return self.load(name)

    def load(self, name: str) -> dict:
        name = _slot(name)
        with closing(self._connect()) as conn:
            try:
                verified, revision = self._read(conn, name)
            except sqlite3.Error as exc:
                raise StoreError("save read failed") from exc
        return {**verified, "slot": name, "revision": revision}

    def _mutate(self, name: str, expected_head: str, action: dict | None) -> dict:
        name = _slot(name)
        if not isinstance(expected_head, str) or len(expected_head) != 64:
            raise StoreError("expected 64-character CAS head")
        with closing(self._connect()) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                previous, revision = self._read(conn, name)
                if previous["head"] != expected_head:
                    raise StoreError("stale save revision")
                if action is None:
                    updated = retry_campaign(previous["session"], expected_head=expected_head)
                    event = {"verb": "retry"}
                else:
                    updated = step_campaign(previous["session"], action, expected_head=expected_head)
                    event = action
                new_head = updated["head"]
                if new_head == expected_head:
                    raise StoreError("save transition did not advance")
                count = conn.execute(
                    "UPDATE slots SET head=?, session=?, revision=? WHERE name=? AND head=? AND revision=?",
                    (new_head, canonical(updated), revision + 1, name, expected_head, revision),
                ).rowcount
                if count != 1:
                    raise StoreError("concurrent save conflict")
                conn.execute(
                    "INSERT INTO actions(slot, revision, prior_head, next_head, action) VALUES(?,?,?,?,?)",
                    (name, revision + 1, expected_head, new_head, canonical(event)),
                )
                conn.execute("COMMIT")
            except sqlite3.Error as exc:
                conn.execute("ROLLBACK")
                raise StoreError("save transaction refused") from exc
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        return self.load(name)

    def step(self, name: str, action: dict, *, expected_head: str) -> dict:
        if not isinstance(action, dict):
            raise StoreError("action must be a JSON object")
        return self._mutate(name, expected_head, action)

    def retry(self, name: str, *, expected_head: str) -> dict:
        return self._mutate(name, expected_head, None)

    def export(self, name: str) -> Path:
        name = _slot(name)
        # An export must not bless a snapshot whose durable action ledger has
        # been altered independently of the replayable session. Audit before
        # publishing any portable artifact; failures leave no export behind.
        audited = self.audit(name)
        verified = self.load(name)
        # Another process can advance this slot after audit but before load.
        # Never publish a newer, unaudited revision under an older audit.
        # Fail closed rather than treating two independent reads as one snapshot.
        if (verified["head"] != audited["head"] or
                verified["revision"] != audited["revision"]):
            raise StoreError("save changed during export audit; retry export")
        bundle = export_campaign(verified["session"])
        if verify_export(bundle)["head"] != verified["head"]:
            raise StoreError("portable export did not replay")
        payload = canonical(bundle) + b"\n"
        if len(payload) > MAX_EXPORT_BYTES:
            raise StoreError("export exceeds byte budget")
        directory = self.root / "exports"
        _safe_directory(directory)
        path = directory / (name + "-" + verified["head"][:12] + "-" + secrets.token_hex(6) + ".json")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = None
        owned_identity = None
        try:
            fd = os.open(path, flags, 0o600)
            opened = os.fstat(fd)
            owned_identity = (opened.st_dev, opened.st_ino)
            with os.fdopen(fd, "wb") as output:
                fd = None
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
        except OSError as exc:
            # An interrupted write must not leave a partial export that a
            # consumer could mistake for a complete replayable save.
            # Never unlink a replacement installed by another process.
            if owned_identity is not None:
                try:
                    current = path.lstat()
                    if (current.st_dev, current.st_ino) == owned_identity:
                        path.unlink()
                except OSError:
                    pass
            raise StoreError("portable export write refused") from exc
        finally:
            if fd is not None:
                os.close(fd)
        return path

    def restore(self, name: str, payload: bytes | str | dict) -> dict:
        """Restore campaign exports without retries into a new audited slot."""
        from .consumer_restore import replay_export
        session, history = replay_export(payload, _source())
        return self._insert_restored(name, session, history)

    def restore_backup(self, name: str, payload: bytes | str | dict) -> dict:
        """Restore full retry-aware consumer backups into a new audited slot."""
        from .consumer_backup import verify_backup
        session, history = verify_backup(payload, _source())
        return self._insert_restored(name, session, history)

    def _insert_restored(self, name: str, session: dict, history: list[dict]) -> dict:
        name = _slot(name)
        if len(canonical(session)) > MAX_EXPORT_BYTES:
            raise StoreError("restored session exceeds byte budget")
        with closing(self._connect()) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                count = conn.execute("SELECT COUNT(*) FROM slots").fetchone()[0]
                if count >= MAX_SAVE_SLOTS:
                    raise StoreError("save slot capacity exhausted")
                conn.execute("INSERT INTO slots VALUES(?,?,?,?)",
                             (name, session["head"], canonical(session), len(history)))
                for revision, item in enumerate(history, 1):
                    conn.execute(
                        "INSERT INTO actions(slot, revision, prior_head, next_head, action) "
                        "VALUES(?,?,?,?,?)",
                        (name, revision, item["prior_head"], item["next_head"],
                         canonical(item["action"])),
                    )
                conn.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK")
                raise StoreError("restore destination already exists") from exc
            except sqlite3.Error as exc:
                conn.execute("ROLLBACK")
                raise StoreError("restore transaction refused") from exc
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        audited = self.audit(name)
        if audited["head"] != session["head"] or audited["revision"] != len(history):
            raise StoreError("restored save audit mismatch")
        return self.load(name)

    def backup(self, name: str) -> Path:
        """Export a transactionally consistent, fully replayable action history."""
        from .consumer_backup import build_backup, MAX_BACKUP_BYTES, MAX_BACKUP_ACTIONS
        name = _slot(name)
        with closing(self._connect()) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                verified, revision = self._read(conn, name)
                # Bound corrupt ledger metadata before materializing any rows.
                if revision > MAX_BACKUP_ACTIONS:
                    raise StoreError("save history exceeds backup action budget")
                rows = conn.execute(
                    "SELECT revision, prior_head, next_head, action FROM actions "
                    "WHERE slot=? ORDER BY revision LIMIT ?", (name, MAX_BACKUP_ACTIONS + 1),
                ).fetchall()
                if len(rows) != revision:
                    raise StoreError("save history is incomplete")
                history = []
                for position, (number, prior, nxt, raw) in enumerate(rows, 1):
                    if number != position or not isinstance(raw, bytes) or len(raw) > 4096:
                        raise StoreError("save history is malformed")
                    try:
                        action = json.loads(raw)
                        if not isinstance(action, dict) or canonical(action) != raw:
                            raise StoreError("save history action is not canonical")
                    except (ValueError, TypeError, UnicodeError) as exc:
                        raise StoreError("save history action is not canonical") from exc
                    history.append({"prior_head": prior, "next_head": nxt, "action": action})
                conn.execute("COMMIT")
            except sqlite3.Error as exc:
                conn.execute("ROLLBACK")
                raise StoreError("backup read transaction refused") from exc
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        # Validate/replay the immutable snapshot AFTER releasing the SQLite
        # writer lock; another process can continue playing during backup.
        bundle = build_backup(verified["session"], history, _source())
        payload = canonical(bundle) + b"\n"
        if len(payload) > MAX_BACKUP_BYTES:
            raise StoreError("backup exceeds byte budget")
        directory = _safe_directory(self.root / "exports")
        path = directory / (name + "-backup-" + verified["head"][:12] + "-" + secrets.token_hex(6) + ".json")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = None
        owned_identity = None
        try:
            fd = os.open(path, flags, 0o600)
            opened = os.fstat(fd)
            owned_identity = (opened.st_dev, opened.st_ino)
            with os.fdopen(fd, "wb") as output:
                fd = None
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
        except OSError as exc:
            # A failed backup must not leave an apparently valid artifact.
            # Do not remove a replacement published by another process.
            if owned_identity is not None:
                try:
                    current = path.lstat()
                    if (current.st_dev, current.st_ino) == owned_identity:
                        path.unlink()
                except OSError:
                    pass
            raise StoreError("portable backup write refused") from exc
        finally:
            if fd is not None:
                os.close(fd)
        return path

    def audit(self, name: str) -> dict:
        name = _slot(name)
        # Read the slot and action ledger in one SQLite snapshot. A second
        # process can commit between two independent reads, falsely making
        # an intact save look corrupt. Release the lock before replay.
        with closing(self._connect()) as conn:
            try:
                conn.execute("BEGIN")
                verified, revision = self._read(conn, name)
                # Audit must obey the same finite replay budget as backup.
                # Corrupt slot metadata must not trigger an unbounded SELECT,
                # nor should a mismatched action table be fully materialized.
                from .consumer_backup import MAX_BACKUP_ACTIONS
                if revision > MAX_BACKUP_ACTIONS:
                    raise StoreError("save history exceeds audit action budget")
                rows = conn.execute(
                    "SELECT revision, prior_head, next_head, action FROM actions "
                    "WHERE slot=? ORDER BY revision LIMIT ?",
                    (name, MAX_BACKUP_ACTIONS + 1),
                ).fetchall()
                conn.execute("COMMIT")
            except sqlite3.Error as exc:
                conn.execute("ROLLBACK")
                raise StoreError("save audit refused") from exc
        current = {**verified, "slot": name, "revision": revision}
        if len(rows) != current["revision"]:
            raise StoreError("save history is incomplete")
        # Verify every stored action against the original campaign and
        # recompute each intermediate head. A contiguous string-only chain is
        # insufficient: an attacker could change the action but retain heads.
        replayed = open_campaign(_source())
        previous = replayed["head"]
        for position, (revision, prior, nxt, raw) in enumerate(rows, 1):
            if revision != position or prior != previous:
                raise StoreError("save history chain broken")
            if not isinstance(raw, bytes) or len(raw) > 4096:
                raise StoreError("save history action invalid")
            try:
                action = json.loads(raw)
                if not isinstance(action, dict) or canonical(action) != raw:
                    raise ValueError("noncanonical audit action")
                if action == {"verb": "retry"}:
                    replayed = retry_campaign(replayed, expected_head=previous)
                else:
                    replayed = step_campaign(replayed, action, expected_head=previous)
            except (ValueError, TypeError, KeyError, UnicodeError) as exc:
                raise StoreError("save history action replay rejected") from exc
            if replayed["head"] != nxt:
                raise StoreError("save history head mismatch")
            previous = nxt
        if previous != current["head"] or replayed != current["session"]:
            raise StoreError("save history head mismatch")
        return {"schema": SCHEMA, "slot": name, "revision": current["revision"],
                "head": current["head"], "status": current["status"],
                "audit_entries": len(rows), "verified": True}
