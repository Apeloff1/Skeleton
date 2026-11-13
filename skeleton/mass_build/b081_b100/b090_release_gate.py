"""B090: advisory evidence audit, never a self-attested release authorization.

Caller-supplied verdicts, timestamps and policy booleans are not authenticated
provider evidence. Even a complete, passing local diagnostic MUST fail closed
as a release gate until a separate provider-authoritative integration exists.
"""
from __future__ import annotations

from typing import Mapping

from ._core import Verdict, digest, require, verdict

REQUIRED = ("B081", "B083", "B084", "B089")
MAX_AGE_TICKS = 24
MAX_EVIDENCE = 64
UNVERIFIED_AUTHORITY = "provider-authority-unverified"


def evaluate(evidence: Mapping[str, tuple[Verdict, int]], now: int, policy_ok: bool) -> Verdict:
    """Audit local evidence; a positive result cannot authorize release.

    This function does NOT query GitHub, validate signatures, bind a commit
    SHA, or check an authenticated repository policy. No local caller can
    supply a bool or a synthetic Verdict to override that absence.
    """
    require(
        isinstance(evidence, Mapping) and len(evidence) <= MAX_EVIDENCE,
        "bounded evidence mapping required",
    )
    require(type(now) is int and now >= 0, "now must be a nonnegative integer tick")
    require(type(policy_ok) is bool, "policy_ok must be a boolean")
    findings = [UNVERIFIED_AUTHORITY]
    bundle = {}
    for key, pair in evidence.items():
        require(isinstance(key, str) and key.strip(), "evidence keys must be nonempty text")
        require(isinstance(pair, tuple) and len(pair) == 2, "evidence must contain verdict/tick pairs")
        v, at = pair
        require(isinstance(v, Verdict), "evidence verdict must be typed")
        require(type(at) is int and at >= 0, "evidence tick must be a nonnegative integer")
        require(isinstance(v.batch, str), "verdict batch must be text")
        require(type(v.passed) is bool, "verdict pass state must be boolean")
        bundle[key] = v.digest
    for batch in REQUIRED:
        if batch not in evidence:
            findings.append(f"missing:{batch}")
            continue
        v, at = evidence[batch]
        if v.batch != batch:
            findings.append(f"mislabeled:{batch}")
        if not v.passed or v.findings:
            findings.append(f"failed:{batch}")
        if now - at > MAX_AGE_TICKS or at > now:
            findings.append(f"stale:{batch}")
    if not policy_ok:
        findings.append("policy")
    return verdict(
        "B090", findings, bundle=digest({key: bundle[key] for key in sorted(bundle)}),
        release_authorized=False, authority="unverified-local-diagnostic",
    )
