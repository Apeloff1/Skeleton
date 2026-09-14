"""Canonical fail-closed charter for product actions exposed by the new shell.

The product UI is allowed to submit only this explicit action vocabulary. Legacy
routers remain outside this charter and cannot become admitted merely because a
capability exists. The bootstrap is versioned so future policy expansion is an
intentional migration rather than an implicit wildcard.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.charter_policy import Rule


POLICY_VERSION = 1


@dataclass(frozen=True, slots=True)
class CanonicalDomainPolicy:
    domain: str
    actions: tuple[str, ...]

    def rules(self) -> list[Rule]:
        return [
            Rule(
                id=f"product-v{POLICY_VERSION}:{self.domain}:{action}",
                action=action,
                min_weight=0,
                requires_quorum=False,
            )
            for action in self.actions
        ]


CANONICAL_PRODUCT_POLICY: tuple[CanonicalDomainPolicy, ...] = (
    CanonicalDomainPolicy("studio", ("project.create", "build.submit", "pipeline.inspect")),
    CanonicalDomainPolicy("world-forge", ("world.create", "world.systems.compose", "asset.forge")),
    CanonicalDomainPolicy("playables", ("playable.launch", "runtime.sessions", "progress.inspect")),
    CanonicalDomainPolicy("jeeves", ("jeeves.reason", "jeeves.plan", "agents.review")),
    CanonicalDomainPolicy("academy", ("academy.continue", "academy.practice", "academy.progress")),
    CanonicalDomainPolicy("operations", ("ops.agents", "ops.runtime", "ops.deployments")),
    CanonicalDomainPolicy("governance", ("governance.policy", "governance.audit", "governance.safety")),
)


def canonical_domains() -> tuple[str, ...]:
    return tuple(item.domain for item in CANONICAL_PRODUCT_POLICY)


def canonical_actions(domain: str) -> tuple[str, ...]:
    match = next((item for item in CANONICAL_PRODUCT_POLICY if item.domain == domain), None)
    return match.actions if match else ()
