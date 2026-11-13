"""
Operational Audit Log. Append-only local log of all dispatches, receipts, and G stamps.
Fills the audit gap. No remote.
"""
from typing import Dict
from pathlib import Path
import json
from datetime import datetime

class AuditLog:
    def __init__(self, path: str = "chronicle/audit.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: Dict) -> None:
        event["ts"] = datetime.utcnow().isoformat()
        with self.path.open("a") as f:
            f.write(json.dumps(event) + "\n")

    def tail(self, n: int = 10) -> list:
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()
        return [json.loads(l) for l in lines[-n:] if l.strip()]
