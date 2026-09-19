"""Distributed AIPolicyStore semantics over a CAS backend."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.policy import AIShellPolicy
from skeleton.shells.ai.policy_store import AIPolicyConflict, AIPolicyRevision
from skeleton.shells.ai.store_protocol import VersionedStateBackend


@dataclass(frozen=True)
class DistributedPolicyConfig:
    namespace: str = "shell-ai-policy"
    key: str = "current"


class DistributedAIPolicyStore:
    """Multi-instance policy store using backend revision as policy revision."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        initial: AIShellPolicy | None = None,
        *,
        config: DistributedPolicyConfig | None = None,
    ) -> None:
        self.backend = backend
        self.config = config or DistributedPolicyConfig()
        existing = backend.get(self.config.namespace, self.config.key)
        if existing is None:
            policy = initial or AIShellPolicy()
            try:
                backend.put_if_absent(
                    self.config.namespace,
                    self.config.key,
                    policy,
                )
            except DistributedStateConflict:
                pass

    def current(self) -> AIPolicyRevision:
        record = self.backend.get(self.config.namespace, self.config.key)
        if record is None or not isinstance(record.value, AIShellPolicy):
            raise RuntimeError("distributed AI policy record missing or invalid")
        return AIPolicyRevision(
            record.revision,
            record.value.fingerprint,
            record.value,
        )

    def compare_and_swap(
        self,
        expected_revision: int,
        policy: AIShellPolicy,
    ) -> AIPolicyRevision:
        try:
            record = self.backend.compare_and_swap(
                self.config.namespace,
                self.config.key,
                expected_revision=expected_revision,
                value=policy,
            )
        except DistributedStateConflict as exc:
            raise AIPolicyConflict("distributed AI policy revision conflict") from exc
        return AIPolicyRevision(
            record.revision,
            policy.fingerprint,
            policy,
        )

    def replace(self, policy: AIShellPolicy) -> AIPolicyRevision:
        current = self.current()
        return self.compare_and_swap(current.revision, policy)
