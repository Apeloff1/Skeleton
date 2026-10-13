"""Deterministic source manifest shared by the Godot CLI, API, and projector.

This receipt describes *emitted text content* only, not runtime behavior or
Godot boot success. No filesystem paths, timestamps, or host dependencies.
"""
from __future__ import annotations

import hashlib
import json
from typing import Mapping

SCHEMA = "skeleton.forge.source_manifest.v1"


def source_manifest(files: Mapping[str, str]) -> dict[str, object]:
    if not isinstance(files, Mapping):
        raise TypeError("generated source files must be a mapping")
    hashes: dict[str, str] = {}
    for name, body in files.items():
        if not isinstance(name, str) or not name:
            raise ValueError("generated source name must be a non-empty string")
        if not isinstance(body, str):
            raise TypeError(f"generated source {name!r} must be a string")
        hashes[name] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    hashes = dict(sorted(hashes.items()))
    digest = hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"schema": SCHEMA, "file_count": len(hashes),
            "files": hashes, "sha256": digest}
