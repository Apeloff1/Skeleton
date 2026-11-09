"""Trust-surface classification for changed-file inventories.

Classification is fail-closed: unknown paths become TrustSurface.UNKNOWN and
privileged prefixes escalate risk for admission decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, Sequence

from .types import Finding, PathObservation, TrustSurface, valid_posix_path


DEPENDENCY_FILENAMES = frozenset(
    {
        "pyproject.toml",
        "poetry.lock",
        "pdm.lock",
        "uv.lock",
        "package.json",
        "package-lock.json",
        "npm-shrinkwrap.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "go.mod",
        "go.sum",
        "Cargo.toml",
        "Cargo.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "gradle.lockfile",
        "requirements.txt",
        "requirements.in",
        "Pipfile",
        "Pipfile.lock",
    }
)

CODE_PREFIXES = (
    "backend/",
    "frontend/",
    "skeleton/",
    "scripts/",
    "tests/",
    "gameforge/",
    "crates/",
)

DOC_PREFIXES = (
    "docs/",
    "README",
    "CHANGELOG",
    "LICENSE",
    "CONTRIBUTING",
)

SECURITY_PREFIXES = (
    ".github/workflows/",
    ".github/actions/",
    ".github/dependabot",
    ".gitleaks",
    ".semgrep",
    "security/",
    "skeleton/security/",
    "skeleton/pr_automation/",
    "scripts/check_",
    "scripts/audit_",
)

RELEASE_PREFIXES = (
    "Dockerfile",
    "docker/",
    "deploy/",
    "helm/",
    "k8s/",
    "release/",
    ".github/workflows/reproducible-release",
    ".github/workflows/container-",
)

WORKFLOW_PREFIXES = (
    ".github/workflows/",
    ".github/actions/",
)

TEST_PREFIXES = (
    "tests/",
    "skeleton/testing/",
    "backend/tests/",
)


@dataclass(frozen=True, slots=True)
class PathTrust:
    path: str
    surfaces: tuple[TrustSurface, ...]
    privileged: bool
    risk_weight: int

    @property
    def primary(self) -> TrustSurface:
        if not self.surfaces:
            return TrustSurface.UNKNOWN
        priority = (
            TrustSurface.SECURITY,
            TrustSurface.WORKFLOW,
            TrustSurface.RELEASE,
            TrustSurface.DEPENDENCY,
            TrustSurface.CODE,
            TrustSurface.DOCS,
            TrustSurface.UNKNOWN,
        )
        for candidate in priority:
            if candidate in self.surfaces:
                return candidate
        return self.surfaces[0]


@dataclass(frozen=True, slots=True)
class InventoryTrust:
    paths: tuple[PathTrust, ...]
    surfaces: tuple[TrustSurface, ...]
    privileged_paths: tuple[str, ...]
    total_additions: int
    total_deletions: int
    findings: tuple[Finding, ...]

    @property
    def has_privileged(self) -> bool:
        return bool(self.privileged_paths)

    @property
    def line_delta(self) -> int:
        return self.total_additions + self.total_deletions

    def contains(self, surface: TrustSurface) -> bool:
        return surface in self.surfaces


def _starts(path: str, prefixes: Sequence[str]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def classify_path(
    path: str,
    *,
    privileged_prefixes: Sequence[str] = SECURITY_PREFIXES,
) -> PathTrust:
    if not valid_posix_path(path):
        return PathTrust(
            path=path,
            surfaces=(TrustSurface.UNKNOWN,),
            privileged=True,
            risk_weight=100,
        )
    surfaces: list[TrustSurface] = []
    name = PurePosixPath(path).name
    if name in DEPENDENCY_FILENAMES or path.endswith("/requirements.txt"):
        surfaces.append(TrustSurface.DEPENDENCY)
    if _starts(path, WORKFLOW_PREFIXES) or path.startswith(".github/workflows/"):
        surfaces.append(TrustSurface.WORKFLOW)
    if _starts(path, SECURITY_PREFIXES):
        surfaces.append(TrustSurface.SECURITY)
    if _starts(path, RELEASE_PREFIXES):
        surfaces.append(TrustSurface.RELEASE)
    if _starts(path, CODE_PREFIXES) and TrustSurface.SECURITY not in surfaces:
        surfaces.append(TrustSurface.CODE)
    if _starts(path, DOC_PREFIXES) or path.endswith((".md", ".rst", ".txt")):
        if not surfaces:
            surfaces.append(TrustSurface.DOCS)
    if not surfaces:
        surfaces.append(TrustSurface.UNKNOWN)

    privileged = _starts(path, privileged_prefixes) or TrustSurface.SECURITY in surfaces or TrustSurface.WORKFLOW in surfaces
    weight = 1
    if TrustSurface.DOCS in surfaces and len(surfaces) == 1:
        weight = 1
    if TrustSurface.CODE in surfaces:
        weight = 3
    if TrustSurface.DEPENDENCY in surfaces:
        weight = 5
    if TrustSurface.RELEASE in surfaces:
        weight = 7
    if TrustSurface.WORKFLOW in surfaces:
        weight = 8
    if TrustSurface.SECURITY in surfaces or privileged:
        weight = 10
    if TrustSurface.UNKNOWN in surfaces:
        weight = max(weight, 6)
    return PathTrust(
        path=path,
        surfaces=tuple(dict.fromkeys(surfaces)),
        privileged=privileged,
        risk_weight=weight,
    )


def classify_inventory(
    observations: Iterable[PathObservation],
    *,
    privileged_prefixes: Sequence[str] = SECURITY_PREFIXES,
    max_files: int | None = None,
) -> InventoryTrust:
    trusts: list[PathTrust] = []
    findings: list[Finding] = []
    additions = 0
    deletions = 0
    privileged_paths: list[str] = []
    surface_set: set[TrustSurface] = set()
    count = 0
    for obs in observations:
        count += 1
        if max_files is not None and count > max_files:
            findings.append(
                Finding(
                    code="trust.inventory_overflow",
                    severity="high",
                    message=f"changed-file inventory exceeded max_files={max_files}",
                )
            )
            break
        trust = classify_path(obs.path, privileged_prefixes=privileged_prefixes)
        trusts.append(trust)
        surface_set.update(trust.surfaces)
        additions += obs.additions
        deletions += obs.deletions
        if trust.privileged:
            privileged_paths.append(obs.path)
        if TrustSurface.UNKNOWN in trust.surfaces:
            findings.append(
                Finding(
                    code="trust.unknown_path",
                    severity="medium",
                    message=f"path {obs.path!r} classified unknown",
                    subject=obs.path,
                )
            )
    return InventoryTrust(
        paths=tuple(trusts),
        surfaces=tuple(sorted(surface_set, key=lambda s: s.value)),
        privileged_paths=tuple(privileged_paths),
        total_additions=additions,
        total_deletions=deletions,
        findings=tuple(findings),
    )


def risk_score(inventory: InventoryTrust) -> int:
    base = sum(p.risk_weight for p in inventory.paths)
    if inventory.has_privileged:
        base += 25
    if inventory.line_delta > 5_000:
        base += 10
    if inventory.line_delta > 15_000:
        base += 20
    return base


__all__ = [
    "CODE_PREFIXES",
    "DEPENDENCY_FILENAMES",
    "DOC_PREFIXES",
    "InventoryTrust",
    "PathTrust",
    "RELEASE_PREFIXES",
    "SECURITY_PREFIXES",
    "TEST_PREFIXES",
    "WORKFLOW_PREFIXES",
    "classify_inventory",
    "classify_path",
    "risk_score",
]
