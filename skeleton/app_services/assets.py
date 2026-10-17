"""Content-addressed file/asset storage (local filesystem adapter).

Blobs live at ``<root>/blobs/<aa>/<sha256>``; metadata in the ``assets`` table.
Identical content is stored once; blobs are garbage-collected when the last
referencing asset is removed.  Names are validated (no traversal, no NUL).
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from skeleton.app_services.db import Database
from skeleton.app_services.ports import Asset

DEFAULT_MAX_BYTES = 256 * 1024 * 1024


def _valid_name(name: str) -> str:
    n = (name or "").replace("\\", "/").strip()
    parts = n.split("/")
    if not n or "\x00" in n or n.startswith("/") or any(p in ("", ".", "..") for p in parts) or len(n) > 512:
        raise ValueError(f"invalid asset name: {name!r}")
    return n


class LocalAssetStore:
    def __init__(self, db: Database, root: str | Path, *, max_bytes: int = DEFAULT_MAX_BYTES,
                 project_quota_bytes: Optional[int] = None) -> None:
        self.db, self.root = db, Path(root)
        self.max_bytes, self.quota = max_bytes, project_quota_bytes
        (self.root / "blobs").mkdir(parents=True, exist_ok=True)

    def _blob(self, sha: str) -> Path:
        return self.root / "blobs" / sha[:2] / sha

    @staticmethod
    def _a(r: Any) -> Asset:
        return Asset(r["asset_id"], r["project_id"], r["name"], r["sha256"], r["size"],
                     r["content_type"], r["created_at"])

    def usage(self, project_id: str) -> int:
        return int(self.db.query("SELECT COALESCE(SUM(size),0) FROM assets WHERE project_id=?",
                                 (project_id,))[0][0])

    def put(self, project_id: str, name: str, data: bytes,
            content_type: str = "application/octet-stream") -> Asset:
        name = _valid_name(name)
        if len(data) > self.max_bytes:
            raise ValueError("asset exceeds max size")
        existing = self.db.query("SELECT size FROM assets WHERE project_id=? AND name=?", (project_id, name))
        prior = existing[0]["size"] if existing else 0
        if self.quota is not None and self.usage(project_id) - prior + len(data) > self.quota:
            raise ValueError("project storage quota exceeded")
        sha = hashlib.sha256(data).hexdigest()
        path = self._blob(sha)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        now = time.time()
        if existing:
            old = self.db.query("SELECT * FROM assets WHERE project_id=? AND name=?", (project_id, name))[0]
            with self.db.tx() as c:
                c.execute("UPDATE assets SET sha256=?, size=?, content_type=?, created_at=? WHERE asset_id=?",
                          (sha, len(data), content_type, now, old["asset_id"]))
            self._gc(old["sha256"])
            return self.get(old["asset_id"])  # type: ignore[return-value]
        aid = f"ast_{uuid.uuid4().hex}"
        with self.db.tx() as c:
            c.execute("INSERT INTO assets VALUES (?,?,?,?,?,?,?)",
                      (aid, project_id, name, sha, len(data), content_type, now))
        return self.get(aid)  # type: ignore[return-value]

    def get(self, asset_id: str) -> Optional[Asset]:
        rows = self.db.query("SELECT * FROM assets WHERE asset_id=?", (asset_id,))
        return self._a(rows[0]) if rows else None

    def open_bytes(self, asset_id: str) -> bytes:
        a = self.get(asset_id)
        if a is None:
            raise KeyError(asset_id)
        data = self._blob(a.sha256).read_bytes()
        if hashlib.sha256(data).hexdigest() != a.sha256:
            raise IOError(f"asset {asset_id} blob integrity check failed")
        return data

    def list(self, project_id: str) -> list[Asset]:
        return [self._a(r) for r in self.db.query(
            "SELECT * FROM assets WHERE project_id=? ORDER BY name", (project_id,))]

    def remove(self, asset_id: str) -> bool:
        a = self.get(asset_id)
        if a is None:
            return False
        with self.db.tx() as c:
            c.execute("DELETE FROM assets WHERE asset_id=?", (asset_id,))
        self._gc(a.sha256)
        return True

    def _gc(self, sha: str) -> None:
        if not self.db.query("SELECT 1 FROM assets WHERE sha256=? LIMIT 1", (sha,)):
            try:
                self._blob(sha).unlink()
            except FileNotFoundError:
                pass
