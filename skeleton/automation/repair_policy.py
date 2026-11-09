"""Deterministic, fail-closed policy for automated repair proposals."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import PurePosixPath
import re
from typing import Iterable

_HIGH_RISK_PATH_RE = re.compile(
    r"(^|/)(\.github/(?:workflows|actions)/|security(?:/|[-_.])|auth(?:/|[-_.])|"
    r"sandbox(?:/|[-_.])|secrets?(?:/|[-_.])|Dockerfile(?:\.|$)|dependabot(?:\.yml)?$|"
    r"provenance(?:/|[-_.])|attestation(?:/|[-_.])|sbom(?:/|[-_.])|merge[-_]?gate)|"
    r"(^|/)(pyproject\.toml|package-lock\.json|poetry\.lock|requirements[^/]*\.txt)$",
    re.IGNORECASE,
)
_SECURITY_MARKERS = (
    "auth",
    "sandbox",
    "secret",
    "permission",
    "provenance",
    "attestation",
)


@dataclass(frozen=True, slots=True)
class RepairDecision:
    fingerprint: str
    risk: str
    automated_merge_allowed: bool
    human_review_required: bool
    reasons: tuple[str, ...]

    @property
    def quarantined(self) -> bool:
        """High-risk proposals are isolated from automated mutation/merge."""
        return self.risk == "high"

    @property
    def disposition(self) -> str:
        if self.quarantined:
            return "quarantine"
        if self.human_review_required:
            return "human_review"
        return "auto_merge"


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_repo_path(value: object) -> tuple[str, bool]:
    """Return canonical path plus whether the input was invalid/non-canonical."""

    if not isinstance(value, str):
        return f"!invalid-type:{type(value).__name__}", True
    raw = value.replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    if not raw or "\x00" in raw:
        return f"!invalid:{raw}", True

    pure = PurePosixPath(raw)
    canonical = pure.as_posix()
    invalid = (
        pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or canonical != raw
    )
    return (f"!invalid:{raw}" if invalid else canonical), invalid


def failure_fingerprint(
    workflow: str,
    conclusion: str,
    head_sha: str,
    finding_ids: Iterable[str] = (),
) -> str:
    """Return stable failure identity independent of finding order/duplicates."""

    values = [
        _required_text(workflow, "workflow").lower(),
        _required_text(conclusion, "conclusion").lower(),
        _required_text(head_sha, "head_sha").lower(),
    ]
    findings = {
        str(value).strip().lower()
        for value in finding_ids
        if str(value).strip()
    }
    values.extend(sorted(findings))
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()


def classify_change(
    paths: Iterable[str],
    *,
    security_finding: bool = False,
) -> RepairDecision:
    """Classify a proposed change; only tiny ordinary docs changes may auto-merge."""

    normalized_items = [_normalize_repo_path(path) for path in paths]
    normalized = tuple(sorted({path for path, _invalid in normalized_items}))
    invalid_path = any(invalid for _path, invalid in normalized_items)
    reasons: list[str] = []

    if invalid_path:
        reasons.append("invalid or non-canonical repository path")
    if security_finding:
        reasons.append("security finding")
    if any(
        not path.startswith("!invalid:") and _HIGH_RISK_PATH_RE.search(path)
        for path in normalized
    ):
        reasons.append("trust/security-sensitive path")
    if any(
        path.startswith((".github/workflows/", ".github/actions/"))
        for path in normalized
    ):
        reasons.append("workflow control plane")
    if any(
        marker in path.lower()
        for path in normalized
        if not path.startswith("!invalid:")
        for marker in _SECURITY_MARKERS
    ):
        reasons.append("security or capability boundary")

    documentation_only = (
        bool(normalized)
        and not invalid_path
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

    fingerprint_material = ["security" if security_finding else "ordinary", *normalized]
    fingerprint = hashlib.sha256(
        "\x1f".join(fingerprint_material).encode("utf-8")
    ).hexdigest()

    return RepairDecision(
        fingerprint=fingerprint,
        risk=risk,
        automated_merge_allowed=allowed,
        human_review_required=not allowed,
        reasons=tuple(dict.fromkeys(reasons)),
    )
