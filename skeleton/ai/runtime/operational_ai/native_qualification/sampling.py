"""Deterministic subset selection for development; never count as full corpus."""
from __future__ import annotations
from typing import Iterable
import hashlib
from .canonical import integer
from .cases import QualificationCase
from .errors import deny


def choose_subset(
    cases: Iterable[QualificationCase], *,
    max_cases: int, seed: int,
) -> tuple[QualificationCase, ...]:
    integer(max_cases, "sample-count", 1, 480)
    integer(seed, "sample-seed", 0, 2**31 - 1)
    rows = list(cases)
    if not rows or len(rows) > 480:
        deny("sample-corpus")
    if len({r.case_id for r in rows}) != len(rows):
        deny("sample-duplicate")
    key = str(seed).encode("ascii")
    rows.sort(key=lambda r: (hashlib.sha256(key + b"\x00" + r.case_id.encode()).digest(), r.case_id))
    return tuple(rows[:max_cases])
