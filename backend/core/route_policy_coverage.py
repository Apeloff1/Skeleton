"""Coverage accounting for fail-closed HTTP route policy rollout.

The security rule is simple: enforcement cannot safely become global until every
intended application path has an explicit disposition. This module turns that
rule into a deterministic report that can be used by tests, startup checks, or
CI without importing FastAPI or booting the application.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from core.principal_seal import RouteDomainPolicy


class RoutePolicyCoverageError(RuntimeError):
    """Raised when an enforcement candidate still contains unwritten routes."""


@dataclass(frozen=True, slots=True)
class RoutePolicyCoverage:
    """Immutable route-policy readiness snapshot."""

    total_routes: int
    open_routes: int
    protected_routes: int
    unwritten_routes: int
    domain_counts: tuple[tuple[str, int], ...]
    open_paths: tuple[str, ...]
    protected_paths: tuple[tuple[str, str], ...]
    unwritten_paths: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return self.unwritten_routes == 0

    @property
    def written_routes(self) -> int:
        return self.open_routes + self.protected_routes

    @property
    def coverage_ratio(self) -> float:
        if self.total_routes == 0:
            return 1.0
        return self.written_routes / self.total_routes

    def as_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-friendly representation."""

        return {
            "total_routes": self.total_routes,
            "open_routes": self.open_routes,
            "protected_routes": self.protected_routes,
            "unwritten_routes": self.unwritten_routes,
            "coverage_ratio": self.coverage_ratio,
            "complete": self.complete,
            "domain_counts": dict(self.domain_counts),
            "open_paths": list(self.open_paths),
            "protected_paths": [
                {"path": path, "domain": domain} for path, domain in self.protected_paths
            ],
            "unwritten_paths": list(self.unwritten_paths),
        }


def _normalize_inventory(paths: Iterable[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for path in paths:
        if not isinstance(path, str):
            raise TypeError("route inventory entries must be text paths")
        candidate = path.strip()
        if not candidate:
            raise ValueError("route inventory cannot contain blank paths")
        if not candidate.startswith("/") or "?" in candidate or "#" in candidate:
            raise ValueError(f"invalid route inventory path: {candidate!r}")
        normalized.add(candidate.rstrip("/") or "/")
    return tuple(sorted(normalized))


def build_route_policy_coverage(
    policy: RouteDomainPolicy,
    paths: Iterable[str],
    *,
    excluded_paths: Iterable[str] = (),
) -> RoutePolicyCoverage:
    """Classify unique application paths against an explicit route policy.

    ``excluded_paths`` is intentionally exact-match only. Documentation or
    framework endpoints may be excluded by deployment policy, but broad prefix
    exclusions would make it too easy to hide a sensitive application route.
    """

    inventory = _normalize_inventory(paths)
    excluded = set(_normalize_inventory(excluded_paths))
    open_paths: list[str] = []
    protected_paths: list[tuple[str, str]] = []
    unwritten_paths: list[str] = []
    domain_counts: Counter[str] = Counter()

    for path in inventory:
        if path in excluded:
            continue
        if policy.is_open(path):
            open_paths.append(path)
            continue
        domain = policy.required_domain(path)
        if domain is None:
            unwritten_paths.append(path)
            continue
        protected_paths.append((path, domain))
        domain_counts[domain] += 1

    total = len(open_paths) + len(protected_paths) + len(unwritten_paths)
    return RoutePolicyCoverage(
        total_routes=total,
        open_routes=len(open_paths),
        protected_routes=len(protected_paths),
        unwritten_routes=len(unwritten_paths),
        domain_counts=tuple(sorted(domain_counts.items())),
        open_paths=tuple(open_paths),
        protected_paths=tuple(protected_paths),
        unwritten_paths=tuple(unwritten_paths),
    )


def require_complete_route_policy(report: RoutePolicyCoverage) -> None:
    """Fail closed when a route inventory is not fully classified."""

    if report.complete:
        return
    sample = ", ".join(report.unwritten_paths[:8])
    suffix = "" if report.unwritten_routes <= 8 else ", ..."
    raise RoutePolicyCoverageError(
        f"route policy incomplete: {report.unwritten_routes}/{report.total_routes} "
        f"unwritten route(s): {sample}{suffix}"
    )
