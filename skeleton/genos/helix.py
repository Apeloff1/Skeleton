"""DNAHelix pair payloads. Chronicle file. Not root-consensus jsonl."""

from __future__ import annotations

from pathlib import Path

from skeleton.genos.law import HELIX_NAME


class DNAHelix:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else Path(".")
        self.path = self.root / HELIX_NAME
        self.pairs: list[tuple[str, str]] = []

    def emit(self, a: str, b: str) -> dict:
        pair = (a, b)
        self.pairs.append(pair)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write('{"a":"%s","b":"%s","stored_prose":0}\n' % (a, b))
        return {"kind": "helix", "n": len(self.pairs), "stored_prose": 0}

    def read(self) -> list[tuple[str, str]]:
        if not self.path.exists():
            return list(self.pairs)
        out: list[tuple[str, str]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if '"a":"' in line and '"b":"' in line:
                a = line.split('"a":"', 1)[1].split('"', 1)[0]
                b = line.split('"b":"', 1)[1].split('"', 1)[0]
                out.append((a, b))
        return out
