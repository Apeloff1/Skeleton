"""Reference-oracle validation against existing optimized AI runtime math."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from .linear import dot, matmul
from .numerics import stable_softmax


@dataclass(frozen=True, slots=True)
class MathAuditCase:
    name: str
    passed: bool
    max_absolute_error: float
    detail: str


@dataclass(frozen=True, slots=True)
class MathAuditReport:
    passed: bool
    cases: tuple[MathAuditCase, ...]
    fingerprint: str


def _max_error(left: list[float] | tuple[float, ...], right: list[float] | tuple[float, ...]) -> float:
    if len(left) != len(right):
        return math.inf
    return max((abs(a - b) for a, b in zip(left, right)), default=0.0)


def _case(name: str, reference, candidate, *, tolerance: float = 1e-12) -> MathAuditCase:
    ref = tuple(float(value) for value in reference)
    got = tuple(float(value) for value in candidate)
    error = _max_error(ref, got)
    return MathAuditCase(
        name=name,
        passed=math.isfinite(error) and error <= tolerance,
        max_absolute_error=error,
        detail=f"tolerance={tolerance:.3e}",
    )


def audit_runtime_kernels(*, tolerance: float = 1e-12) -> MathAuditReport:
    """Cross-check current runtime kernels without granting this module runtime authority."""

    from skeleton.ai.runtime.kernel.ops.attention import attend
    from skeleton.ai.runtime.kernel.ops.matmul import matmul as runtime_matmul
    from skeleton.ai.runtime.kernel.ops.softmax import softmax as runtime_softmax

    cases: list[MathAuditCase] = []

    logits = [1000.0, 999.0, 997.5, -1000.0]
    cases.append(
        _case(
            "softmax.extreme_shift",
            stable_softmax(logits),
            runtime_softmax(logits),
            tolerance=tolerance,
        )
    )

    left = [[1.0, 2.0, -3.0], [1e-10, 4.0, 5.0]]
    right = [[2.0, 0.0], [-1.0, 3.0], [0.5, 4.0]]
    reference_matrix = matmul(left, right)
    candidate_matrix = runtime_matmul(left, right, tile=2)
    flattened_reference = tuple(value for row in reference_matrix for value in row)
    flattened_candidate = tuple(value for row in candidate_matrix for value in row)
    cases.append(
        _case(
            "matmul.reference_parity",
            flattened_reference,
            flattened_candidate,
            tolerance=tolerance,
        )
    )

    query = [1.0, -0.5, 0.25]
    kv = [
        ([1.0, 0.0, 0.5], [0.5, 1.0]),
        ([0.0, 1.0, -0.5], [1.5, -1.0]),
        ([0.25, -0.75, 1.0], [2.0, 0.25]),
    ]
    scale = 1.0 / math.sqrt(len(query))
    scores = [scale * dot(query, key) for key, _ in kv]
    weights = stable_softmax(scores)
    expected_attention = tuple(
        sum(weight * value[index] for weight, (_, value) in zip(weights, kv))
        for index in range(len(kv[0][1]))
    )
    cases.append(
        _case(
            "attention.row_reference_parity",
            expected_attention,
            attend(query, kv),
            tolerance=tolerance,
        )
    )

    payload = [
        {
            "name": item.name,
            "passed": item.passed,
            "max_absolute_error": format(item.max_absolute_error, ".17g"),
            "detail": item.detail,
        }
        for item in cases
    ]
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return MathAuditReport(
        passed=all(item.passed for item in cases),
        cases=tuple(cases),
        fingerprint=fingerprint,
    )
