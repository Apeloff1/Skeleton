"""Companion provenance meta for generated files. No secrets. No prose."""

from __future__ import annotations

from typing import Any


STEPS = (
    "vision",
    "snowball",
    "prototype",
    "mass_forge",
    "world",
    "cockpit",
    "export",
)
MAX_PATH = 120


class ProvenanceError(ValueError):
    """Provenance meta contract violation."""


def meta(
    *,
    path: str,
    seed: int,
    step: str,
    rotor: str = "default",
) -> dict[str, Any]:
    name = str(path or "").replace("\\", "/").strip()
    if not name or len(name) > MAX_PATH:
        raise ProvenanceError("path invalid")
    if ".." in name or name.startswith("/"):
        raise ProvenanceError("path traversal")
    cue = str(step or "").strip()
    if cue not in STEPS:
        raise ProvenanceError("unknown forge step")
    rotor_id = str(rotor or "").strip()
    if not rotor_id or len(rotor_id) > 32:
        raise ProvenanceError("rotor invalid")
    if any(token in name.lower() for token in (".env", "id_rsa", ".pem")):
        raise ProvenanceError("secret path")
    return {
        "kind": "provenance",
        "path": name,
        "meta_path": name + ".meta.json",
        "seed": int(seed),
        "step": cue,
        "rotor": rotor_id,
        "stored_prose": 0,
    }
