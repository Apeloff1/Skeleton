"""Read-only sampled-keyframe audit of the exact repository-pinned Fold GLB.
Not a continuous collision, deformation, artistic, or GPU qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
from typing import BinaryIO

from dragon_atelier_admit import PIN, unique_object, invalid_constant

MAX_JSON = 32 * 1024 * 1024
MAX_TRACKS = 250_000
MAX_VALUES = 160_000_000
MAX_ACCESSORS = 250_000
WIDTH = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}


def require(value, message):
    if not value:
        raise ValueError(message)


def bounded_index(value, size, label):
    require(type(value) is int and 0 <= value < size, "invalid " + label)
    return value


def integer(value, low, high, label):
    require(type(value) is int and low <= value <= high, "invalid " + label)
    return value


def array(document, name, max_count):
    value = document.get(name)
    require(isinstance(value, list) and 0 < len(value) <= max_count, "invalid " + name)
    require(all(isinstance(item, dict) for item in value), "malformed " + name)
    return value


class TrackReader:
    def __init__(self, stream: BinaryIO, document: dict, binary_start: int, binary_size: int):
        self.stream = stream
        self.start = binary_start
        self.size = binary_size
        self.views = array(document, "bufferViews", MAX_ACCESSORS)
        self.accessors = array(document, "accessors", MAX_ACCESSORS)
        self.values_read = 0
        self.time_cache = {}
        self.output_cache = {}

    def layout(self, reference, expected=None):
        i = bounded_index(reference, len(self.accessors), "accessor reference")
        acc = self.accessors[i]
        require(acc.get("componentType") == 5126 and not acc.get("normalized") and "sparse" not in acc,
                "animation accessor must contain ordinary FLOAT data")
        shape = acc.get("type")
        require(shape in WIDTH and (expected is None or shape == expected), "invalid animation accessor shape")
        width = WIDTH[shape]
        count = integer(acc.get("count"), 1, 10_000_000, "accessor count")
        view = self.views[bounded_index(acc.get("bufferView"), len(self.views), "bufferView reference")]
        require(view.get("buffer") == 0, "non-embedded accessor")
        base = integer(view.get("byteOffset", 0), 0, self.size, "view offset")
        length = integer(view.get("byteLength"), 1, self.size - base, "view length")
        offset = integer(acc.get("byteOffset", 0), 0, length, "accessor offset")
        stride = integer(view.get("byteStride", width * 4), width * 4, 252, "accessor stride")
        require((base + offset) % 4 == 0 and stride % 4 == 0, "unaligned animation accessor")
        require(offset + (count - 1) * stride + width * 4 <= length, "animation accessor exceeds view")
        return i, width, count, self.start + base + offset, stride

    def samples(self, layout):
        _, width, count, start, stride = layout
        self.values_read += width * count
        require(self.values_read <= MAX_VALUES, "animation value budget exceeded")
        # The chunk is intentionally bounded even for interleaved source data.
        step = max(1, (1024 * 1024) // stride)
        for first in range(0, count, step):
            n = min(step, count - first)
            length = (n - 1) * stride + width * 4
            self.stream.seek(start + first * stride)
            block = self.stream.read(length)
            require(len(block) == length, "truncated animation data")
            for j in range(n):
                yield struct.unpack_from("<" + "f" * width, block, j * stride)

    def times(self, ref):
        i, _, count, *_ = layout = self.layout(ref, "SCALAR")
        if i in self.time_cache:
            return self.time_cache[i]
        first = last = None
        for (value,) in self.samples(layout):
            require(math.isfinite(value) and value >= 0 and (last is None or value > last),
                    "animation timestamps must be finite, nonnegative and strictly increasing")
            first = value if first is None else first
            last = value
        result = (count, first, last)
        self.time_cache[i] = result
        return result

    def output(self, ref, target, interpolation, keys, weights):
        shape = {"translation": "VEC3", "rotation": "VEC4", "scale": "VEC3", "weights": "SCALAR"}[target]
        i, _, count, *_ = layout = self.layout(ref, shape)
        multiplier = 3 if interpolation == "CUBICSPLINE" else 1
        require(count == keys * multiplier * (weights if target == "weights" else 1), "animation output count mismatch")
        cache_key = (i, target, interpolation)
        if cache_key in self.output_cache:
            return self.output_cache[cache_key]
        worst_rotation_error = 0.0
        for ordinal, values in enumerate(self.samples(layout)):
            require(all(math.isfinite(v) for v in values), "non-finite animation output")
            if target == "rotation" and (multiplier == 1 or ordinal % 3 == 1):
                norm = math.sqrt(sum(v * v for v in values))
                error = abs(norm - 1.0)
                worst_rotation_error = max(worst_rotation_error, error)
                require(error <= 0.025, "rotation key is not a near-unit quaternion")
        self.output_cache[cache_key] = worst_rotation_error
        return worst_rotation_error


def morph_count(node, meshes):
    mesh = meshes[bounded_index(node.get("mesh"), len(meshes), "morph target mesh")]
    primitives = mesh.get("primitives")
    require(isinstance(primitives, list) and bool(primitives), "invalid morph mesh")
    counts = []
    for primitive in primitives:
        targets = primitive.get("targets", [])
        require(isinstance(targets, list), "invalid morph target array")
        counts.append(len(targets))
    require(len(set(counts)) == 1 and 0 < counts[0] <= 1024, "inconsistent morph target count")
    return counts[0]


def audit_tracks(stream, document, binary_start, binary_size):
    nodes = array(document, "nodes", 8192)
    animations = array(document, "animations", 1024)
    meshes = document.get("meshes", [])
    require(isinstance(meshes, list) and len(meshes) <= 4096, "invalid mesh inventory")
    reader = TrackReader(stream, document, binary_start, binary_size)
    clips = []
    names = set()
    total_tracks = 0
    for anim in animations:
        name = anim.get("name")
        require(isinstance(name, str) and 0 < len(name) <= 256 and name not in names, "duplicate or invalid clip name")
        names.add(name)
        channels = array(anim, "channels", 8192)
        samplers = array(anim, "samplers", 8192)
        total_tracks += len(channels)
        require(total_tracks <= MAX_TRACKS, "animation track budget exceeded")
        seen = set()
        first = math.inf
        last = 0.0
        keys_total = 0
        worst = 0.0
        driven = set()
        for channel in channels:
            sampler = samplers[bounded_index(channel.get("sampler"), len(samplers), "sampler")]
            target = channel.get("target", {})
            node = bounded_index(target.get("node"), len(nodes), "animation node")
            path = target.get("path")
            require(path in ("translation", "rotation", "scale", "weights"), "unsupported animation target")
            require((node, path) not in seen, "duplicate node/path animation channel")
            seen.add((node, path))
            driven.add(node)
            interpolation = sampler.get("interpolation", "LINEAR")
            require(interpolation in ("LINEAR", "STEP", "CUBICSPLINE"), "unsupported interpolation")
            count, lo, hi = reader.times(sampler.get("input"))
            first, last = min(first, lo), max(last, hi)
            keys_total += count
            weights = morph_count(nodes[node], meshes) if path == "weights" else 1
            worst = max(worst, reader.output(sampler.get("output"), path, interpolation, count, weights))
        require(last > first, "clip has no positive time span")
        clips.append({"name": name, "channels": len(channels), "animated_nodes": len(driven),
                      "channel_keys": keys_total, "start_seconds": first, "end_seconds": last,
                      "max_rotation_norm_error": worst})
    return {"clips": clips, "tracks": total_tracks, "float_components_examined": reader.values_read,
            "unique_time_accessors": len(reader.time_cache), "unique_output_contracts": len(reader.output_cache)}


def identity(s):
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def audit_pinned(model: Path, pin: dict):
    require(model.name == "emerald_continuum.glb" and not model.is_symlink(), "original model path required")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(model, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size == pin["modelBytes"], "original byte size mismatch")
        require(hashlib.file_digest(stream, "sha256").hexdigest() == pin["modelSha256"], "original digest mismatch")
        stream.seek(0)
        magic, version, length, size, kind = struct.unpack("<4sIIII", stream.read(20))
        require(magic == b"glTF" and version == 2 and length == before.st_size and kind == 0x4e4f534a, "invalid GLB header")
        require(4 <= size <= MAX_JSON and size % 4 == 0 and 28 + size <= length, "invalid JSON size")
        document = json.loads(stream.read(size), object_pairs_hook=unique_object, parse_constant=invalid_constant)
        binary_size, marker = struct.unpack("<II", stream.read(8))
        require(marker == 0x004e4942 and binary_size % 4 == 0 and 28 + size + binary_size == length, "invalid embedded BIN")
        buffers = array(document, "buffers", 1)
        require(len(buffers) == 1 and "uri" not in buffers[0], "external buffer")
        declared = integer(buffers[0].get("byteLength"), 1, binary_size, "buffer byte count")
        require(binary_size - declared <= 3, "unexpected BIN padding")
        result = audit_tracks(stream, document, 28 + size, declared)
        require(len(result["clips"]) == 380, "wrong original clip count")
        require(identity(before) == identity(os.fstat(stream.fileno())), "asset changed during audit")
        return {"schema": "skeleton.emerald.sampled-animation-audit.v1", "model_sha256": pin["modelSha256"],
                "model_bytes": before.st_size, **result, "continuous_collision_verified": False,
                "physical_deformation_verified": False, "artist_approved": False, "physical_rtx_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(audit_pinned(args.model, json.loads(PIN.read_text(encoding="utf-8"))["native"]), indent=2))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, struct.error, OverflowError) as exc:
        parser.exit(2, "Animation audit rejected: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
