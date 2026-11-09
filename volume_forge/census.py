"""Census from disk. Estimates are not law."""

from __future__ import annotations

import json
from pathlib import Path

def count_tree(root: Path) -> dict[str, object]:
    files = lines = bytes_ = 0
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        files += 1
        lines += text.count("\n")
        bytes_ += path.stat().st_size
    return {"files": files, "lines": lines, "bytes": bytes_}

def write_ledger(root: Path, dest: Path) -> dict[str, object]:
    census = count_tree(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(census, indent=2), encoding="utf-8")
    return census
