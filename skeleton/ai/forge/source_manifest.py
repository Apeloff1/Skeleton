"""Deterministic source manifest shared by the Godot CLI, API, and projector.

This receipt describes *emitted text content* only, not runtime behavior or
Godot boot success. No filesystem paths, timestamps, or host dependencies.
"""
from __future__ import annotations

import hashlib
import json
from typing import Mapping

SCHEMA = "skeleton.forge.source_manifest.v1"
MAX_SOURCE_FILE_BYTES = 100 * 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_SOURCE_FILES = 500_000
_SOURCE_HASH_CHUNK_CHARS = 64 * 1024


def source_manifest(files: Mapping[str, str]) -> dict[str, object]:
    # Reuse the exact path validation enforced when projecting to Godot.
    # Without this, an API-only run could attest paths a real build rejects.
    from skeleton.forge.projector import _validate

    if not isinstance(files, Mapping) or len(files) > MAX_SOURCE_FILES:
        raise ValueError("generated source file budget exceeded")
    checked = _validate(files)
    hashes: dict[str, str] = {}
    total_bytes = 0
    for name, body in checked.items():
        if not isinstance(name, str) or not name:
            raise ValueError("generated source name must be a non-empty string")
        if not isinstance(body, str):
            raise TypeError(f"generated source {name!r} must be a string")
        if len(body) > MAX_SOURCE_FILE_BYTES:
            raise ValueError("generated source text exceeds file byte budget")
        hasher = hashlib.sha256()
        file_bytes = 0
        # UTF-8 length is not equal to Python character length. Hash bounded
        # chunks to avoid allocating the entire source again in encoded form.
        for start in range(0, len(body), _SOURCE_HASH_CHUNK_CHARS):
            chunk = body[start:start + _SOURCE_HASH_CHUNK_CHARS].encode("utf-8")
            file_bytes += len(chunk)
            if file_bytes > MAX_SOURCE_FILE_BYTES:
                raise ValueError("generated source file exceeds byte budget")
            if file_bytes > MAX_SOURCE_TOTAL_BYTES - total_bytes:
                raise ValueError("generated source tree exceeds byte budget")
            hasher.update(chunk)
        total_bytes += file_bytes
        hashes[name] = hasher.hexdigest()
    hashes = dict(sorted(hashes.items()))
    index = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"))
    for chunk in encoder.iterencode(hashes):
        index.update(chunk.encode("utf-8"))
    return {"schema": SCHEMA, "file_count": len(hashes),
            "files": hashes, "sha256": index.hexdigest()}
