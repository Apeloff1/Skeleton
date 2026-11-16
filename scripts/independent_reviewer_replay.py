"""Explicitly initialized durable replay ledger for the independent signer.

No implicit database creation, pruning, epoch reset or migration. A nonce is
consumed transactionally before signing, including denied review decisions.
Physical backup rollback and storage replacement remain operator controls.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys

from scripts.independent_reviewer_policy import PolicyDenied, _identity, _hex

_APP_ID = 1397445196
_VERSION = 1
_MAX_ENTRIES = 1_000_000
_MAX_PAGES = 65536
_NONCE = re.compile(r"[0-9a-f]{48}\Z", re.ASCII)
_META = """CREATE TABLE ledger_identity (singleton INTEGER PRIMARY KEY CHECK(singleton=1), ledger_id TEXT NOT NULL, authority TEXT NOT NULL, domain TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity BETWEEN 1 AND 1000000), consumed INTEGER NOT NULL CHECK(consumed BETWEEN 0 AND capacity))"""
_NONCES = """CREATE TABLE consumed_nonces (nonce_sha256 TEXT PRIMARY KEY NOT NULL CHECK(length(nonce_sha256)=64)) WITHOUT ROWID"""


def _deny():
    return PolicyDenied("durable reviewer replay custody unavailable")


def _config(path, ledger_id, authority, domain):
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.name in ("", ".", "..") or path.suffix != ".sqlite3"
            or not _hex(ledger_id) or not _identity(authority)
            or not _identity(domain) or authority == domain or os.name != "posix"):
        raise _deny()
    # Private direct parent, no symlink ancestors. Shared ancestors must
    # either be non-writable to others or sticky (e.g. /tmp).
    parent = path.parent
    for directory in (parent, *parent.parents):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise _deny()
        if directory == parent:
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise _deny()
        elif info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
            raise _deny()
    return parent


def _identity_at(path):
    data = path.lstat()
    if (not stat.S_ISREG(data.st_mode) or data.st_uid != os.geteuid()
            or data.st_mode & 0o077 or data.st_nlink != 1):
        raise _deny()
    return data.st_dev, data.st_ino


def _connect(path):
    conn = sqlite3.connect(path.as_uri()+"?mode=rw", uri=True, timeout=2.0,
                           isolation_level=None)
    try:
        conn.execute("PRAGMA trusted_schema=OFF")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=2000")
        if conn.execute("PRAGMA journal_mode").fetchone() != ("delete",):
            raise _deny()
        if conn.execute("PRAGMA max_page_count="+str(_MAX_PAGES)).fetchone()[0] > _MAX_PAGES:
            raise _deny()
        return conn
    except BaseException:
        conn.close()
        raise


def _validate(conn, ledger_id, authority, domain, *, full=False):
    if (conn.execute("PRAGMA application_id").fetchone() != (_APP_ID,)
            or conn.execute("PRAGMA user_version").fetchone() != (_VERSION,)):
        raise _deny()
    schema = dict(conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"))
    if schema != {"ledger_identity": _META, "consumed_nonces": _NONCES}:
        raise _deny()
    if conn.execute("SELECT count(*) FROM sqlite_master WHERE type IN ('trigger','view')").fetchone() != (0,):
        raise _deny()
    row = conn.execute("SELECT ledger_id, authority, domain, capacity, consumed FROM ledger_identity WHERE singleton=1").fetchone()
    if (row is None or row[:3] != (ledger_id, authority, domain)
            or type(row[3]) is not int or type(row[4]) is not int
            or not 0 <= row[4] <= row[3] <= _MAX_ENTRIES or row[3] == 0):
        raise _deny()
    if full and (conn.execute("PRAGMA quick_check(1)").fetchone() != ("ok",)
                 or conn.execute("SELECT count(*) FROM consumed_nonces").fetchone() != (row[4],)):
        raise _deny()
    return row[3], row[4]


def initialize(path, *, ledger_id, authority, domain, capacity):
    """Run only during independently reviewed initial installation."""
    parent = _config(path, ledger_id, authority, domain)
    if type(capacity) is not int or not 1 <= capacity <= _MAX_ENTRIES:
        raise _deny()
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    os.close(fd)
    try:
        owned = _identity_at(path)
        with _closing(_connect(path)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("PRAGMA application_id="+str(_APP_ID))
            conn.execute("PRAGMA user_version="+str(_VERSION))
            conn.execute(_META)
            conn.execute(_NONCES)
            conn.execute("INSERT INTO ledger_identity VALUES(1,?,?,?,?,0)",
                         (ledger_id, authority, domain, capacity))
            conn.execute("COMMIT")
            _validate(conn, ledger_id, authority, domain, full=True)
        if _identity_at(path) != owned:
            raise _deny()
        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        # Retain incomplete initialization for independent investigation.
        # Never silently delete, recreate or reset a ledger.
        raise _deny() from None


from contextlib import closing as _closing


class DurableReplayLedger:
    def __init__(self, path, *, ledger_id, authority, domain):
        try:
            _config(path, ledger_id, authority, domain)
            self.path, self.ledger_id = path, ledger_id
            self.authority, self.domain = authority, domain
            self._inode = _identity_at(path)
            with _closing(_connect(path)) as conn:
                conn.execute("BEGIN")
                _validate(conn, ledger_id, authority, domain, full=True)
                conn.execute("COMMIT")
            self._check()
        except Exception:
            raise _deny() from None

    def _check(self):
        _config(self.path, self.ledger_id, self.authority, self.domain)
        if _identity_at(self.path) != self._inode:
            raise _deny()

    def consume(self, nonce):
        if type(nonce) is not str or _NONCE.fullmatch(nonce) is None:
            raise _deny()
        # Domain separation is fixed across policy generations and key
        # rotations on this ledger; no raw context, actor or certificate stored.
        key = hashlib.sha256(("skeleton.reviewer.nonce.v1\0"+self.ledger_id+"\0"+nonce).encode("ascii")).hexdigest()
        try:
            self._check()
            with _closing(_connect(self.path)) as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    capacity, consumed = _validate(conn, self.ledger_id, self.authority, self.domain)
                    if consumed >= capacity:
                        raise _deny()
                    conn.execute("INSERT INTO consumed_nonces VALUES(?)", (key,))
                    changed = conn.execute("UPDATE ledger_identity SET consumed=consumed+1 WHERE singleton=1 AND consumed=? AND consumed<capacity", (consumed,))
                    if changed.rowcount != 1:
                        raise _deny()
                    self._check()
                    conn.execute("COMMIT")
                    self._check()
                except BaseException:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise
        except Exception:
            raise _deny() from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize-new-ledger", required=True, action="store_true")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--ledger-id", required=True)
    parser.add_argument("--authority", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--capacity", required=True, type=int)
    options = parser.parse_args(argv)
    try:
        initialize(options.database, ledger_id=options.ledger_id, authority=options.authority,
                   domain=options.domain, capacity=options.capacity)
    except Exception:
        print("Replay ledger initialization denied; existing custody preserved.", file=sys.stderr)
        return 2
    print("New durable replay ledger initialized; no signer or deployment activation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
