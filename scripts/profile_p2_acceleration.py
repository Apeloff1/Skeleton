#!/usr/bin/env python3
"""Generate reproducible P2 accelerator profile receipts for known candidates."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Callable

from skeleton.native.profiling import ProfileCase, profile_pair
from skeleton.native.asm_accelerator import AsmVectorAccelerator
from skeleton.memory.jvm_vector_accelerator import JvmVectorAccelerator
from skeleton.observability.jvm_accelerator import JvmObservabilityAccelerator
from skeleton.simulation.physics.jvm_broadphase_accelerator import JvmBroadPhaseAccelerator
from skeleton.simulation.physics.math3d import AABB, Vec3


ROOT = Path(__file__).resolve().parents[1]


class BenchmarkScenarioError(RuntimeError):
    pass


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _source_identity(*relative_paths: str) -> str:
    records: list[str] = []
    for relative in relative_paths:
        path = ROOT / relative
        if not path.is_file():
            raise BenchmarkScenarioError(f"source identity path missing: {relative}")
        records.append(f"{relative}:{_git_blob_sha(path)}")
    payload = "\n".join(sorted(records)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _vector_fixture(
    *,
    dimensions: int = 64,
    candidates: int = 256,
) -> tuple[list[float], float, list[tuple[list[float], float]]]:
    if dimensions < 1 or candidates < 1:
        raise ValueError("vector fixture dimensions/candidates must be positive")
    query = [((index % 8) - 3.5) * 0.25 for index in range(dimensions)]
    query_norm = math.sqrt(sum(value * value for value in query))
    rows: list[tuple[list[float], float]] = []
    for row in range(candidates):
        vector = [
            ((((row + 3) * (column + 5)) % 17) - 8) * 0.125
            for column in range(dimensions)
        ]
        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            vector[0] = 0.125
            norm = math.sqrt(sum(value * value for value in vector))
        rows.append((vector, norm))
    return query, query_norm, rows


def _reference_vector_top_k(
    query: list[float],
    query_norm: float,
    candidates: list[tuple[list[float], float]],
    top_k: int,
) -> list[dict[str, float | int]]:
    hits: list[tuple[int, float]] = []
    for index, (vector, norm) in enumerate(candidates):
        dot = sum(left * right for left, right in zip(query, vector))
        similarity = dot / (query_norm * norm)
        if similarity > 1.0 and similarity < 1.0 + 1e-12:
            similarity = 1.0
        if similarity < -1.0 and similarity > -1.0 - 1e-12:
            similarity = -1.0
        hits.append((index, similarity))
    hits.sort(key=lambda item: (-item[1], item[0]))
    return [
        {"index": index, "similarity": similarity}
        for index, similarity in hits[:top_k]
    ]


def _physics_fixture(count: int = 256) -> list[tuple[AABB, bool]]:
    if count < 2:
        raise ValueError("physics fixture requires at least two bodies")
    bodies: list[tuple[AABB, bool]] = []
    for index in range(count):
        x = float(index % 32) * 0.75
        y = float((index // 32) % 8) * 0.75
        z = float(index // 256) * 0.75
        center = Vec3(x, y, z)
        half = Vec3(0.5, 0.5, 0.5)
        bodies.append((AABB.from_center_half_extents(center, half), index % 3 != 0))
    return bodies


def _reference_broadphase(
    bodies: list[tuple[AABB, bool]],
    *,
    max_pairs: int,
) -> list[list[int]]:
    pairs: list[list[int]] = []
    for left in range(len(bodies)):
        left_bounds, left_dynamic = bodies[left]
        for right in range(left + 1, len(bodies)):
            right_bounds, right_dynamic = bodies[right]
            if not left_dynamic and not right_dynamic:
                continue
            if not left_bounds.overlaps(right_bounds):
                continue
            if len(pairs) >= max_pairs:
                raise BenchmarkScenarioError("reference broad-phase pair bound exceeded")
            pairs.append([left, right])
    return pairs


def _observability_fixture(count: int = 8192) -> list[float]:
    if count < 2:
        raise ValueError("observability fixture count must be >= 2")
    return [
        float(((index * 37) % 257) - 128) * 0.125
        for index in range(count)
    ]


def _reference_summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        raise ValueError("summary requires values")
    n = 0
    mean = 0.0
    m2 = 0.0
    total = 0.0
    correction = 0.0
    for value in values:
        if not math.isfinite(value):
            raise ValueError("non-finite input")
        n += 1
        delta = value - mean
        mean += delta / n
        delta2 = value - mean
        m2 += delta * delta2

        candidate = total + value
        if abs(total) >= abs(value):
            correction += (total - candidate) + value
        else:
            correction += (value - candidate) + total
        total = candidate

    variance = m2 / (n - 1) if n > 1 else 0.0
    if variance < 0.0 and variance > -1e-15:
        variance = 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    p50 = (
        (ordered[mid - 1] + ordered[mid]) / 2.0
        if len(ordered) % 2 == 0
        else ordered[mid]
    )

    def percentile(q: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        index = math.floor(len(ordered) * q)
        if index >= len(ordered):
            index = len(ordered) - 1
        return ordered[index]

    return {
        "count": len(ordered),
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "mean": mean,
        "sample_variance": variance,
        "sample_stdev": math.sqrt(variance),
        "p50": p50,
        "p90": percentile(0.90),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
        "total": total + correction,
    }


def _native_vector(repeat: int, evidence_id: str) -> dict[str, Any]:
    left = [((index % 8) - 3.5) * 0.25 for index in range(512)]
    right = [(((index * 5) % 16) - 7.5) * 0.125 for index in range(512)]
    accelerator = AsmVectorAccelerator(build_if_missing=True)
    try:
        run = profile_pair(
            evidence_id=evidence_id,
            candidate_id="ACCEL-NATIVE-VECTOR",
            source_identity=_source_identity(
                "skeleton/native/asm_accelerator.py",
                "skeleton/native/asm/x86_64.S",
                "skeleton/native/asm/aarch64.S",
            ),
            reference=lambda: sum(a * b for a, b in zip(left, right)),
            candidate=lambda: accelerator.dot_f32(left, right),
            cases=[ProfileCase()],
            repeat_count=repeat,
        )
    finally:
        close = getattr(accelerator, "close", None)
        if callable(close):
            close()
    return asdict(run.evidence)


def _jvm_vector(repeat: int, evidence_id: str) -> dict[str, Any]:
    query, query_norm, rows = _vector_fixture()
    top_k = 16
    accelerator = JvmVectorAccelerator()
    try:
        run = profile_pair(
            evidence_id=evidence_id,
            candidate_id="ACCEL-JVM-VECTOR",
            source_identity=_source_identity(
                "skeleton/memory/jvm_vector_accelerator.py",
                "java-accelerators/vector/VectorSearchMain.java",
            ),
            reference=lambda: _reference_vector_top_k(query, query_norm, rows, top_k),
            candidate=lambda: [
                {"index": item.index, "similarity": item.similarity}
                for item in accelerator.top_k(query, query_norm, rows, top_k)
            ],
            cases=[ProfileCase()],
            repeat_count=repeat,
        )
    finally:
        accelerator.close()
    return asdict(run.evidence)


def _jvm_physics(repeat: int, evidence_id: str) -> dict[str, Any]:
    bodies = _physics_fixture()
    max_pairs = 100_000
    accelerator = JvmBroadPhaseAccelerator()
    try:
        run = profile_pair(
            evidence_id=evidence_id,
            candidate_id="ACCEL-JVM-PHYSICS",
            source_identity=_source_identity(
                "skeleton/simulation/physics/jvm_broadphase_accelerator.py",
                "java-accelerators/physics/BroadPhaseMain.java",
            ),
            reference=lambda: _reference_broadphase(bodies, max_pairs=max_pairs),
            candidate=lambda: [
                [item.left, item.right]
                for item in accelerator.compute_pairs(
                    bodies,
                    max_pairs=max_pairs,
                    epsilon=0.0,
                )
            ],
            cases=[ProfileCase()],
            repeat_count=repeat,
        )
    finally:
        accelerator.close()
    return asdict(run.evidence)


def _jvm_observability(repeat: int, evidence_id: str) -> dict[str, Any]:
    values = _observability_fixture()
    accelerator = JvmObservabilityAccelerator()
    try:
        run = profile_pair(
            evidence_id=evidence_id,
            candidate_id="ACCEL-JVM-OBSERVABILITY",
            source_identity=_source_identity(
                "skeleton/observability/jvm_accelerator.py",
                "java-accelerators/observability/AcceleratorMain.java",
            ),
            reference=lambda: _reference_summary(values),
            candidate=lambda: asdict(accelerator.summarize(values)),
            cases=[ProfileCase()],
            repeat_count=repeat,
        )
    finally:
        accelerator.close()
    return asdict(run.evidence)


SCENARIOS: dict[str, Callable[[int, str], dict[str, Any]]] = {
    "ACCEL-NATIVE-VECTOR": _native_vector,
    "ACCEL-JVM-VECTOR": _jvm_vector,
    "ACCEL-JVM-PHYSICS": _jvm_physics,
    "ACCEL-JVM-OBSERVABILITY": _jvm_observability,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--evidence-id")
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.repeat < 1:
        parser.error("--repeat must be positive")
    evidence_id = args.evidence_id or f"{args.candidate.lower()}-profile"
    try:
        receipt = SCENARIOS[args.candidate](args.repeat, evidence_id)
    except Exception as exc:
        print(
            f"P2 acceleration profile failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
