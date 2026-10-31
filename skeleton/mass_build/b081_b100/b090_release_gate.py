"""B090: release promotion requires current dependency, code, secret, provenance, policy evidence."""
from __future__ import annotations

from typing import Mapping

from ._core import Verdict, digest, verdict

REQUIRED = ("B081", "B083", "B084", "B089")
MAX_AGE_TICKS = 24


def evaluate(evidence: Mapping[str, tuple[Verdict, int]], now: int, policy_ok: bool):
    """``evidence`` maps batch id -> (verdict, tick produced)."""
    findings = []
    for b in REQUIRED:
        if b not in evidence:
            findings.append(f"missing:{b}")
            continue
        v, at = evidence[b]
        if v.batch != b:
            findings.append(f"mislabeled:{b}")
        if not v.passed:
            findings.append(f"failed:{b}")
        if now - at > MAX_AGE_TICKS or at > now:
            findings.append(f"stale:{b}")
    if not policy_ok:
        findings.append("policy")
    bundle = {b: evidence[b][0].digest for b in sorted(evidence)}
    return verdict("B090", findings, bundle=digest(bundle))
