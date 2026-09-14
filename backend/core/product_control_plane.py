"""Restart-safe control plane for canonical product operations.

Owns durable policy persistence and the operation coordinator as one service
boundary. New installations receive an explicit versioned allow-list matching
the canonical product shell; persisted policy always wins on restart.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.canonical_product_policy import CANONICAL_PRODUCT_POLICY, POLICY_VERSION
from core.charter_policy import Charter, CharterPolicy, Edict, Rule
from core.policy_repository import PolicyRepository
from core.product_executor_registry import ExecutorNotRegistered, ProductExecutorRegistry
from core.product_kernel import PRODUCT_KERNEL, ProductKernel
from core.product_operations import AdmittedOperation, ProductOperationCoordinator


class ProductControlPlane:
    def __init__(
        self,
        root: str | Path,
        *,
        kernel: ProductKernel = PRODUCT_KERNEL,
        outbox_cap: int = 4096,
        bootstrap_policy: bool = True,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.policy_repository = PolicyRepository(self.root / "policy")
        self.policy: CharterPolicy = self.policy_repository.load()
        self.bootstrap_policy = bootstrap_policy
        if bootstrap_policy and not self.policy.snapshot().charters:
            self._bootstrap_canonical_policy()
        self.operations = ProductOperationCoordinator(
            self.root / "operations",
            kernel=kernel,
            policy=self.policy,
            outbox_cap=outbox_cap,
        )

    def _bootstrap_canonical_policy(self) -> None:
        for domain_policy in CANONICAL_PRODUCT_POLICY:
            self.policy.ratify(domain_policy.domain, domain_policy.rules())
        self.policy_repository.save(self.policy)

    def ratify(self, domain: str, rules: list[Rule]) -> Charter:
        charter = self.policy.ratify(domain, rules)
        self.policy_repository.save(self.policy)
        return charter

    def propose_edict(self, domain: str, rule: Rule, proposed_by: str) -> Edict | None:
        edict = self.policy.propose_edict(domain, rule, proposed_by)
        if edict is not None:
            self.policy_repository.save(self.policy)
        return edict

    def enforce_edict(self, edict_id: str) -> bool:
        enforced = self.policy.enforce_edict(edict_id)
        if enforced:
            self.policy_repository.save(self.policy)
        return enforced

    def admit(self, **kwargs: Any) -> AdmittedOperation:
        return self.operations.admit(**kwargs)

    def pending(self) -> list[dict[str, Any]]:
        return [
            {
                "operation_id": operation.id,
                "capability_id": operation.capability_id,
                "pillar": operation.pillar,
                "domain": operation.domain,
                "action": operation.action,
                "principal": operation.principal,
                "outbox_seq": operation.outbox_seq,
                "admitted_at": operation.admitted_at,
                "idempotency_key": operation.idempotency_key,
            }
            for operation in self.operations.pending_operations()
        ]

    async def execute_registered(self, seq: int, registry: ProductExecutorRegistry) -> bool:
        operation = next((item for item in self.operations.pending_operations() if item.outbox_seq == seq), None)
        if operation is None:
            return False
        try:
            executor = registry.executor_for(operation)
        except ExecutorNotRegistered:
            return False
        result = await self.operations.execute_one(seq, executor)
        return result.confirmed

    async def execute_registered_pending(
        self,
        registry: ProductExecutorRegistry,
        *,
        limit: int | None = None,
    ) -> int:
        pending = self.operations.pending_operations()
        if limit is not None:
            if limit < 0:
                raise ValueError("limit cannot be negative")
            pending = pending[:limit]
        confirmed = 0
        for operation in pending:
            if await self.execute_registered(operation.outbox_seq, registry):
                confirmed += 1
        return confirmed

    def status(self) -> dict[str, Any]:
        governance = self.policy.snapshot()
        return {
            "policy_version": POLICY_VERSION,
            "policy_bootstrap_enabled": self.bootstrap_policy,
            "kernel": {
                "capabilities": [
                    {
                        "id": capability.id,
                        "pillar": capability.pillar.value,
                        "critical": capability.critical,
                    }
                    for capability in self.operations.kernel.all()
                ],
                "critical_ids": list(self.operations.kernel.critical_ids()),
            },
            "governance": {
                "charters": [asdict(charter) for charter in governance.charters],
                "edicts": [asdict(edict) for edict in governance.edicts],
            },
            "operations": self.operations.snapshot(),
        }
