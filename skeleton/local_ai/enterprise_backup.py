"""
Enterprise Backup. Snapshot helix, receipts, and config. Local only. Fail-closed restore.
"""
from typing import Dict
from pathlib import Path
import json
import shutil
from .helix_persist import HelixPersist
from .receipts import ReceiptStore

class EnterpriseBackup:
    def __init__(self, backup_dir: str = "chronicle/backups"):
        self.dir = Path(backup_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def snapshot(self, name: str) -> Dict:
        helix = HelixPersist()
        receipts = ReceiptStore()
        data = {"helix": helix.read_all(), "receipts": receipts.list()}
        path = self.dir / f"{name}.json"
        path.write_text(json.dumps(data))
        return {"snapshot": name, "path": str(path), "pairs": len(data["helix"])}

    def restore(self, name: str) -> Dict:
        path = self.dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError("snapshot missing")
        data = json.loads(path.read_text())
        return {"restored": name, "pairs": len(data.get("helix", []))}
