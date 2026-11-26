"""Versioned sprite and audio receipt for files the materialiser already writes.

Binary assets are not generated. When the emitted project has no sprite or
audio text, the receipt fail-closes to the stub the golden brief already
lists. When those paths are present, the receipt copies their sha256 digests.
"""
from __future__ import annotations

import hashlib
import json
from typing import Mapping

SCHEMA = "skeleton.forge.asset_manifest.v1"
MANIFEST_PATH = "assets/manifest.json"
STUB = "authored sprites, meshes, and audio"
_ASSET_SUFFIXES = (".png", ".webp", ".wav", ".ogg", ".mp3")


def asset_manifest_files(files: Mapping[str, str]) -> dict[str, str]:
    """Return the manifest file to copy into an already-materialised project."""
    if MANIFEST_PATH in files:
        return {}
    assets: list[dict[str, str]] = []
    for name in sorted(files):
        if not isinstance(name, str) or not name.endswith(_ASSET_SUFFIXES):
            continue
        body = files[name]
        if not isinstance(body, str):
            continue
        assets.append({
            "path": name,
            "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        })
    body = {
        "schema": SCHEMA,
        "version": 1,
        "assets": assets,
        "stubbed": None if assets else STUB,
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return {MANIFEST_PATH: json.dumps(body, sort_keys=True, indent=2) + "\n"}
