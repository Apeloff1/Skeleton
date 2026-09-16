"""Deterministic policy and fingerprinting for automated repair intake.

This module is intentionally independent of any LLM. Repository and GitHub text
is data, never policy. The policy classifies the *change surface* before a repair
engine is allowed to propose or merge anything.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable


TRUST_SURFACES = frozenset(
    {
        ".github/workflows/",
        "security",
        "auth",
        "sandbox",
        "capabil",
        "secret",
        "permission",
        "provenance",
        "merge",
        "dockerfile",
    }
)

HIGH_RISK_PATH_RE = re.compile(
    r"(^|/)(\.github/workflows/|security|auth|sandbox|secrets?|Dockerfile(?:\.|$))|"
    r"(^|/)(pyproject\.toml|package-lock\.json|poetry\.lock|requirements[^/]*\.txt)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RepairDecision:
    fingerprint: str
    risk: str
    automated_merge_allowed: bool
    human_review_required: bool
    reasons: tuple[str, ...]


def failure_fingerprint(
    workflow: str,
    conclusion: str,
    head_sha: str,
    finding_ids: Iterable[str] = (),
) -> str:
    """Return a stable identity for one observed failure/root-cause candidate."""
    values = [workflow.strip().lower(), conclusion.strip().lower(), head_sha.strip()]
    values.extend(sorted(str(value).strip().lower() for value in finding_ids if str(value).strip()))
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()


def classify_change(paths: Iterable[str], *, security_finding: bool = False) -> RepairDecision:
    normalized = tuple(sorted({p.replace("\\", "/").lstrip("./") for p in paths if p}))
    reasons: list[str] = []

    if security_finding:
        reasons.append("security finding")
    if any(HIGH_RISK_PATH_RE.search(path) for path in normalized):
        reasons.append("trust/security-sensitive path")
    if any(path.startswith(".github/workflows/") for path in normalized):
        reasons.append("workflow control plane")
    if any("auth" in path.lower() or "sandbox" in path.lower() for path in normalized):
        reasons.append("authorization or capability boundary")

    if reasons:
        risk = "high"
        allowed = False
    elif any(path.endswith((".md", ".mdx", ".rst")) for path in normalized) and len(normalized) <= 3:
        risk = "low"
        allowed = True
    else:
        risk = "medium"
        allowed = False
        reasons.append("non-trivial code/config change")

    return RepairDecision(
        fingerprint=hashlib.sha256("\x1f".join(normalized).encode("utf-8")).hexdigest(),
        risk=risk,
        automated_merge_allowed=allowed,
        human_review_required=not allowed,
        reasons=tuple(dict.fromkeys(reasons)),
    )
