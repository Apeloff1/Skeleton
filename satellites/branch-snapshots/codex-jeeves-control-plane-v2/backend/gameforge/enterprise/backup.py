from __future__ import annotations
import os
import json
import tarfile
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("gameforge.backup")


def _data_dir() -> Path:
    p = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
    p.mkdir(parents=True, exist_ok=True)
    return p


class BackupService:
    def __init__(self, backup_dir: Optional[str] = None):
        self.backup_dir = Path(backup_dir or _data_dir() / "backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.s3 = None
        try:
            from gameforge.enterprise.backup_s3 import S3BackupUploader

            self.s3 = S3BackupUploader()
        except Exception:
            self.s3 = None

    async def _write_local_snapshot(self, label: str) -> Path:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        name = f"gameforge_{label}_{ts}.tar.gz"
        path = self.backup_dir / name
        data_root = _data_dir()
        with tarfile.open(path, "w:gz") as tar:
            # include common local artifacts if present
            for rel in ("gameforge_diaries.db", "agents", "audit", "kms_wrapped"):
                p = data_root / rel
                if p.exists():
                    tar.add(p, arcname=rel)
            meta = {
                "label": label,
                "created_at": datetime.utcnow().isoformat(),
                "version": "1.0.0-enterprise",
            }
            meta_path = self.backup_dir / f".meta_{ts}.json"
            meta_path.write_text(json.dumps(meta, indent=2))
            tar.add(meta_path, arcname="backup_meta.json")
            try:
                meta_path.unlink()
            except Exception:
                pass
        return path

    async def create_snapshot(self, label: str = "manual") -> dict:
        local_path = await self._write_local_snapshot(label)
        result = {
            "local_path": str(local_path),
            "created_at": datetime.utcnow().isoformat(),
            "label": label,
            "size_bytes": local_path.stat().st_size if local_path.exists() else 0,
        }
        if self.s3 and getattr(self.s3, "enabled", False):
            try:
                result["s3"] = self.s3.upload_file(str(local_path))
            except Exception as e:
                result["s3"] = {"uploaded": False, "error": str(e)}
        else:
            result["s3"] = {"uploaded": False, "reason": "disabled"}
        logger.info("Backup created %s", result["local_path"])
        return result
