"""
DNAHelix persistence for local AI.
Emit pairs on forge, read from genos organ. Local jsonl under chronicle. No chain.
"""
from typing import List, Dict
import json
from pathlib import Path

class HelixPersist:
    def __init__(self, path: str = "chronicle/helix.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, pairs: List[Dict]) -> None:
        with self.path.open("a") as f:
            for p in pairs:
                f.write(json.dumps(p) + "\n")

    def read_all(self) -> List[Dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
