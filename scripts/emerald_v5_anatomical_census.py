"""Classify every exact-pinned Emerald triangle into anatomical contact cohorts.

A successful classification does NOT qualify contact or continuous collision.
Produces an explicit finite worklist for remaining high-risk posed-mesh checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import mmap
import os
from pathlib import Path
import struct
from typing import Any

import numpy as np

DONOR_SHA = "c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a"
PINNED = {
    ("hatchling", "v4"): (111849460, "452371639f28e5ade305b3ba1aa506804d9749197936339817bed027f320d38f"),
    ("scout", "v4"): (112199628, "0ca21a7e3889d0bac5df48292fd711a7325b0373add2a84710540d3814d96d2b"),
    ("scholar", "v4"): (112509064, "db15c598fe3c6ef71384ca5f834c7eb2271014819ff0603207d454a87c03fdb9"),
    ("pathfinder", "v4"): (112706532, "e51e44a3277da1123df017d23f41aee43e373ea1c9e126f30dafd9a24c213092"),
    ("archivist", "v4"): (112829184, "0b7804643c65a5eb06f5baac2008d88b101b363613d2244016b3a33470c18d8f"),
    ("scholar", "v5"): (113305100, "3bf57f602c905c1c6864c2fdddcc7df3bd79699bcbccab0c5c2d83480fa7b877"),
    ("pathfinder", "v5"): (114687832, "80a98c198f5d8a6e101b571a9def6869904df4dfb0e5d90cba33f8890de9112f"),
    ("archivist", "v5"): (114810480, "569fdf85be64705b857a43e2491b62ae6970fe90739c1050ffb49494da642b27"),
}
COHORTS = (
    ("torso", 0, 8),
    ("head", 8, 14),
    ("forelegs", 14, 24),
    ("hindlegs", 24, 34),
    ("tail", 34, 44),
    ("wing_primary_near", 44, 56),
    ("wing_primary_far", 56, 67),
    ("wing_mounted_detail", 67, 68),
    ("wing_flight_near", 68, 80),
    ("wing_flight_far", 80, 92),
    ("rig_correctives", 92, 108),
)
OLD_REGION_RANGES = (
    ("head", 8, 14), ("fore_near", 14, 19), ("fore_far", 19, 24),
    ("hind_near", 24, 29), ("hind_far", 29, 34),
    ("wing_near", 68, 80), ("wing_far", 80, 92),
)
RISK_PAIRS = (
    ("wing_flight_near", "wing_flight_far"),
    ("wing_flight_near", "torso"), ("wing_flight_far", "torso"),
    ("wing_primary_near", "torso"), ("wing_primary_far", "torso"),
    ("wing_flight_near", "head"), ("wing_flight_far", "head"),
    ("wing_flight_near", "forelegs"), ("wing_flight_far", "forelegs"),
    ("wing_flight_near", "hindlegs"), ("wing_flight_far", "hindlegs"),
    ("wing_flight_near", "tail"), ("wing_flight_far", "tail"),
    ("rig_correctives", "wing_flight_near"),
    ("rig_correctives", "wing_flight_far"),
    ("rig_correctives", "torso"),
    ("wing_mounted_detail", "torso"),
    ("head", "forelegs"), ("tail", "hindlegs"),
)
MAX_BYTES = 512*1024**2
MAX_JSON = 32*1024**2
MAX_ACCESSORS = 250000


def require(condition: Any, why: str) -> None:
    if not condition:
        raise ValueError(why)


def cohort_table() -> np.ndarray:
    lookup = np.full(108, -1, dtype=np.int16)
    for i, (_name, start, end) in enumerate(COHORTS):
        require(0 <= start < end <= 108 and np.all(lookup[start:end] == -1),
                "overlapping rig groups")
        lookup[start:end] = i
    require(np.all(lookup != -1), "missing rig joint classification")
    return lookup


def classify(weights: np.ndarray, joints: np.ndarray,
             faces: np.ndarray) -> tuple[np.ndarray, dict[str, int]]:
    """Two-of-three anatomical vote; three distinct groups remain unresolved.

    Does not treat weak or corrective influences as proven contact-safe.
    """
    require(weights.ndim == 2 and weights.shape[1] == 4 and
            joints.shape == weights.shape and
            faces.ndim == 2 and faces.shape[1] == 3 and
            len(weights) > 0 and len(faces) > 0, "invalid geometry arrays")
    require(np.issubdtype(joints.dtype, np.integer) and
            int(joints.min()) >= 0 and int(joints.max()) < 108 and
            np.isfinite(weights).all() and
            np.all(weights >= 0) and
            np.max(np.abs(weights.sum(axis=1)-1)) <= 2e-5,
            "unsafe skin weights or joint IDs")
    require(np.issubdtype(faces.dtype, np.integer) and
            int(faces.min()) >= 0 and int(faces.max()) < len(weights),
            "out-of-range triangle indices")
    strongest = np.argmax(weights, axis=1)
    dominant = joints[np.arange(len(weights)), strongest]
    category = cohort_table()[dominant]
    votes = category[faces]
    ab = votes[:, 0] == votes[:, 1]
    ac = votes[:, 0] == votes[:, 2]
    bc = votes[:, 1] == votes[:, 2]
    majority = np.where(ab | ac, votes[:, 0],
                        np.where(bc, votes[:, 1], -1)).astype(np.int16)
    counts = {name: int(np.count_nonzero(majority == i))
              for i, (name, _start, _end) in enumerate(COHORTS)}
    counts["three_way_mixed"] = int(np.count_nonzero(majority == -1))
    require(sum(counts.values()) == len(faces), "triangle census incomplete")
    return majority, counts


def prior_coverage(weights: np.ndarray, joints: np.ndarray,
                   faces: np.ndarray) -> dict[str, Any]:
    """Reconcile the earlier strict high-risk region selection independently."""
    dominant = joints[np.arange(len(weights)), np.argmax(weights, axis=1)]
    sufficient = weights.max(axis=1) >= 0.40
    occupied = np.zeros(len(faces), dtype=np.bool_)
    counts = {}
    for name, start, end in OLD_REGION_RANGES:
        eligible = (dominant >= start) & (dominant < end) & sufficient
        exact = np.all(eligible[faces], axis=1)
        require(not np.any(occupied & exact), "overlapping prior regions")
        occupied |= exact
        counts[name] = int(np.count_nonzero(exact))
    return {
        "old_classified_triangles": int(np.count_nonzero(occupied)),
        "old_unclassified_triangles": int(np.count_nonzero(~occupied)),
        "old_region_counts": counts,
    }


def worklist(counts: dict[str, int]) -> list[dict[str, Any]]:
    rows = []
    for a, b in RISK_PAIRS:
        rows.append({
            "cohorts": [a, b],
            "triangles_a": counts[a],
            "triangles_b": counts[b],
            "potential_cross_pairs": counts[a]*counts[b],
            "status": "unqualified-pose-and-interval",
            "required_evidence": [
                "source-bound sampled skinned triangle distance",
                "adaptive interval motion bounds",
                "independent equipment and material clearance",
            ],
        })
    rows.append({
        "cohorts": ["three_way_mixed", "all_other_cohorts"],
        "triangles_a": counts["three_way_mixed"],
        "triangles_b": sum(counts.values())-counts["three_way_mixed"],
        "potential_cross_pairs": counts["three_way_mixed"] *
                                 (sum(counts.values())-counts["three_way_mixed"]),
        "status": "unqualified-seam",
        "required_evidence": ["mixed-influence seam retopology review",
                              "non-adjacent posed-triangle contact screening"],
    })
    return rows


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_accessor(raw: mmap.mmap, doc: dict, data_start: int,
                  index: int, expected_type: str, component: int) -> np.ndarray:
    require(type(index) is int and 0 <= index < min(len(doc["accessors"]), MAX_ACCESSORS),
            "accessor index out of range")
    row = doc["accessors"][index]
    require(row["type"] == expected_type and row["componentType"] == component and
            "sparse" not in row and
            type(row["count"]) is int and 0 < row["count"] <= 2_000_000,
            "unsupported accessor")
    view = doc["bufferViews"][row["bufferView"]]
    require(view["buffer"] == 0 and "byteStride" not in view, "external or strided accessor")
    dtype = {5123: "<u2", 5125: "<u4", 5126: "<f4"}[component]
    components = {"SCALAR": 1, "VEC4": 4}[expected_type]
    count = row["count"]
    local = row.get("byteOffset", 0)
    offset = view.get("byteOffset", 0)+local
    size = np.dtype(dtype).itemsize*count*components
    require(type(offset) is int and type(local) is int and
            offset >= 0 and local >= 0 and
            local+size <= view["byteLength"] and
            offset+size <= doc["buffers"][0]["byteLength"] and
            offset % np.dtype(dtype).itemsize == 0,
            "accessor out of bounds")
    return np.frombuffer(raw, dtype=dtype, count=count*components,
                         offset=data_start+offset).reshape(-1, components).copy()


def classify_model(path: Path, stage: str, version: str) -> dict:
    key = (stage, version)
    require(key in PINNED, "stage/version is not an approved source pin")
    size, pinned_sha = PINNED[key]
    require(path.is_file() and not path.is_symlink() and
            32 <= path.stat().st_size <= MAX_BYTES and
            path.stat().st_size == size and
            sha256_file(path) == pinned_sha, "exact source SHA-256 or size differs")
    with path.open("rb") as stream:
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as raw:
            magic, gltf_version, total, jslen, tag = struct.unpack_from("<4sIIII", raw)
            require((magic, gltf_version, total, tag) == (b"glTF", 2, len(raw), 0x4e4f534a)
                    and jslen % 4 == 0 and 0 < jslen <= MAX_JSON,
                    "unsupported GLB")
            binary_bytes, binary_tag = struct.unpack_from("<II", raw, 20+jslen)
            start = 28+jslen
            require(start+binary_bytes == len(raw) and binary_tag == 0x004e4942,
                    "invalid embedded binary")
            doc = json.loads(raw[20:20+jslen])
            require(doc["asset"]["version"] == "2.0" and
                    doc["extras"]["stage"] == stage and
                    doc["extras"]["donorSha256"] == DONOR_SHA and
                    len(doc["skins"]) == 1 and len(doc["skins"][0]["joints"]) == 108 and
                    len(doc["animations"]) == 381 and
                    len(doc["meshes"]) == 1 and
                    len(doc["buffers"]) == 1 and
                    "uri" not in doc["buffers"][0] and
                    doc["buffers"][0]["byteLength"] <= binary_bytes,
                    "unexpected donor, rig or external asset")
            weights = []
            joints = []
            faces = []
            cursor = 0
            for primitive in doc["meshes"][0]["primitives"]:
                attributes = primitive["attributes"]
                joint = read_accessor(raw, doc, start, attributes["JOINTS_0"], "VEC4", 5123)
                weight = read_accessor(raw, doc, start, attributes["WEIGHTS_0"], "VEC4", 5126)
                index = read_accessor(raw, doc, start, primitive["indices"], "SCALAR", 5125)
                require(len(joint) == len(weight) and len(index) % 3 == 0 and
                        len(weight) <= 2_000_000 and
                        int(index.max()) < len(weight), "primitive triangle census mismatch")
                joints.append(joint)
                weights.append(weight)
                faces.append(index.reshape(-1, 3).astype(np.int32)+cursor)
                cursor += len(weight)
    joints_all = np.concatenate(joints, axis=0)
    weights_all = np.concatenate(weights, axis=0)
    faces_all = np.concatenate(faces, axis=0)
    cohort_index, counts = classify(weights_all, joints_all, faces_all)
    old = prior_coverage(weights_all, joints_all, faces_all)
    total = len(faces_all)
    safe_majority = total-counts["three_way_mixed"]
    return {
        "schema": "skeleton.emerald.full-mesh-anatomical-census.v1",
        "stage": stage, "source_generation": version,
        "model_bytes": size, "model_sha256": pinned_sha,
        "donor_sha256": DONOR_SHA,
        "skin_joints": 108, "animations": 381,
        "vertices": len(weights_all), "triangles": total,
        "classification_method": "two-of-three dominant vertex influences; not geometry clearance",
        "majority_assigned_triangles": safe_majority,
        "three_way_mixed_triangles": counts["three_way_mixed"],
        "triangle_classification_counts": counts,
        "prior_strict_coverage": old,
        "full_mesh_classified_or_explicitly_mixed": True,
        "pose_contact_tests_run": 0,
        "continuous_intervals_qualified": 0,
        "worklist": worklist(counts),
        "all_anatomical_contacts_qualified": False,
        "all_equipment_contacts_qualified": False,
        "continuous_collision_qualified": False,
        "real_renderer_qualified": False,
        "artistic_approved": False,
        "physical_rtx_verified": False,
        "release_qualified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--stage", choices=sorted({k[0] for k in PINNED}), required=True)
    parser.add_argument("--generation", choices=("v4", "v5"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(args.output.parent.is_dir() and not args.output.parent.is_symlink() and
            not os.path.lexists(args.output), "trusted new evidence path required")
    report = classify_model(args.model, args.stage, args.generation)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: v for k, v in report.items() if k != "worklist"}, indent=2))


if __name__ == "__main__":
    main()
