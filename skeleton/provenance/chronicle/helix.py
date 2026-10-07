"""Append-only helix jsonl. Merkle of observe/forge/gossip roots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Helix:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, kind: str, root: str) -> dict:
        prev = self.tip()
        rec = {
            "kind": kind,
            "root": root,
            "prev": prev,
            "link": _digest((prev or "genesis") + ":" + kind + ":" + root),
            "stored_prose": 0,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        return rec

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out

    def tip(self) -> str | None:
        recs = self.records()
        return recs[-1]["link"] if recs else None

    def verify(self) -> bool:
        prev = None
        for rec in self.records():
            if rec.get("prev") != prev:
                return False
            expect = _digest((prev or "genesis") + ":" + rec["kind"] + ":" + rec["root"])
            if rec.get("link") != expect:
                return False
            prev = rec["link"]
        return True

    def tamper(self, index: int, root: str) -> None:
        recs = self.records()
        recs[index]["root"] = root
        self.path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
