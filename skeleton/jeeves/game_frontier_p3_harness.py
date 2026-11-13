"""P3 production qualification harness.

Aggregates P0/P1/P2 receipts into a single qualification record.
Does not certify external model success or GPU throughput.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


class P3QualificationError(ValueError):
    pass


@dataclass(frozen=True)
class P3Qualification:
    p0_admission_id: str
    p1_receipt: str
    p2_receipt_id: str
    qualification_id: str
    claim: str = "candidate-only"


def qualify(
    *,
    p0_admission_id: str,
    p1_receipt: str,
    p2_receipt_id: str,
) -> P3Qualification:
    """Bind the three milestone receipts. Fails closed on missing ids."""
    for label, value in (
        ("p0", p0_admission_id),
        ("p1", p1_receipt),
        ("p2", p2_receipt_id),
    ):
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise P3QualificationError(f"{label} receipt must be lowercase SHA-256")
    payload = json.dumps(
        {"p0": p0_admission_id, "p1": p1_receipt, "p2": p2_receipt_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return P3Qualification(
        p0_admission_id=p0_admission_id,
        p1_receipt=p1_receipt,
        p2_receipt_id=p2_receipt_id,
        qualification_id=sha256(payload.encode()).hexdigest(),
    )
