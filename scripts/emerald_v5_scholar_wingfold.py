"""Byte-exact Scholar V5 terminal-wing correction, not automatic adoption.

Appends 760 independently corrected quaternion streams. Retains all original
mesh/material/skin/morph bytes and the entire final growth clip. The correction
is still unqualified for continuous collision, artist or physical RTX approval.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import mmap
import os
from pathlib import Path
import struct
import numpy as np

DONOR_SHA = "c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a"
SOURCE_SHA = "db15c598fe3c6ef71384ca5f834c7eb2271014819ff0603207d454a87c03fdb9"
SOURCE_BYTES = 112509064
OUTPUT_SHA = "3bf57f602c905c1c6864c2fdddcc7df3bd79699bcbccab0c5c2d83480fa7b877"
OUTPUT_BYTES = 113305100
ANGLE = .18
TARGET_SKIN_JOINTS = (79, 91)
CLIP_COUNT = 380
MAX_JSON = 32 * 1024**2
MAX_MODEL = 512 * 1024**2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def hash_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def corrected_quaternions(quaternions, angle=ANGLE):
    """Postmultiply a unit quaternion by local-Z angular correction."""
    require(isinstance(quaternions, np.ndarray) and quaternions.ndim == 2
            and quaternions.shape[1] == 4 and np.isfinite(quaternions).all(),
            "invalid quaternion input")
    require(np.max(np.abs(np.linalg.norm(quaternions, axis=1) - 1)) < 2e-5,
            "unqualified input quaternion")
    require(math.isfinite(angle) and 0.05 <= angle <= .35, "unapproved angle")
    s, c = math.sin(angle/2), math.cos(angle/2)
    x, y, z, w = quaternions.T.astype(np.float64)
    result = np.column_stack((c*x+s*y, c*y-s*x, c*z+s*w, c*w-s*z))
    result /= np.linalg.norm(result, axis=1)[:, None]
    require(np.isfinite(result).all(), "nonfinite corrected rotation")
    return np.ascontiguousarray(result, dtype="<f4")


def parse_model(path):
    source = Path(path)
    require(source.is_file() and not source.is_symlink() and
            source.stat().st_size == SOURCE_BYTES and
            hash_file(source) == SOURCE_SHA, "original Scholar V4 identity mismatch")
    handle = source.open("rb")
    raw = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
    try:
        require(len(raw) >= 32, "truncated GLB")
        magic, version, total, jslen, tag = struct.unpack_from("<4sIIII", raw)
        require((magic, version, total, tag) == (b"glTF", 2, len(raw), 0x4e4f534a)
                and 4 <= jslen <= MAX_JSON and jslen % 4 == 0, "invalid GLB header")
        binary_len, binary_tag = struct.unpack_from("<II", raw, 20+jslen)
        start = 28+jslen
        require(binary_tag == 0x004e4942 and start+binary_len == total,
                "wrong GLB binary size")
        doc = json.loads(raw[20:20+jslen])
        require(doc["asset"]["version"] == "2.0"
                and doc["extras"]["stage"] == "scholar"
                and doc["extras"]["donorSha256"] == DONOR_SHA,
                "wrong donor or evolution stage")
        skin = doc["skins"]
        require(len(skin) == 1 and len(skin[0]["joints"]) == 108
                and len(doc["animations"]) == CLIP_COUNT+1,
                "rig or clip catalogue differs")
        require(doc["buffers"] == [{"byteLength": binary_len}], "unexpected embedded buffer")
        return handle, raw, doc, start, binary_len
    except BaseException:
        raw.close()
        handle.close()
        raise


def rotation_accessor(raw, doc, start, index):
    row = doc["accessors"][index]
    view = doc["bufferViews"][row["bufferView"]]
    require(row["type"] == "VEC4" and row["componentType"] == 5126
            and row["count"] > 0 and "sparse" not in row
            and "byteStride" not in view, "unsafe rotation accessor")
    local = row.get("byteOffset", 0)
    offset = view.get("byteOffset", 0) + local
    length = row["count"]*16
    require(local >= 0 and local+length <= view["byteLength"]
            and offset+length <= doc["buffers"][0]["byteLength"],
            "rotation accessor outside buffer")
    return np.frombuffer(raw, dtype="<f4", count=row["count"]*4,
                         offset=start+offset).reshape(-1, 4)


def build(source, destination):
    dest = Path(destination)
    require(dest.parent.is_dir() and not dest.parent.is_symlink()
            and not os.path.lexists(dest), "existing trusted destination parent required")
    handle, raw, original, start, binary_len = parse_model(source)
    try:
        doc = copy.deepcopy(original)
        ids = {doc["skins"][0]["joints"][i] for i in TARGET_SKIN_JOINTS}
        names = [item["name"] for item in doc["animations"]]
        require(len(names) == len(set(names)) and
                names[-1] == "growth-scholar-to-pathfinder",
                "wrong growth animation or duplicate clips")
        chunks = []
        length = binary_len
        updated = 0
        for animation in doc["animations"][:CLIP_COUNT]:
            seen = set()
            for channel in animation["channels"]:
                target = channel["target"]
                node = target["node"]
                if node not in ids or target["path"] != "rotation":
                    continue
                require(node not in seen, "duplicate rotation target")
                seen.add(node)
                sampler = animation["samplers"][channel["sampler"]]
                corrected = corrected_quaternions(
                    rotation_accessor(raw, original, start, sampler["output"]))
                padding = (-length) % 4
                chunks.extend((b"\0"*padding, corrected.tobytes()))
                length += padding
                view = len(doc["bufferViews"])
                doc["bufferViews"].append({
                    "buffer": 0, "byteOffset": length,
                    "byteLength": corrected.nbytes})
                sampler["output"] = len(doc["accessors"])
                doc["accessors"].append({
                    "bufferView": view, "componentType": 5126,
                    "count": len(corrected), "type": "VEC4"})
                length += corrected.nbytes
                updated += 1
            require(seen == ids, "missing terminal rotation in "+animation["name"])
        require(updated == 2*CLIP_COUNT and
                doc["animations"][-1] == original["animations"][-1],
                "incomplete track edit or modified growth")
        doc["buffers"][0]["byteLength"] = length
        doc["asset"]["generator"] = "Emerald original-donor Scholar wing-fold candidate r1"
        doc["extras"]["wingFoldCorrection"] = {
            "kind": "experimental-terminal-joint-post-rotation",
            "joint_ids": list(TARGET_SKIN_JOINTS),
            "local_z_radians": ANGLE,
            "source_model_sha256": SOURCE_SHA,
            "source_donor_sha256": DONOR_SHA,
            "original_tracks_modified": False,
            "original_growth_unchanged": True,
            "continuous_clearance_verified": False,
            "artist_approved": False,
            "physical_rtx_verified": False,
            "equipment_enabled": False,
            "release_qualified": False,
        }
        js = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        js += b" "*((-len(js))%4)
        tail = (-length)%4
        total = 28+len(js)+length+tail
        require(total < MAX_MODEL, "model exceeds bounds")
        try:
            with dest.open("xb") as out:
                out.write(struct.pack("<4sIIII", b"glTF", 2, total,
                                      len(js), 0x4e4f534a))
                out.write(js)
                out.write(struct.pack("<II", length+tail, 0x004e4942))
                out.write(raw[start:start+binary_len])
                for chunk in chunks:
                    out.write(chunk)
                out.write(b"\0"*tail)
                out.flush()
                os.fsync(out.fileno())
            require(dest.stat().st_size == OUTPUT_BYTES and
                    hash_file(dest) == OUTPUT_SHA,
                    "reproduction differs from independently measured V5 output")
        except BaseException:
            # Do not expose failed or partial bytes as an accepted candidate.
            if dest.exists():
                dest.unlink()
            raise
        return {"schema": "skeleton.emerald.scholar-wingfold-rebuild.v1",
                "sha256": OUTPUT_SHA, "bytes": OUTPUT_BYTES,
                "source_sha256": SOURCE_SHA, "donor_sha256": DONOR_SHA,
                "corrected_tracks": updated, "radians": ANGLE,
                "growth_unchanged": True, "adopted": False,
                "continuous_collision_qualified": False,
                "artist_approved": False, "release_qualified": False}
    finally:
        raw.close()
        handle.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
