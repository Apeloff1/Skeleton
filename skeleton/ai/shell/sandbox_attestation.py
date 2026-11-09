"""Attest and verify sandbox backend capabilities against AI contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.shells.ai.resource_profile import AIResourceProfile
from skeleton.shells.ai.sandbox_contract import AISandboxContract
from skeleton.shells.isolation import IsolationLevel


@dataclass(frozen=True)
class SandboxCapabilities:
    backend_id: str
    backend_version: str
    max_level: IsolationLevel
    private_tmp: bool
    clean_environment: bool
    readonly_source: bool
    network_namespace: bool
    home_hiding: bool
    process_group: bool
    no_new_privileges: bool
    syscall_filter: bool
    resource_limits: bool
    max_profile: AIResourceProfile

    def __post_init__(self) -> None:
        if not self.backend_id or not self.backend_version:
            raise ValueError("sandbox backend identity required")
        object.__setattr__(self, "max_level", IsolationLevel(self.max_level))

    def to_dict(self) -> dict[str, object]:
        return {
            "backend_id": self.backend_id,
            "backend_version": self.backend_version,
            "max_level": self.max_level.value,
            "private_tmp": self.private_tmp,
            "clean_environment": self.clean_environment,
            "readonly_source": self.readonly_source,
            "network_namespace": self.network_namespace,
            "home_hiding": self.home_hiding,
            "process_group": self.process_group,
            "no_new_privileges": self.no_new_privileges,
            "syscall_filter": self.syscall_filter,
            "resource_limits": self.resource_limits,
            "max_profile": self.max_profile.to_dict(),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SandboxAttestationReport:
    compatible: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"compatible": self.compatible, "reasons": list(self.reasons)}


class SandboxAttestationVerifier:
    def inspect(
        self,
        contract: AISandboxContract,
        capabilities: SandboxCapabilities,
    ) -> SandboxAttestationReport:
        reasons = []
        strength = {
            IsolationLevel.HOST: 0,
            IsolationLevel.WORKSPACE: 1,
            IsolationLevel.SANDBOXED: 2,
        }
        requirement = contract.isolation.requirement
        if strength[capabilities.max_level] < strength[requirement.level]:
            reasons.append("sandbox isolation level is below requirement")
        if requirement.require_private_tmp and not capabilities.private_tmp:
            reasons.append("sandbox cannot provide private temporary directory")
        if requirement.require_clean_environment and not capabilities.clean_environment:
            reasons.append("sandbox cannot provide clean environment")
        if requirement.require_readonly_source and not capabilities.readonly_source:
            reasons.append("sandbox cannot provide read-only source")
        if not requirement.allow_network and contract.require_network_namespace and not capabilities.network_namespace:
            reasons.append("sandbox cannot isolate network")
        if not requirement.allow_home and not capabilities.home_hiding:
            reasons.append("sandbox cannot hide home directory")
        if contract.require_process_group and not capabilities.process_group:
            reasons.append("sandbox cannot isolate process group")
        if contract.require_no_new_privileges and not capabilities.no_new_privileges:
            reasons.append("sandbox lacks no-new-privileges enforcement")
        if contract.require_syscall_filter and not capabilities.syscall_filter:
            reasons.append("sandbox lacks syscall filtering")
        if not capabilities.resource_limits:
            reasons.append("sandbox does not enforce resource limits")
        elif not contract.resources.profile.no_wider_than(capabilities.max_profile):
            reasons.append("sandbox resource capability is below requested ceiling")
        return SandboxAttestationReport(not reasons, tuple(reasons))
