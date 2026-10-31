"""Completionist packager: bundles sealed Godot files into a deliverable pack.
"""
from __future__ import annotations
from typing import Dict, Any, List

def package_sealed(result: Dict[str, Any]) -> Dict[str, Any]:
    if not result.get("sealed"):
        return {"ok": False, "reason": "not_sealed", "pack": {}}
    files = result.get("godot_files", [])
    if len(files) < 3:
        return {"ok": False, "reason": "incomplete_godot", "pack": {}}
    pack = {
        "name": "jeeves_studio_pack",
        "era": result.get("era"),
        "mode": result.get("mode"),
        "fidelity": result.get("fidelity"),
        "optical": result.get("optical"),
        "files": files,
        "rooms": result.get("rooms"),
        "phases": result.get("phases", []),
        "narrative": result.get("narrative"),
        "status": "completionist",
    }
    return {"ok": True, "reason": "ok", "pack": pack}
