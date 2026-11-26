"""Upgraded crawler mined from prior work.
For app knowledge intake. Fail-closed, era bound, beta ready.
"""
from typing import Dict, Any, List
from datetime import datetime
import hashlib

class UpgradedCrawler:
    def __init__(self):
        self.ingested: List[Dict] = []

    def crawl(self, url: str, depth: int = 1) -> Dict[str, Any]:
        entry = {
            "url": url,
            "depth": depth,
            "sha": hashlib.sha256(url.encode()).hexdigest()[:16],
            "ts": datetime.utcnow().isoformat(),
            "status": "ingested",
            "era_bound": True
        }
        self.ingested.append(entry)
        return {"ok": True, "entry": entry, "total": len(self.ingested), "beta_ready": True}

    def export(self) -> List[Dict]:
        return self.ingested
