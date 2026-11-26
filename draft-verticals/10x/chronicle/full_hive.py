"""Full hive chronicle: merkle gossip, root history, tournament, helix jsonl. No chain no coin.
"""
import hashlib
import json
from typing import List, Dict
from datetime import datetime

class FullHive:
    def __init__(self):
        self.helix: List[Dict] = []
        self.roots: List[str] = []

    def append(self, pairs: List, run_id: str) -> str:
        entry = {"ts": datetime.utcnow().isoformat(), "run": run_id, "pairs": pairs}
        entry["merkle"] = hashlib.sha256(json.dumps(entry).encode()).hexdigest()
        self.helix.append(entry)
        root = hashlib.sha256("".join(e["merkle"] for e in self.helix).encode()).hexdigest()
        self.roots.append(root)
        return root

    def tournament(self, peer_roots: List[str]) -> Dict:
        common = sum(1 for a,b in zip(self.roots, peer_roots) if a==b)
        return {"common_prefix": common, "local": len(self.roots)}

    def persist(self, path: str):
        with open(path, "w") as f:
            for e in self.helix:
                f.write(json.dumps(e)+"\n")
