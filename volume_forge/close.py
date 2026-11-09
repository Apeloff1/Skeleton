"""Close. File counts live. Line counts are prior wc seals."""

from __future__ import annotations

import json
from pathlib import Path

SEALS = {
    "organ": {"dir": "emit", "files": 2368, "lines": 3329408},
    "masterplan": {"dir": "emit10", "files": 200, "lines": 15302600},
    "x10": {"dir": "emit100", "files": 200, "lines": 153003200},
    "x100": {"dir": "emit_x100", "files": 1, "lines": 7650009},
}

def close(root: Path) -> dict[str, object]:
    strata = []
    for name, spec in SEALS.items():
        path = root / spec["dir"]
        found = len(list(path.glob("**/*.py"))) if path.is_dir() else 0
        strata.append({"name": name, "files_found": found, "files_sealed": spec["files"], "lines_sealed": spec["lines"], "files_ok": found == spec["files"]})
    body = {"stored_prose": 0, "clip": 1.1, "files_ok": all(s["files_ok"] for s in strata), "strata": strata}
    dest = root / "reports" / "CLOSE.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return body
