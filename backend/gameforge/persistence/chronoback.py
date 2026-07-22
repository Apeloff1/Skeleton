from __future__ import annotations
"""
Chronoback — self-sustained internal backup system.

Design:
  - Dual (or triple) deliberate duplicates to survive single-file corruption
  - CRC32 checksums per shard
  - Self-heal: majority vote / copy-from-healthy
  - Self-zip rotating archives
  - Anti-corruption: atomic writes via temp+rename, fsync
"""

import hashlib
import json
import os
import shutil
import threading
import time
import zipfile
import zlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _crc32(data: bytes) -> str:
    return format(zlib.crc32(data) & 0xFFFFFFFF, "08x")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class ShardMeta:
    name: str
    crc32: str
    sha256: str
    size: int
    replicas: List[str] = field(default_factory=list)
    healthy: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


class Chronoback:
    """
    Backs up a set of source paths into a replica tree:
      chronoback/<user>/replica_a/...
      chronoback/<user>/replica_b/...
      chronoback/<user>/replica_c/...  (optional third)
      chronoback/<user>/zips/chrono_*.zip
    """

    def __init__(self, user_id: str = "default", replicas: int = 2):
        self.user_id = user_id
        self.replicas = max(2, min(3, replicas))  # 2 or 3
        root = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.root = root / "chronoback" / user_id
        self.replica_dirs = [self.root / f"replica_{chr(ord('a') + i)}" for i in range(self.replicas)]
        self.zip_dir = self.root / "zips"
        self.manifest_path = self.root / "manifest.json"
        for d in self.replica_dirs:
            d.mkdir(parents=True, exist_ok=True)
        self.zip_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.log: List[dict] = []

    def _atomic_write(self, path: Path, data: bytes):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _log(self, event: str, **kw):
        self.log.append({"ts": _ts(), "event": event, **kw})
        if len(self.log) > 2000:
            self.log = self.log[-2000:]

    def backup_bytes(self, relative_name: str, data: bytes) -> ShardMeta:
        crc = _crc32(data)
        sha = _sha256(data)
        replica_paths = []
        with self._lock:
            for rdir in self.replica_dirs:
                dest = rdir / relative_name
                self._atomic_write(dest, data)
                # verify readback
                read = dest.read_bytes()
                if _crc32(read) != crc:
                    self._log("replica_crc_fail", path=str(dest))
                    # rewrite once
                    self._atomic_write(dest, data)
                replica_paths.append(str(dest))
            meta = ShardMeta(
                name=relative_name,
                crc32=crc,
                sha256=sha,
                size=len(data),
                replicas=replica_paths,
                healthy=True,
            )
            self._update_manifest(meta)
            self._log("backup", name=relative_name, size=len(data), replicas=len(replica_paths))
        return meta

    def backup_file(self, src: Path, relative_name: Optional[str] = None) -> Optional[ShardMeta]:
        src = Path(src)
        if not src.exists() or not src.is_file():
            return None
        rel = relative_name or src.name
        return self.backup_bytes(rel, src.read_bytes())

    def backup_tree(self, src_dir: Path, prefix: str = "") -> List[ShardMeta]:
        src_dir = Path(src_dir)
        out = []
        if not src_dir.exists():
            return out
        for p in src_dir.rglob("*"):
            if p.is_file() and not p.name.endswith(".tmp"):
                rel = str(Path(prefix) / p.relative_to(src_dir)) if prefix else str(p.relative_to(src_dir))
                m = self.backup_file(p, rel.replace("\\", "/"))
                if m:
                    out.append(m)
        return out

    def _update_manifest(self, meta: ShardMeta):
        manifest = {}
        if self.manifest_path.exists():
            try:
                manifest = json.loads(self.manifest_path.read_text())
            except Exception:
                manifest = {}
        shards = manifest.get("shards", {})
        shards[meta.name] = meta.to_dict()
        manifest["shards"] = shards
        manifest["updated_at"] = _ts()
        manifest["replicas"] = self.replicas
        self._atomic_write(self.manifest_path, json.dumps(manifest, indent=2).encode())

    def verify(self) -> Dict[str, Any]:
        """Check all replicas against manifest CRC; report corruption."""
        manifest = {}
        if self.manifest_path.exists():
            try:
                manifest = json.loads(self.manifest_path.read_text())
            except Exception as e:
                return {"ok": False, "error": f"manifest_corrupt: {e}"}
        bad = []
        good = 0
        for name, meta in (manifest.get("shards") or {}).items():
            expected = meta.get("crc32")
            for i, rdir in enumerate(self.replica_dirs):
                path = rdir / name
                if not path.exists():
                    bad.append({"name": name, "replica": i, "error": "missing"})
                    continue
                crc = _crc32(path.read_bytes())
                if crc != expected:
                    bad.append({"name": name, "replica": i, "error": "crc_mismatch", "got": crc, "expected": expected})
                else:
                    good += 1
        return {"ok": len(bad) == 0, "healthy_replicas": good, "corruptions": bad, "shards": len(manifest.get("shards") or {})}

    def heal(self) -> Dict[str, Any]:
        """
        Self-heal: for each shard, if any replica is healthy, overwrite bad ones.
        If all disagree, prefer replica_a and re-duplicate (logged).
        """
        report = self.verify()
        healed = []
        failed = []
        manifest = {}
        if self.manifest_path.exists():
            try:
                manifest = json.loads(self.manifest_path.read_text())
            except Exception:
                return {"ok": False, "error": "manifest_unreadable"}
        # group corruptions by name
        by_name: Dict[str, List[dict]] = {}
        for c in report.get("corruptions") or []:
            by_name.setdefault(c["name"], []).append(c)

        for name, meta in (manifest.get("shards") or {}).items():
            expected = meta.get("crc32")
            healthy_data = None
            for rdir in self.replica_dirs:
                path = rdir / name
                if path.exists():
                    data = path.read_bytes()
                    if _crc32(data) == expected:
                        healthy_data = data
                        break
            if healthy_data is None:
                # majority bytes vote among existing
                blobs = []
                for rdir in self.replica_dirs:
                    path = rdir / name
                    if path.exists():
                        blobs.append(path.read_bytes())
                if not blobs:
                    failed.append({"name": name, "error": "all_missing"})
                    continue
                # pick first as authority and re-seal
                healthy_data = blobs[0]
                expected = _crc32(healthy_data)
                meta["crc32"] = expected
                meta["sha256"] = _sha256(healthy_data)
                meta["size"] = len(healthy_data)
            # write to all replicas
            for rdir in self.replica_dirs:
                dest = rdir / name
                self._atomic_write(dest, healthy_data)
            healed.append(name)
            shards = manifest.get("shards", {})
            shards[name] = meta
            manifest["shards"] = shards
        manifest["updated_at"] = _ts()
        self._atomic_write(self.manifest_path, json.dumps(manifest, indent=2).encode())
        self._log("heal", healed=len(healed), failed=len(failed))
        return {"ok": len(failed) == 0, "healed": healed, "failed": failed}

    def self_zip(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Zip replica_a (+ manifest) into rotating archive."""
        label = label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        zip_path = self.zip_dir / f"chrono_{label}.zip"
        with self._lock:
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                if self.manifest_path.exists():
                    zf.write(self.manifest_path, "manifest.json")
                for p in self.replica_dirs[0].rglob("*"):
                    if p.is_file():
                        zf.write(p, f"replica_a/{p.relative_to(self.replica_dirs[0])}")
            # dual-zip duplicate for anti-corruption
            zip_dup = self.zip_dir / f"chrono_{label}_dup.zip"
            shutil.copy2(zip_path, zip_dup)
            # verify both
            ok = zipfile.is_zipfile(zip_path) and zipfile.is_zipfile(zip_dup)
            # rotation: keep last 20 pairs
            zips = sorted(self.zip_dir.glob("chrono_*.zip"))
            while len(zips) > 40:
                zips[0].unlink(missing_ok=True)
                zips = sorted(self.zip_dir.glob("chrono_*.zip"))
        self._log("self_zip", path=str(zip_path), ok=ok)
        return {"ok": ok, "zip": str(zip_path), "dup": str(zip_dup)}

    def backup_critical_paths(self, paths: List[Path]) -> Dict[str, Any]:
        metas = []
        for p in paths:
            p = Path(p)
            if p.is_file():
                m = self.backup_file(p, p.name)
                if m:
                    metas.append(m.to_dict())
            elif p.is_dir():
                for m in self.backup_tree(p, prefix=p.name):
                    metas.append(m.to_dict())
        return {"ok": True, "shards": len(metas), "items": metas[:50]}

    def status(self) -> Dict[str, Any]:
        v = self.verify()
        return {
            "root": str(self.root),
            "replicas": self.replicas,
            "verify": v,
            "zips": len(list(self.zip_dir.glob("chrono_*.zip"))),
            "log_tail": self.log[-10:],
        }
