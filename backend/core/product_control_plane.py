"""Restart-safe, evidence-derived control plane for canonical product operations."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.capability_readiness import ReadinessReport, evaluate_readiness
from core.canonical_product_policy import CANONICAL_PRODUCT_POLICY, POLICY_VERSION
from core.charter_policy import Charter, CharterPolicy, Edict, Rule
from core.execution_evidence import derive_ledger, derive_lifecycle
from core.execution_receipts import ExecutionReceiptStore
from core.policy_repository import PolicyRepository
from core.product_default_executors import build_default_executor_registry
from core.product_executor_registry import ExecutorNotRegistered, ProductExecutorRegistry
from core.product_kernel import PRODUCT_KERNEL, ProductKernel
from core.product_operations import AdmittedOperation, OperationExecutionError, ProductOperationCoordinator
from core.system_assurance import evaluate_assurance
from core.system_root_attestation import build_root_attestation


class ProductControlPlane:
    def __init__(self, root: str | Path, *, kernel: ProductKernel = PRODUCT_KERNEL,
                 outbox_cap: int = 4096, bootstrap_policy: bool = True,
                 bind_native_executors: bool = True) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.policy_repository = PolicyRepository(self.root / "policy")
        self.policy: CharterPolicy = self.policy_repository.load()
        self.bootstrap_policy = bootstrap_policy
        if bootstrap_policy and not self.policy.snapshot().charters:
            self._bootstrap_canonical_policy()
        self.operations = ProductOperationCoordinator(
            self.root / "operations", kernel=kernel, policy=self.policy, outbox_cap=outbox_cap,
        )
        self.receipts = ExecutionReceiptStore(self.root / "receipts")
        if bind_native_executors:
            self.executors, self.native_executors = build_default_executor_registry(
                self.receipts,
                operations_provider=self.operations.snapshot,
                policy_provider=self._policy_projection,
                audit_provider=self._audit_projection,
                safety_provider=self._safety_projection,
            )
        else:
            self.executors = ProductExecutorRegistry()
            self.native_executors = None

    def _bootstrap_canonical_policy(self) -> None:
        for domain_policy in CANONICAL_PRODUCT_POLICY:
            self.policy.ratify(domain_policy.domain, domain_policy.rules())
        self.policy_repository.save(self.policy)

    def _policy_projection(self) -> dict[str, Any]:
        snapshot = self.policy.snapshot()
        return {
            "policy_version": POLICY_VERSION,
            "charters": [asdict(charter) for charter in snapshot.charters],
            "edicts": [asdict(edict) for edict in snapshot.edicts],
        }

    def _audit_projection(self) -> list[dict[str, Any]]:
        return [asdict(entry) for entry in self.operations.audit.entries(limit=50)]

    def _readiness_model(self) -> ReadinessReport:
        policy = self.policy.snapshot()
        return evaluate_readiness(
            canonical_policy=CANONICAL_PRODUCT_POLICY,
            policy_domains=[
                {"domain": charter.domain, "rules": [asdict(rule) for rule in charter.rules]}
                for charter in policy.charters
            ],
            executor_bindings=self.executors.snapshot(),
            receipt_stats=self.receipts.stats(),
        )

    def readiness_report(self) -> dict[str, Any]:
        return asdict(self._readiness_model())

    def executor_coverage(self) -> dict[str, Any]:
        canonical = [(domain.domain, action) for domain in CANONICAL_PRODUCT_POLICY for action in domain.actions]
        bound = {(item["capability_id"], item["action"]) for item in self.executors.snapshot()}
        covered = [(domain, action) for domain, action in canonical if (domain, action) in bound]
        missing = [
            {"capability_id": domain, "action": action}
            for domain, action in canonical if (domain, action) not in bound
        ]
        total = len(canonical)
        return {
            "canonical_actions": total,
            "bound_actions": len(covered),
            "coverage_pct": round((len(covered) / total) * 100, 1) if total else 100.0,
            "missing": missing,
        }

    def assurance_report(self) -> dict[str, Any]:
        return asdict(evaluate_assurance(
            lifecycle=self.execution_ledger(),
            operations=self.operations.snapshot(),
            executor_bindings=self.executors.snapshot(),
            executor_coverage=self.executor_coverage(),
            receipt_stats=self.receipts.stats(),
            readiness=self.readiness_report(),
        ))

    def system_root(self) -> dict[str, Any]:
        operations = self.operations.snapshot()
        attestation = build_root_attestation({
            "policy": self._policy_projection(),
            "executors": list(self.executors.snapshot()),
            "readiness": self.readiness_report(),
            "lifecycle": self.execution_ledger(),
            "audit": {"sequence": operations.get("audit_sequence"), "head": operations.get("audit_head")},
            "receipts": self.receipts.stats(),
            "kernel": [
                {"id": capability.id, "pillar": capability.pillar.value, "critical": capability.critical}
                for capability in self.operations.kernel.all()
            ],
        })
        return {
            "schema_version": attestation.schema_version,
            "components": [
                {"name": name, "sha256": digest} for name, digest in attestation.components
            ],
            "root_sha256": attestation.root_sha256,
        }

    def _safety_projection(self) -> dict[str, Any]:
        assurance = self.assurance_report()
        readiness = self.readiness_report()
        return {
            "posture": assurance["posture"],
            "hard_failures": assurance["hard_failures"],
            "warnings": assurance["warnings"],
            "native_coverage_pct": assurance["native_coverage_pct"],
            "readiness_pct": assurance["readiness_pct"],
            "attestation_sha256": assurance["attestation_sha256"],
            "readiness_attestation_sha256": readiness["attestation_sha256"],
            "system_root_sha256": self.system_root()["root_sha256"],
            "invariants": assurance["invariants"],
        }

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
                "executor_bound": self.executors.resolve(operation.capability_id, operation.action) is not None,
            }
            for operation in self.operations.pending_operations()
        ]

    def audit_history(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if limit < 0 or limit > 500:
            raise ValueError("audit limit must be between 0 and 500")
        return [asdict(entry) for entry in self.operations.audit.entries(limit=limit)]

    def receipt_history(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return [asdict(receipt) for receipt in self.receipts.list_recent(limit=limit)]

    def receipt(self, operation_id: str) -> dict[str, Any] | None:
        receipt = self.receipts.read(operation_id)
        return asdict(receipt) if receipt is not None else None

    def receipt_result(self, operation_id: str) -> dict[str, Any]:
        return self.receipts.load_result(operation_id)

    def operation_lifecycle(self, operation_id: str) -> dict[str, Any]:
        pending = self.pending()
        receipts = self.receipt_history(limit=500)
        audit = self.audit_history(limit=500)
        evidence = derive_lifecycle(
            operation_id, pending_operations=pending, receipts=receipts, audit_entries=audit,
        )
        pending_item = next((item for item in pending if item["operation_id"] == operation_id), None)
        receipt_item = next((item for item in receipts if item["operation_id"] == operation_id), None)
        binding = None
        if pending_item is not None:
            binding = self.executors.resolve(pending_item["capability_id"], pending_item["action"])
        return {
            **asdict(evidence),
            "pending_operation": pending_item,
            "executor": (
                {"name": binding.name, "version": binding.version,
                 "effect_class": binding.effect_class, "replay_safe": binding.replay_safe}
                if binding is not None else None
            ),
            "receipt": receipt_item,
        }

    def execution_ledger(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in derive_ledger(
            pending_operations=self.pending(),
            receipts=self.receipt_history(limit=500),
            audit_entries=self.audit_history(limit=500),
        )]

    async def execute_registered(self, seq: int, registry: ProductExecutorRegistry | None = None) -> bool:
        active_registry = registry or self.executors
        operation = next((item for item in self.operations.pending_operations() if item.outbox_seq == seq), None)
        if operation is None:
            return False
        try:
            executor = active_registry.executor_for(operation)
        except ExecutorNotRegistered:
            return False
        return (await self.operations.execute_one(seq, executor)).confirmed

    async def dispatch_pending(self, registry: ProductExecutorRegistry | None = None,
                               *, limit: int | None = None) -> dict[str, Any]:
        active_registry = registry or self.executors
        pending = self.operations.pending_operations()
        if limit is not None:
            if limit < 0:
                raise ValueError("limit cannot be negative")
            pending = pending[:limit]
        report: dict[str, Any] = {
            "attempted": len(pending), "confirmed": [], "deferred": [], "unbound": [], "failed": [],
        }
        for operation in pending:
            binding = active_registry.resolve(operation.capability_id, operation.action)
            if binding is None:
                report["unbound"].append(operation.outbox_seq)
                continue
            try:
                result = await self.operations.execute_one(operation.outbox_seq, binding.executor)
            except OperationExecutionError as exc:
                report["failed"].append({
                    "outbox_seq": operation.outbox_seq,
                    "operation_id": operation.id,
                    "executor": binding.name,
                    "error": str(exc),
                })
                continue
            report["confirmed" if result.confirmed else "deferred"].append(operation.outbox_seq)
        report["remaining"] = self.operations.outbox.pending_count
        return report

    async def execute_registered_pending(self, registry: ProductExecutorRegistry | None = None,
                                         *, limit: int | None = None) -> int:
        return len((await self.dispatch_pending(registry, limit=limit))["confirmed"])

    def status(self) -> dict[str, Any]:
        governance = self.policy.snapshot()
        ledger = self.execution_ledger()
        lifecycle_counts: dict[str, int] = {}
        anomaly_count = 0
        for item in ledger:
            lifecycle_counts[item["state"]] = lifecycle_counts.get(item["state"], 0) + 1
            anomaly_count += len(item.get("anomalies", ()))
        readiness = self.readiness_report()
        assurance = self.assurance_report()
        root = self.system_root()
        return {
            "policy_version": POLICY_VERSION,
            "policy_bootstrap_enabled": self.bootstrap_policy,
            "kernel": {
                "capabilities": [
                    {"id": capability.id, "pillar": capability.pillar.value, "critical": capability.critical}
                    for capability in self.operations.kernel.all()
                ],
                "critical_ids": list(self.operations.kernel.critical_ids()),
            },
            "governance": {
                "charters": [asdict(charter) for charter in governance.charters],
                "edicts": [asdict(edict) for edict in governance.edicts],
            },
            "executors": {
                "bound": len(self.executors), "bindings": list(self.executors.snapshot()),
                "coverage": self.executor_coverage(),
            },
            "readiness": readiness,
            "receipts": self.receipts.stats(),
            "lifecycle": {
                "operations": len(ledger), "states": lifecycle_counts,
                "evidence_gaps": lifecycle_counts.get("evidence_gap", 0) + lifecycle_counts.get("receipt_unattested", 0),
                "anomalies": anomaly_count,
            },
            "assurance": assurance,
            "system_root": root,
            "safety": self._safety_projection(),
            "operations": self.operations.snapshot(),
        }
