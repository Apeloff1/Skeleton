"""Claim dependency propagation for fail-closed higher-level conclusions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class ClaimDependency:
    claim_id: str
    status: str
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.claim_id:
            raise ReverseEngineeringError("claim dependency requires claim_id")
        if self.status not in {"hypothesis", "supported", "conflicted", "rejected"}:
            raise ReverseEngineeringError("invalid claim dependency status")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ReverseEngineeringError("claim dependencies must be unique")
        if self.claim_id in self.depends_on:
            raise ReverseEngineeringError("claim cannot depend on itself")


@dataclass(frozen=True)
class ClaimDependencyResult:
    claim_id: str
    declared_status: str
    effective_status: str
    blocking_dependency_ids: tuple[str, ...]


@dataclass(frozen=True)
class ClaimDependencyReport:
    claim_count: int
    blocked_count: int
    rejected_count: int
    results: tuple[ClaimDependencyResult, ...]
    cycle_free: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_count": self.claim_count,
            "blocked_count": self.blocked_count,
            "rejected_count": self.rejected_count,
            "results": [
                {
                    "claim_id": item.claim_id,
                    "declared_status": item.declared_status,
                    "effective_status": item.effective_status,
                    "blocking_dependency_ids": list(item.blocking_dependency_ids),
                }
                for item in self.results
            ],
            "cycle_free": self.cycle_free,
            "digest": self.digest,
        }


def analyze_claim_dependencies(
    claims: Sequence[ClaimDependency],
) -> ClaimDependencyReport:
    if not claims:
        raise ReverseEngineeringError("claim dependency analysis requires claims")
    ids = [claim.claim_id for claim in claims]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("claim ids must be unique")
    by_id = {claim.claim_id: claim for claim in claims}
    for claim in claims:
        missing = set(claim.depends_on) - set(by_id)
        if missing:
            raise ReverseEngineeringError(
                f"claim {claim.claim_id!r} has unknown dependencies"
            )

    state: dict[str, int] = {}
    cycle = False

    def visit(claim_id: str) -> None:
        nonlocal cycle
        marker = state.get(claim_id, 0)
        if marker == 1:
            cycle = True
            return
        if marker == 2:
            return
        state[claim_id] = 1
        for dependency in by_id[claim_id].depends_on:
            visit(dependency)
        state[claim_id] = 2

    for claim_id in sorted(by_id):
        visit(claim_id)

    if cycle:
        payload = {
            "claims": [
                {
                    "claim_id": claim.claim_id,
                    "status": claim.status,
                    "depends_on": list(claim.depends_on),
                }
                for claim in sorted(claims, key=lambda value: value.claim_id)
            ]
        }
        return ClaimDependencyReport(
            claim_count=len(claims),
            blocked_count=len(claims),
            rejected_count=sum(claim.status == "rejected" for claim in claims),
            results=tuple(
                ClaimDependencyResult(
                    claim_id=claim.claim_id,
                    declared_status=claim.status,
                    effective_status="conflicted",
                    blocking_dependency_ids=tuple(sorted(claim.depends_on)),
                )
                for claim in sorted(claims, key=lambda value: value.claim_id)
            ),
            cycle_free=False,
            digest=stable_digest(payload),
        )

    effective: dict[str, str] = {}

    def resolve(claim_id: str) -> str:
        if claim_id in effective:
            return effective[claim_id]
        claim = by_id[claim_id]
        dependency_statuses = [resolve(dep) for dep in claim.depends_on]
        if claim.status == "rejected" or "rejected" in dependency_statuses:
            status = "rejected"
        elif claim.status == "conflicted" or "conflicted" in dependency_statuses:
            status = "conflicted"
        elif claim.status == "supported" and all(status == "supported" for status in dependency_statuses):
            status = "supported"
        else:
            status = "hypothesis"
        effective[claim_id] = status
        return status

    results: list[ClaimDependencyResult] = []
    for claim_id in sorted(by_id):
        claim = by_id[claim_id]
        status = resolve(claim_id)
        blockers = tuple(
            sorted(
                dep
                for dep in claim.depends_on
                if resolve(dep) != "supported"
            )
        )
        results.append(
            ClaimDependencyResult(
                claim_id=claim_id,
                declared_status=claim.status,
                effective_status=status,
                blocking_dependency_ids=blockers,
            )
        )

    payload = {
        "claims": [
            {
                "claim_id": claim.claim_id,
                "status": claim.status,
                "depends_on": list(claim.depends_on),
            }
            for claim in sorted(claims, key=lambda value: value.claim_id)
        ]
    }
    return ClaimDependencyReport(
        claim_count=len(claims),
        blocked_count=sum(
            item.effective_status != item.declared_status
            or bool(item.blocking_dependency_ids)
            for item in results
        ),
        rejected_count=sum(item.effective_status == "rejected" for item in results),
        results=tuple(results),
        cycle_free=True,
        digest=stable_digest(payload),
    )
