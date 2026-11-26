"""Bounded anatomical AABB screen of actual skinned V5 meshes.

Requires the exact, reviewed contact_audit.py from the original retained
source-and-contact-evidence ZIP; checks its SHA-256 before importing it.
Outputs conservative sampled-pose separations and unresolved overlap work,
never a continuous collision or artistic/hardware qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import time

import numpy as np
from emerald_v5_anatomical_census import (
    PINNED, COHORTS, RISK_PAIRS, classify, require,
)

AUDITOR_SHA = "0333ec4e01f701554e6f62b443fc5b2283bb68e8a62aaf324760068cc7107d4f"
AUDITOR_BYTES = 23471
STAGES = ("pathfinder", "archivist")
SAMPLES = (
    ("ground-idle-1", 0.), ("ground-idle-1", .5),
    ("ground-idle-1", 1.), ("ground-cuddle-1", .5),
    ("takeoff-1", .5), ("orbit-01", .5), ("landing-1", .5),
)
MARGIN = .008
NUMERIC_SLACK = 1e-7
MAX_SECONDS = 7200


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def vetted_auditor(path: Path):
    require(path.is_file() and not path.is_symlink() and
            path.stat().st_size == AUDITOR_BYTES and sha(path) == AUDITOR_SHA,
            "trusted original contact auditor is missing or modified")
    spec = importlib.util.spec_from_file_location(
        "emerald_retained_contact_audit_v1", str(path))
    require(spec is not None and spec.loader is not None,
            "could not open qualified source auditor")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    require(getattr(mod, "SHA_DONOR", None) ==
            "c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a",
            "contact implementation donor changed")
    return mod


def region_vertex_sets(weights, joints, faces):
    labels, counts = classify(weights, joints, faces)
    subset = {}
    for i, (name, _start, _end) in enumerate(COHORTS):
        triangles = faces[labels == i]
        subset[name] = np.unique(triangles.reshape(-1)) if triangles.size else np.empty(0, dtype=np.int32)
    require(sum(counts.values()) == len(faces), "unqualified region partition")
    return subset, counts


def pair_lower_bound(bounds_a, bounds_b) -> float:
    """True lower bound between two AABBs; not the triangle distance."""
    a_min, a_max = bounds_a
    b_min, b_max = bounds_b
    require(np.all(np.isfinite(a_min)) and np.all(np.isfinite(a_max))
            and np.all(np.isfinite(b_min)) and np.all(np.isfinite(b_max))
            and np.all(a_min <= a_max) and np.all(b_min <= b_max),
            "invalid sampled bounds")
    gap = np.maximum(np.maximum(a_min - b_max, b_min - a_max), 0)
    return float(np.linalg.norm(gap))


def screen(bounds: dict, margin: float = MARGIN) -> list[dict]:
    require(math.isfinite(margin) and 0 < margin <= .02, "invalid clearance margin")
    rows = []
    for a, b in RISK_PAIRS:
        if bounds[a] is None or bounds[b] is None:
            rows.append({"pair": a+"__"+b,
                         "status": "empty-unqualified",
                         "gap_lower_bound_m": None})
            continue
        dist = pair_lower_bound(bounds[a], bounds[b])
        # A small extra numerical tolerance ensures near-margin cases stay
        # unresolved rather than receiving a false "separated" label.
        status = ("separated-at-pose"
                  if dist > margin + NUMERIC_SLACK
                  else "overlap-needs-triangle-test")
        rows.append({"pair": a+"__"+b, "status": status,
                     "gap_lower_bound_m": dist})
    return rows


def run(model: Path, stage: str, source_tool: Path, time_budget: float = 120.) -> dict:
    require(stage in STAGES and
            (stage, "v5") in PINNED, "unknown corrected stage")
    require(math.isfinite(time_budget) and 5 <= time_budget <= MAX_SECONDS,
            "unbounded or invalid scan budget")
    audit = vetted_auditor(source_tool)
    size, expected_sha = PINNED[stage, "v5"]
    start = time.monotonic()
    source = audit.GLB(model, size, expected_sha, stage)
    try:
        geometry = source.geometry()
        faces = geometry["faces"]
        vertices, counts = region_vertex_sets(
            geometry["weights"], geometry["joints"], faces)
        require(len(faces) == 719312 and
                counts["three_way_mixed"] == 84,
                "source topology or anatomical census changed")
        results = []
        for clip, fraction in SAMPLES:
            require(time.monotonic()-start <= time_budget,
                    "source scan budget exhausted; all intervals unqualified")
            positions = source.pose(geometry, clip, fraction)
            require(positions.shape == (len(geometry["weights"]), 3)
                    and np.isfinite(positions).all(),
                    "nonfinite skinned geometry")
            bounds = {name: (positions[ids].min(axis=0),
                              positions[ids].max(axis=0))
                      if len(ids) else None
                      for name, ids in vertices.items()}
            pairs = screen(bounds)
            results.append({
                "clip": clip, "fraction": fraction,
                "status": "sampled-pose-broadphase-only",
                "pairs": pairs,
            })
        totals = {
            status: sum(row["status"] == status
                        for frame in results for row in frame["pairs"])
            for status in ("separated-at-pose",
                           "overlap-needs-triangle-test",
                           "empty-unqualified")
        }
        require(sum(totals.values()) == len(SAMPLES)*len(RISK_PAIRS),
                "incomplete broadphase pair inventory")
        return {
            "schema": "skeleton.emerald.expanded-anatomy-bounds.v1",
            "stage": stage,
            "model_bytes": size,
            "model_sha256": expected_sha,
            "auditor_sha256": AUDITOR_SHA,
            "anatomical_cohorts": len(COHORTS),
            "pair_count": len(RISK_PAIRS),
            "poses_checked": len(SAMPLES),
            "margin_m": MARGIN,
            "triangle_count": 719312,
            "majority_assigned": 719228,
            "mixed_three_way": 84,
            "summary": totals,
            "poses": results,
            "tested_on_actual_skinned_model": True,
            "triangles_narrowphase_qualified": False,
            "unsampled_intervals_qualified": False,
            "blended_skin_seams_qualified": False,
            "continuous_collision_qualified": False,
            "equipment_enabled": False,
            "artist_approved": False,
            "physical_rtx_verified": False,
            "release_qualified": False,
        }
    finally:
        # GLB geometry arrays must be dropped before closing mmap. A Python
        # buffer may stay live in the source tool on exceptional unwind.
        try:
            del geometry, positions, vertices, faces
        except UnboundLocalError:
            pass
        try:
            source.close()
        except BufferError:
            pass


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", required=True, type=Path)
    p.add_argument("--stage", required=True, choices=STAGES)
    p.add_argument("--contact-tool", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--time-budget", type=float, default=120.)
    a = p.parse_args()
    require(a.out.parent.is_dir() and not a.out.parent.is_symlink()
            and not os.path.lexists(a.out),
            "trusted unused evidence output path required")
    result = run(a.model, a.stage, a.contact_tool, a.time_budget)
    with a.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: value for key, value in result.items()
                      if key != "poses"}, indent=2))


if __name__ == "__main__":
    main()
