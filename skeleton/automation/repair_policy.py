"""Deterministic policy and fingerprinting for automated repair intake."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable


# These surfaces are never eligible for autonomous merging.
TRUST_SURFACES = frozenset(
    {
        ".github/workflows/",
        ".github/actions/",
        "security",
        "auth",
        "sandbox",
        "capabil",
        "secret",
        "permission",
        "provenance",
        "attestation",
        "merge",
        "dockerfile",
        "dependabot",
    }
)

HIGH_RISK_PATH_RE = re.compile(
    r"(^|/)(\.github/(workflows|actions)/|security|auth|sandbox|secrets?|Dockerfile(?:\.|$)|"
    r"dependabot(?:\.yml)?|provenance|attestation|sbom|merge[-_]?gate)|"
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
    if any(path.startswith((".github/workflows/", ".github/actions/")) for path in normalized):
        reasons.append("workflow control plane")
    if any(
        marker in path.lower()
        for path in normalized
        for marker in ("auth", "sandbox", "secret", "permission", "provenance", "attestation")
    ):
        reasons.append("security or capability boundary")

    # Autonomous merging is intentionally an explicit allowlist, not a broad
    # denylist: only small documentation-only changes qualify today.
    documentation_only = (
        bool(normalized)
        and len(normalized) <= 3
        and all(path.endswith((".md", ".mdx", ".rst")) for path in normalized)
    )
    if reasons:
        risk = "high"
        allowed = False
    elif documentation_only:
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
