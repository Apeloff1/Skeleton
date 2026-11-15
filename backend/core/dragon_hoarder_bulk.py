"""Opt-in Hoarder bulk storage primitive; not a source authorization service.

Use on operator-controlled private local filesystems. The caller must qualify
retention, retrieval and deletion against canonical crawler policy. Never use
an object receipt as permission to read external evidence.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
import stat
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

GIB = 1024 ** 3
TIB = 1024 ** 4
MAX_OBJECT = 16 * 1024 ** 2
MAX_VOLUMES = 2560
MIN_RESERVE = GIB
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class StorageHeld(RuntimeError):
    """No storage publication was admitted."""


def owner_key(scope: dict[str, str]) -> str:
    """Separate content identity by the authenticated tenant AND owner."""
    if not isinstance(scope, dict) or set(scope) != {"tenant_id", "owner_id"}:
        raise ValueError("invalid scope")
    parts = []
    for key in ("tenant_id", "owner_id"):
        value = scope[key]
        if not isinstance(value, str) or not value or len(value) > 256 or "\0" in value:
            raise ValueError("invalid scope")
        parts.append(value.encode("utf-8"))
    return hashlib.sha256(b"".join(len(p).to_bytes(4, "big") + p for p in parts)).hexdigest()


def _storage_owner(scope,namespace=None):
    """Internal domain separation for partition-local chunk references.

    None preserves every legacy physical object ID. Namespace must be an
    operator-created random partition witness, not an HTTP input.
    """
    owner=owner_key(scope)
    if namespace is None:return owner
    if not isinstance(namespace,str) or not _HASH.fullmatch(namespace):
        raise ValueError("invalid storage namespace")
    return hashlib.sha256(b"dragon.manifest.partition.v1\\0"+bytes.fromhex(owner)+bytes.fromhex(namespace)).hexdigest()


@dataclass(frozen=True)
class Volume:
    name: str
    root: Path
    payload_budget: int
    free_reserve: int = MIN_RESERVE

    def __post_init__(self):
        if not isinstance(self.name, str) or not _ID.fullmatch(self.name):
            raise ValueError("invalid volume identity")
        if type(self.payload_budget) is not int or not GIB <= self.payload_budget <= 1024 * TIB:
            raise ValueError("invalid payload budget")
        if type(self.free_reserve) is not int or self.free_reserve < MIN_RESERVE:
            raise ValueError("invalid free-space reserve")
        root = Path(self.root)
        if not root.is_absolute() or root.resolve(strict=True) != root:
            raise ValueError("volume must be an existing canonical directory")
        mode = root.stat().st_mode
        if not stat.S_ISDIR(mode):
            raise ValueError("volume must be a directory")
        if os.name == "posix" and (mode & 0o077 or root.stat().st_uid != os.getuid()):
            raise ValueError("volume must be private and owned by the runtime user")
        object.__setattr__(self, "root", root)


@dataclass(frozen=True)
class Receipt:
    volume: str
    scope_key: str
    digest: str
    raw_bytes: int
    compressed_bytes: int


_SCHEMA = """
CREATE TABLE IF NOT EXISTS volume_identity(
  singleton INTEGER PRIMARY KEY CHECK(singleton=1), name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage(
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  payload_bytes INTEGER NOT NULL CHECK(payload_bytes>=0),
  objects INTEGER NOT NULL CHECK(objects>=0)
);
INSERT OR IGNORE INTO usage VALUES(1,0,0);
CREATE TABLE IF NOT EXISTS objects(
  owner TEXT NOT NULL, digest TEXT NOT NULL,
  raw_bytes INTEGER NOT NULL CHECK(raw_bytes BETWEEN 1 AND 16777216),
  compressed_bytes INTEGER NOT NULL CHECK(compressed_bytes>0),
  payload BLOB NOT NULL, PRIMARY KEY(owner,digest),
  CHECK(length(payload)=compressed_bytes)
) WITHOUT ROWID;
"""


class BulkArchive:
    """Independent volume ledgers, immutable payloads and exact-size receipts.

    The logical compressed payload budget is distinct from SQLite file/WAL size.
    Filesystem reserve is a best-effort admission observation, not an OS quota.
    No network exposure, automatic retries or source lifecycle is supplied here.
    """

    def __init__(self, volumes: tuple[Volume, ...]):
        if not 1 <= len(volumes) <= MAX_VOLUMES:
            raise ValueError("invalid number of volumes")
        self.volumes = {v.name: v for v in volumes}
        if len(self.volumes) != len(volumes):
            raise ValueError("duplicate volume name")
        devices = set()
        self._root_identities = {}
        self._file_identities = {}
        for volume in volumes:
            identity = volume.root.stat()
            if identity.st_dev in devices:
                raise ValueError("configure one volume per filesystem device")
            devices.add(identity.st_dev)
            self._root_identities[volume.name] = (identity.st_dev, identity.st_ino)
            # Initialize separately so an interrupted initialization is repeatable.
            with self._db(volume) as db:
                db.executescript(_SCHEMA)
                db.execute("INSERT OR IGNORE INTO volume_identity VALUES(1,?)", (volume.name,))
                if db.execute("SELECT name FROM volume_identity WHERE singleton=1").fetchone() != (volume.name,):
                    raise StorageHeld("volume identity mismatch")

    @contextmanager
    def _db(self, volume: Volume):
        # This boundary assumes exclusive operator control of the root; it is
        # not a sandbox for malicious processes running under the same UID.
        if volume.root.resolve(strict=True) != volume.root:
            raise StorageHeld("volume root changed")
        root_stat = volume.root.stat()
        if (root_stat.st_dev,root_stat.st_ino) != self._root_identities[volume.name]:
            raise StorageHeld("mounted volume identity changed")
        if os.name == "posix" and (root_stat.st_mode & 0o077 or root_stat.st_uid != os.getuid()):
            raise StorageHeld("volume permissions changed")
        path = volume.root / "hoarder-payload-v1.sqlite3"
        for file in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
            if file.is_symlink() or (file.exists() and not file.is_file()):
                raise StorageHeld("unsafe storage entry")
        if not path.exists():
            if volume.name in self._file_identities:
                raise StorageHeld("payload database disappeared")
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        st = path.stat()
        if os.name == "posix" and (st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_nlink != 1):
            raise StorageHeld("payload permissions or links changed")
        current = (st.st_dev,st.st_ino)
        if self._file_identities.setdefault(volume.name,current) != current:
            raise StorageHeld("payload database identity changed")
        db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5, isolation_level=None)
        try:
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:
            db.close()

    @staticmethod
    def _decode(data: bytes, size: int, digest: str) -> bytes:
        if not 1 <= size <= MAX_OBJECT or len(data) > MAX_OBJECT + 65536:
            raise StorageHeld("object bounds invalid")
        try:
            decoder = zlib.decompressobj()
            raw = decoder.decompress(data, size + 1)
        except zlib.error as exc:
            raise StorageHeld("object compression damaged") from exc
        if (len(raw) != size or not decoder.eof or decoder.unconsumed_tail
                or decoder.unused_data or hashlib.sha256(raw).hexdigest() != digest):
            raise StorageHeld("object integrity failed")
        return raw

    def put(self, volume: str, scope: dict[str, str], raw: bytes, *, namespace=None) -> Receipt:
        owner = _storage_owner(scope,namespace)
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_OBJECT:
            raise ValueError("invalid object size")
        digest = hashlib.sha256(raw).hexdigest()
        payload = zlib.compress(raw, level=6)
        v = self.volumes[volume]
        with self._db(v) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT raw_bytes,compressed_bytes,payload FROM objects WHERE owner=? AND digest=?",
                    (owner, digest),
                ).fetchone()
                if existing:
                    self._decode(existing[2], existing[0], digest)
                    receipt = Receipt(volume, owner, digest, existing[0], existing[1])
                else:
                    used = db.execute("SELECT payload_bytes FROM usage WHERE singleton=1").fetchone()[0]
                    if used + len(payload) > v.payload_budget:
                        raise StorageHeld("logical payload budget reached")
                    # Account conservatively for page allocation and WAL copies.
                    if shutil.disk_usage(v.root).free < v.free_reserve + 4 * len(payload) + 1024 ** 2:
                        raise StorageHeld("physical free-space reserve reached")
                    db.execute("INSERT INTO objects VALUES(?,?,?,?,?)",
                               (owner, digest, len(raw), len(payload), payload))
                    db.execute("UPDATE usage SET payload_bytes=payload_bytes+?,objects=objects+1 WHERE singleton=1",
                               (len(payload),))
                    receipt = Receipt(volume, owner, digest, len(raw), len(payload))
                db.execute("COMMIT")
                return receipt
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _check_receipt(self, scope, receipt, *, namespace=None):
        if (not isinstance(receipt, Receipt) or receipt.scope_key != _storage_owner(scope,namespace)
                or not _HASH.fullmatch(receipt.digest)
                or not 1 <= receipt.raw_bytes <= MAX_OBJECT
                or not 1 <= receipt.compressed_bytes <= MAX_OBJECT + 65536):
            raise StorageHeld("object receipt invalid")

    def read(self, scope: dict[str, str], receipt: Receipt, *, namespace=None) -> bytes:
        self._check_receipt(scope, receipt,namespace=namespace)
        with self._db(self.volumes[receipt.volume]) as db:
            row = db.execute(
                "SELECT raw_bytes,compressed_bytes,payload FROM objects WHERE owner=? AND digest=?",
                (receipt.scope_key, receipt.digest),
            ).fetchone()
        if not row or tuple(row[:2]) != (receipt.raw_bytes, receipt.compressed_bytes):
            raise StorageHeld("object receipt unavailable")
        return self._decode(row[2], row[0], receipt.digest)

    def erase_unreferenced(self, scope: dict[str, str], receipt: Receipt, *, namespace=None) -> bool:
        """Caller MUST establish that no canonical reference retains this object.

        Logical removal, not secure physical erasure of WAL/pages/backups.
        """
        self._check_receipt(scope, receipt,namespace=namespace)
        with self._db(self.volumes[receipt.volume]) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                result = db.execute(
                    "DELETE FROM objects WHERE owner=? AND digest=? AND raw_bytes=? AND compressed_bytes=?",
                    (receipt.scope_key, receipt.digest, receipt.raw_bytes, receipt.compressed_bytes),
                )
                if result.rowcount:
                    db.execute("UPDATE usage SET payload_bytes=payload_bytes-?,objects=objects-1 WHERE singleton=1",
                               (receipt.compressed_bytes,))
                db.execute("COMMIT")
                return bool(result.rowcount)
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def capacity(self) -> list[dict]:
        """Operator-only telemetry; never expose shared disk statistics to tenants."""
        result = []
        for v in self.volumes.values():
            with self._db(v) as db:
                payload, objects = db.execute(
                    "SELECT payload_bytes,objects FROM usage WHERE singleton=1"
                ).fetchone()
            disk = shutil.disk_usage(v.root)
            result.append({"volume": v.name, "budget_bytes": v.payload_budget,
                           "stored_payload_bytes": payload, "objects": objects,
                           "filesystem_free_bytes": disk.free,
                           "physical_reserve_bytes": v.free_reserve,
                           "advisory_headroom_bytes": max(0, min(v.payload_budget - payload,
                               (disk.free - v.free_reserve - 1024 ** 2) // 4)),
                           "capacity_is_guaranteed": False})
        return result


    def lookup(self,volume: str,scope:dict[str,str],digest:str,*,namespace=None)->Receipt|None:
        """Resolve a previously journaled object after uncertain publication."""
        owner=_storage_owner(scope,namespace)
        if not isinstance(digest,str) or not _HASH.fullmatch(digest):
            raise ValueError("object digest")
        with self._db(self.volumes[volume]) as db:
            row=db.execute("SELECT raw_bytes,compressed_bytes,payload FROM objects WHERE owner=? AND digest=?",
                           (owner,digest)).fetchone()
        if not row:
            return None
        self._decode(row[2],row[0],digest)
        return Receipt(volume,owner,digest,row[0],row[1])
