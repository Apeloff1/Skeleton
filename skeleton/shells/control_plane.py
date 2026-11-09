"""Composition root for shell policy, admission, queueing, and execution metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.shells.admission import CommandAdmission
from skeleton.shells.capabilities import CapabilityGrant
from skeleton.shells.commands import CommandCatalog
from skeleton.shells.dedupe import DedupeRegistry
from skeleton.shells.explain import explain_command
from skeleton.shells.leases import LeaseRegistry
from skeleton.shells.preflight import PreflightAnalyzer, PreflightReport
from skeleton.shells.queue import ShellWorkQueue
from skeleton.shells.rate_limit import RateLimiter
from skeleton.shells.runner import ShellCommand, ShellPolicy
from skeleton.shells.workspace import WorkspacePolicy


@dataclass(frozen=True)
class ControlPlaneDecision:
    allowed: bool
    reason: str = ""
    retry_after_seconds: float = 0.0


class ShellControlPlane:
    """Policy-only control plane; it never spawns a process itself."""

    def __init__(
        self,
        *,
        policy: ShellPolicy,
        catalog: CommandCatalog,
        workspace: WorkspacePolicy | None = None,
        rate_limiter: RateLimiter | None = None,
        dedupe: DedupeRegistry | None = None,
        leases: LeaseRegistry | None = None,
        queue: ShellWorkQueue | None = None,
    ) -> None:
        self.policy = policy
        self.catalog = catalog
        self.admission = CommandAdmission(catalog, workspace)
        self.preflight = PreflightAnalyzer(self.admission)
        self.rate_limiter = rate_limiter or RateLimiter()
        self.dedupe = dedupe or DedupeRegistry()
        self.leases = leases or LeaseRegistry()
        self.queue = queue or ShellWorkQueue()

    def inspect(self, command: ShellCommand, grant: CapabilityGrant) -> ControlPlaneDecision:
        decision = self.admission.inspect(command, grant)
        return ControlPlaneDecision(decision.allowed, decision.reason)

    def admit_with_rate_limit(
        self,
        command: ShellCommand,
        grant: CapabilityGrant,
        *,
        rate_key: str,
    ) -> ControlPlaneDecision:
        admission = self.admission.inspect(command, grant)
        if not admission.allowed:
            return ControlPlaneDecision(False, admission.reason)
        rate = self.rate_limiter.acquire(rate_key)
        if not rate.allowed:
            return ControlPlaneDecision(False, "rate limit exceeded", rate.retry_after_seconds)
        return ControlPlaneDecision(True)

    def preflight_commands(self, commands, grant: CapabilityGrant) -> PreflightReport:
        return self.preflight.commands(commands, grant)

    def explain(self, command: str, grant: CapabilityGrant) -> dict[str, Any]:
        return explain_command(command, catalog=self.catalog, policy=self.policy, grant=grant).to_dict()
