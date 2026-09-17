"""GB-14 three-artifact export cards. No zip bytes with a Godot binary inside."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.game.emit_tree import build


BUNDLES = ("godot_project", "web_stub", "data_only")


class ZipBundleError(ValueError):
    """Zip bundle contract violation."""


def _digest(name: str, seed: int, files: list[str]) -> str:
    blob = json.dumps({"name": name, "seed": seed, "files": files}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def bundles(*, seed: int = 8847291) -> dict[str, Any]:
    tree = build(seed=int(seed))
    godot_files = [name for name in tree["files"] if not name.endswith(".meta.json")]
    data_files = [name for name in tree["files"] if name.startswith("data/") or name.startswith("reports/")]
    web_files = ["data/spec.json", "world.json", "reports/build_report.md"]
    rows = [
        {
            "name": "godot_project",
            "files": godot_files,
            "digest": _digest("godot_project", seed, godot_files),
            "godot_binary": 0,
        },
        {
            "name": "web_stub",
            "files": web_files,
            "digest": _digest("web_stub", seed, web_files),
            "godot_binary": 0,
        },
        {
            "name": "data_only",
            "files": data_files,
            "digest": _digest("data_only", seed, data_files),
            "godot_binary": 0,
        },
    ]
    if {row["name"] for row in rows} != set(BUNDLES):
        raise ZipBundleError("bundle set incomplete")
    return {
        "kind": "zip_bundle",
        "seed": int(seed),
        "n": len(rows),
        "bundles": rows,
        "spec": "data/spec.json",
        "sota_ready": False,
        "stored_prose": 0,
        "ok": True,
    }
