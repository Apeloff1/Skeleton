"""Offline, read-only admission of the original Emerald Atelier Fold GLB.
The expected digest must come from an independently trusted asset custodian.
No asset is downloaded, extracted, rewritten or activated by this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
from typing import Any

MAX_BYTES = 384 * 1024 * 1024
MAX_JSON = 32 * 1024 * 1024
MIN_CLIPS = 360
MIN_JOINTS = 92
SCHEMA = "skeleton.dragon.atelier-fold.admission.v1"
FAMILIES = ("ground", "takeoff", "flight", "landing")


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, value in pairs:
        require(name not in out, "duplicate JSON property")
        out[name] = value
    return out


def invalid_constant(value: str) -> Any:
    raise ValueError("non-finite JSON constant: " + value)


def rows(document: dict, key: str, ceiling: int) -> list:
    values = document.get(key, [])
    require(isinstance(values, list) and len(values) <= ceiling, "invalid " + key)
    require(all(isinstance(row, dict) for row in values), "invalid " + key + " row")
    return values


def index(value: Any, size: int, label: str) -> int:
    require(type(value) is int and 0 <= value < size, "invalid " + label)
    return value


def reject_external(value: Any) -> None:
    # Iterative traversal: don't follow external URLs, even in extensions.
    pending = [value]
    seen = 0
    while pending:
        part = pending.pop()
        seen += 1
        require(seen <= 5_000_000, "JSON structure exceeds policy")
        if isinstance(part, dict):
            require("uri" not in part and "url" not in part, "external resource locator denied")
            pending.extend(part.values())
        elif isinstance(part, list):
            pending.extend(part)


def inspect_glb(path: Path, expected: str) -> dict:
    require(re.fullmatch(r"[0-9a-f]{64}", expected) is not None, "trusted lowercase SHA-256 required")
    require(path.name == "emerald_continuum.glb", "original model filename required")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    require(not path.is_symlink(), "symlink asset denied")
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and 28 <= before.st_size <= MAX_BYTES, "invalid model size")
        digest = hashlib.sha256()
        header = source.read(20)
        digest.update(header)
        magic, version, length, json_size, kind = struct.unpack("<4sIIII", header)
        require(magic == b"glTF" and version == 2 and length == before.st_size, "invalid GLB envelope")
        require(kind == 0x4E4F534A and 4 <= json_size <= MAX_JSON and json_size % 4 == 0, "invalid JSON chunk")
        require(20 + json_size + 8 <= length, "missing binary chunk")
        payload = source.read(json_size)
        require(len(payload) == json_size, "truncated GLB JSON")
        digest.update(payload)
        chunk = source.read(8)
        require(len(chunk) == 8, "truncated binary header")
        digest.update(chunk)
        binary_size, binary_kind = struct.unpack("<II", chunk)
        require(binary_kind == 0x004E4942 and binary_size % 4 == 0 and 28 + json_size + binary_size == length, "invalid binary chunk")
        remaining = binary_size
        while remaining:
            block = source.read(min(remaining, 1024 * 1024))
            require(bool(block), "truncated binary chunk")
            digest.update(block)
            remaining -= len(block)
        after = os.fstat(source.fileno())
        require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "asset changed during read")
        require(digest.hexdigest() == expected, "asset digest mismatch")
    document = json.loads(payload.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=invalid_constant)
    require(isinstance(document, dict) and document.get("asset", {}).get("version") == "2.0", "invalid glTF document")
    reject_external(document)
    require(not document.get("extensionsRequired"), "required extensions need separate qualification")
    buffers = rows(document, "buffers", 1)
    require(len(buffers) == 1, "one embedded buffer required")
    declared = buffers[0].get("byteLength")
    require(type(declared) is int and 0 < declared <= binary_size and binary_size - declared <= 3, "buffer size mismatch")
    views = rows(document, "bufferViews", 200_000)
    for view in views:
        require(view.get("buffer") == 0, "external buffer denied")
        off, size = view.get("byteOffset", 0), view.get("byteLength")
        require(type(off) is int and type(size) is int and off >= 0 and size > 0 and off + size <= declared, "buffer view exceeds storage")
    nodes = rows(document, "nodes", 8192)
    skins = rows(document, "skins", 128)
    joints = set()
    for skin in skins:
        items = skin.get("joints")
        require(isinstance(items, list) and bool(items), "invalid skin")
        joints.update(index(i, len(nodes), "joint") for i in items)
    require(len(joints) >= MIN_JOINTS, "peak skeleton threshold not met")
    animations = rows(document, "animations", 1024)
    names = []
    for anim in animations:
        name = anim.get("name")
        require(isinstance(name, str) and 0 < len(name) <= 256 and name == name.strip() and name.isprintable(), "invalid animation name")
        channels, samplers = rows(anim, "channels", 8192), rows(anim, "samplers", 8192)
        require(bool(channels) and bool(samplers), "empty animation")
        names.append(name)
    require(len(names) >= MIN_CLIPS and len(set(names)) == len(names), "peak animation threshold or unique names not met")
    meshes = rows(document, "meshes", 4096)
    require(bool(meshes), "missing geometry")
    scenes = rows(document, "scenes", 64)
    require(bool(scenes), "missing scenes")
    return {"schema": SCHEMA, "asset": path.name, "sha256": expected,
            "bytes": length, "joints": len(joints), "clips": names,
            "claim": "digest-and-structure-only", "artistic_qualification": False,
            "unreal_qualification": False, "physical_rtx_qualification": False}


def bind_families(receipt: dict, mapping: dict) -> dict:
    require(isinstance(mapping, dict) and set(mapping) == set(FAMILIES), "all four explicit clip families required")
    seen = set()
    known = set(receipt["clips"])
    for family in FAMILIES:
        names = mapping[family]
        require(isinstance(names, list) and all(isinstance(n, str) for n in names), "invalid clip family")
        minimum = 20 if family != "ground" else 300
        require(len(names) >= minimum and len(set(names)) == len(names), "incomplete clip family")
        require(set(names) <= known and not seen.intersection(names), "unknown or overlapping clip names")
        seen.update(names)
    return {**receipt, "families": mapping}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--families", type=Path)
    args = parser.parse_args()
    try:
        receipt = inspect_glb(args.model, args.sha256)
        if args.families:
            with args.families.open("rb") as source:
                raw = source.read(256 * 1024 + 1)
            require(len(raw) <= 256 * 1024, "mapping too large")
            receipt = bind_families(receipt, json.loads(raw, object_pairs_hook=unique_object))
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError, AttributeError, RecursionError, struct.error) as exc:
        parser.exit(2, "Dragon asset not admitted: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
