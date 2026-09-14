"""Restart-safe control plane for canonical product operations.

Owns durable policy persistence and the operation coordinator as one service
boundary. Mutating governance methods save immediately; admission always uses
the currently persisted policy state.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.charter_policy import Charter, CharterPolicy, Edict, Rule
from core.policy_repository import PolicyRepository
from core.product_kernel import PRODUCT_KERNEL, ProductKernel
from core.product_operations import AdmittedOperation, ProductOperationCoordinator


class ProductControlPlane:
    def __init__(
        self,
        root: str | Path,
        *,
        kernel: ProductKernel = PRODUCT_KERNEL,
        outbox_cap: int = 4096,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.policy_repository = PolicyRepository(self.root / "policy")
        self.policy: CharterPolicy = self.policy_repository.load()
        self.operations = ProductOperationCoordinator(
            self.root / "operations",
            kernel=kernel,
            policy=self.policy,
            outbox_cap=outbox_cap,
        )

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

    def status(self) -> dict[str, Any]:
        governance = self.policy.snapshot()
        return {
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
