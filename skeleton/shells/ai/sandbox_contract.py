"""Combined isolation and resource contract for AI shell execution."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.shells.ai.isolation_compiler import AIIsolationDecision
from skeleton.shells.ai.resource_profile import AIResourceDecision


@dataclass(frozen=True)
class AISandboxContract:
    isolation: AIIsolationDecision
    resources: AIResourceDecision
    require_process_group: bool = True
    require_no_new_privileges: bool = True
    require_syscall_filter: bool = False
    require_network_namespace: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "isolation": self.isolation.to_dict(),
            "resources": self.resources.to_dict(),
            "require_process_group": self.require_process_group,
            "require_no_new_privileges": self.require_no_new_privileges,
            "require_syscall_filter": self.require_syscall_filter,
            "require_network_namespace": self.require_network_namespace,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


class AISandboxContractBuilder:
    def build(
        self,
        isolation: AIIsolationDecision,
        resources: AIResourceDecision,
    ) -> AISandboxContract:
        level = isolation.requirement.level.value
        requires_strong = level == "sandboxed"
        return AISandboxContract(
            isolation,
            resources,
            require_process_group=True,
            require_no_new_privileges=requires_strong,
            require_syscall_filter=requires_strong,
            require_network_namespace=not isolation.requirement.allow_network,
        )
