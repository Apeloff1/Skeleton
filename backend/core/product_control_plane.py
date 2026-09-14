"""Restart-safe, evidence-derived control plane for canonical product operations."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.capability_readiness import ReadinessReport, evaluate_readiness
from core.canonical_product_policy import CANONICAL_PRODUCT_POLICY, POLICY_VERSION
from core.charter_policy import Charter, CharterPolicy, Edict, Rule
from core.curiosity_engine import CuriosityEngine
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
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.policy_repository = PolicyRepository(self.root / "policy")
        self.policy: CharterPolicy = self.policy_repository.load()
        self.bootstrap_policy = bootstrap_policy
        if bootstrap_policy and not self.policy.snapshot().charters: self._bootstrap_canonical_policy()
        self.operations = ProductOperationCoordinator(self.root / "operations", kernel=kernel, policy=self.policy, outbox_cap=outbox_cap)
        self.receipts = ExecutionReceiptStore(self.root / "receipts")
        self.curiosity = CuriosityEngine(self.root / "curiosity")
        if bind_native_executors:
            self.executors, self.native_executors = build_default_executor_registry(
                self.receipts, curiosity=self.curiosity,
                operations_provider=self._operations_projection,
                policy_provider=self._policy_projection, audit_provider=self._audit_projection,
                safety_provider=self._safety_projection,
            )
        else:
            self.executors = ProductExecutorRegistry(); self.native_executors = None

    def _bootstrap_canonical_policy(self) -> None:
        for item in CANONICAL_PRODUCT_POLICY: self.policy.ratify(item.domain, item.rules())
        self.policy_repository.save(self.policy)

    def _policy_projection(self) -> dict[str, Any]:
        snap = self.policy.snapshot()
        return {"policy_version": POLICY_VERSION, "charters": [asdict(x) for x in snap.charters], "edicts": [asdict(x) for x in snap.edicts]}

    def _audit_projection(self) -> list[dict[str, Any]]:
        return [asdict(x) for x in self.operations.audit.entries(limit=50)]

    def _operations_projection(self) -> dict[str, Any]:
        projection = dict(self.operations.snapshot())
        projection["outbox_health"] = self.operations.outbox.health()
        projection["curiosity"] = self.curiosity.stats()
        return projection

    def _readiness_model(self) -> ReadinessReport:
        snap = self.policy.snapshot()
        return evaluate_readiness(
            canonical_policy=CANONICAL_PRODUCT_POLICY,
            policy_domains=[{"domain": c.domain, "rules": [asdict(r) for r in c.rules]} for c in snap.charters],
            executor_bindings=self.executors.snapshot(), receipt_stats=self.receipts.stats(),
        )

    def readiness_report(self) -> dict[str, Any]: return asdict(self._readiness_model())

    def executor_coverage(self) -> dict[str, Any]:
        canonical = [(d.domain, a) for d in CANONICAL_PRODUCT_POLICY for a in d.actions]
        bound = {(x["capability_id"], x["action"]) for x in self.executors.snapshot()}
        missing = [{"capability_id": d, "action": a} for d, a in canonical if (d, a) not in bound]
        total = len(canonical); ready = total - len(missing)
        return {"canonical_actions": total, "bound_actions": ready, "coverage_pct": round(ready / total * 100, 1) if total else 100.0, "missing": missing}

    def assurance_report(self) -> dict[str, Any]:
        return asdict(evaluate_assurance(
            lifecycle=self.execution_ledger(), operations=self._operations_projection(),
            executor_bindings=self.executors.snapshot(), executor_coverage=self.executor_coverage(),
            receipt_stats=self.receipts.stats(), readiness=self.readiness_report(),
        ))

    def system_root(self) -> dict[str, Any]:
        operations = self._operations_projection()
        att = build_root_attestation({
            "policy": self._policy_projection(), "executors": list(self.executors.snapshot()),
            "readiness": self.readiness_report(), "lifecycle": self.execution_ledger(),
            "audit": {"sequence": operations.get("audit_sequence"), "head": operations.get("audit_head"), "health": operations.get("audit_health")},
            "outbox": operations.get("outbox_health"), "receipts": self.receipts.stats(),
            "curiosity": self.curiosity.stats(),
            "kernel": [{"id": c.id, "pillar": c.pillar.value, "critical": c.critical} for c in self.operations.kernel.all()],
        })
        return {"schema_version": att.schema_version, "components": [{"name": n, "sha256": d} for n, d in att.components], "root_sha256": att.root_sha256}

    def _safety_projection(self) -> dict[str, Any]:
        assurance = self.assurance_report(); readiness = self.readiness_report()
        return {"posture": assurance["posture"], "hard_failures": assurance["hard_failures"], "warnings": assurance["warnings"],
            "native_coverage_pct": assurance["native_coverage_pct"], "readiness_pct": assurance["readiness_pct"],
            "attestation_sha256": assurance["attestation_sha256"], "readiness_attestation_sha256": readiness["attestation_sha256"],
            "system_root_sha256": self.system_root()["root_sha256"], "curiosity": self.curiosity.stats(),
            "invariants": assurance["invariants"]}

    def ratify(self, domain: str, rules: list[Rule]) -> Charter:
        charter = self.policy.ratify(domain, rules); self.policy_repository.save(self.policy); return charter
    def propose_edict(self, domain: str, rule: Rule, proposed_by: str) -> Edict | None:
        edict = self.policy.propose_edict(domain, rule, proposed_by)
        if edict is not None: self.policy_repository.save(self.policy)
        return edict
    def enforce_edict(self, edict_id: str) -> bool:
        ok = self.policy.enforce_edict(edict_id)
        if ok: self.policy_repository.save(self.policy)
        return ok
    def admit(self, **kwargs: Any) -> AdmittedOperation: return self.operations.admit(**kwargs)

    def pending(self) -> list[dict[str, Any]]:
        return [{"operation_id": o.id, "capability_id": o.capability_id, "pillar": o.pillar, "domain": o.domain, "action": o.action,
                 "principal": o.principal, "outbox_seq": o.outbox_seq, "admitted_at": o.admitted_at, "idempotency_key": o.idempotency_key,
                 "executor_bound": self.executors.resolve(o.capability_id, o.action) is not None} for o in self.operations.pending_operations()]

    def audit_history(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if limit < 0 or limit > 500: raise ValueError("audit limit must be between 0 and 500")
        return [asdict(x) for x in self.operations.audit.entries(limit=limit)]
    def receipt_history(self, *, limit: int = 50) -> list[dict[str, Any]]: return [asdict(x) for x in self.receipts.list_recent(limit=limit)]
    def receipt(self, operation_id: str) -> dict[str, Any] | None:
        value = self.receipts.read(operation_id); return asdict(value) if value is not None else None
    def receipt_result(self, operation_id: str) -> dict[str, Any]: return self.receipts.load_result(operation_id)

    def operation_lifecycle(self, operation_id: str) -> dict[str, Any]:
        pending = self.pending(); receipts = self.receipt_history(limit=500); audit = self.audit_history(limit=500)
        evidence = derive_lifecycle(operation_id, pending_operations=pending, receipts=receipts, audit_entries=audit)
        p = next((x for x in pending if x["operation_id"] == operation_id), None); r = next((x for x in receipts if x["operation_id"] == operation_id), None)
        binding = self.executors.resolve(p["capability_id"], p["action"]) if p else None
        return {**asdict(evidence), "pending_operation": p,
                "executor": ({"name": binding.name, "version": binding.version, "effect_class": binding.effect_class, "replay_safe": binding.replay_safe} if binding else None),
                "receipt": r}

    def execution_ledger(self) -> list[dict[str, Any]]:
        return [asdict(x) for x in derive_ledger(pending_operations=self.pending(), receipts=self.receipt_history(limit=500), audit_entries=self.audit_history(limit=500))]

    async def execute_registered(self, seq: int, registry: ProductExecutorRegistry | None = None) -> bool:
        active = registry or self.executors; operation = next((x for x in self.operations.pending_operations() if x.outbox_seq == seq), None)
        if operation is None: return False
        try: executor = active.executor_for(operation)
        except ExecutorNotRegistered: return False
        return (await self.operations.execute_one(seq, executor)).confirmed

    async def dispatch_pending(self, registry: ProductExecutorRegistry | None = None, *, limit: int | None = None) -> dict[str, Any]:
        active = registry or self.executors; pending = self.operations.pending_operations()
        if limit is not None:
            if limit < 0: raise ValueError("limit cannot be negative")
            pending = pending[:limit]
        report: dict[str, Any] = {"attempted": len(pending), "confirmed": [], "deferred": [], "unbound": [], "failed": []}
        for op in pending:
            binding = active.resolve(op.capability_id, op.action)
            if binding is None: report["unbound"].append(op.outbox_seq); continue
            try: result = await self.operations.execute_one(op.outbox_seq, binding.executor)
            except OperationExecutionError as exc:
                report["failed"].append({"outbox_seq": op.outbox_seq, "operation_id": op.id, "executor": binding.name, "error": str(exc)}); continue
            report["confirmed" if result.confirmed else "deferred"].append(op.outbox_seq)
        report["remaining"] = self.operations.outbox.pending_count; return report

    async def execute_registered_pending(self, registry: ProductExecutorRegistry | None = None, *, limit: int | None = None) -> int:
        return len((await self.dispatch_pending(registry, limit=limit))["confirmed"])

    def status(self) -> dict[str, Any]:
        governance = self.policy.snapshot(); ledger = self.execution_ledger(); counts: dict[str, int] = {}; anomalies = 0
        for item in ledger: counts[item["state"]] = counts.get(item["state"], 0) + 1; anomalies += len(item.get("anomalies", ()))
        readiness = self.readiness_report(); assurance = self.assurance_report(); root = self.system_root(); operations = self._operations_projection()
        return {"policy_version": POLICY_VERSION, "policy_bootstrap_enabled": self.bootstrap_policy,
            "kernel": {"capabilities": [{"id": c.id, "pillar": c.pillar.value, "critical": c.critical} for c in self.operations.kernel.all()], "critical_ids": list(self.operations.kernel.critical_ids())},
            "governance": {"charters": [asdict(x) for x in governance.charters], "edicts": [asdict(x) for x in governance.edicts]},
            "executors": {"bound": len(self.executors), "bindings": list(self.executors.snapshot()), "coverage": self.executor_coverage()},
            "readiness": readiness, "receipts": self.receipts.stats(), "curiosity": self.curiosity.stats(),
            "lifecycle": {"operations": len(ledger), "states": counts, "evidence_gaps": counts.get("evidence_gap", 0) + counts.get("receipt_unattested", 0), "anomalies": anomalies},
            "assurance": assurance, "system_root": root, "safety": self._safety_projection(), "operations": operations}
