"""Verified sandbox execution backend for compiled AI shell plans."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Protocol, runtime_checkable

from skeleton.shells.ai.execution_backend import AIPlanExecutionBackend
from skeleton.shells.ai.sandbox_attestation import (
    SandboxAttestationReport,
    SandboxAttestationVerifier,
    SandboxCapabilities,
)
from skeleton.shells.ai.sandbox_contract import AISandboxContract
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.execution_plan import ExecutionPlan
from skeleton.shells.plan_executor import PlanExecutionReport


@runtime_checkable
class SandboxPlanExecutor(Protocol):
    @property
    def backend_id(self) -> str: ...

    @property
    def capabilities(self) -> SandboxCapabilities: ...

    def execute_plan(
        self,
        plan: ExecutionPlan,
        *,
        context: ExecutionContext,
        contract: AISandboxContract,
    ) -> PlanExecutionReport: ...

    def receipt_root(self) -> str: ...


@dataclass(frozen=True)
class SandboxBinding:
    plan_fingerprint: str
    contract_digest: str
    backend_capability_digest: str

    def __post_init__(self) -> None:
        for name in (
            "plan_fingerprint",
            "contract_digest",
            "backend_capability_digest",
        ):
            if len(getattr(self, name)) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_fingerprint": self.plan_fingerprint,
            "contract_digest": self.contract_digest,
            "backend_capability_digest": self.backend_capability_digest,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


class VerifiedSandboxExecutionBackend:
    """Execute one exact plan only through an attested sandbox executor."""

    def __init__(
        self,
        backend: SandboxPlanExecutor,
        contract: AISandboxContract,
        *,
        plan_fingerprint: str,
        verifier: SandboxAttestationVerifier | None = None,
    ) -> None:
        self.backend = backend
        self.contract = contract
        self.verifier = verifier or SandboxAttestationVerifier()
        report = self.verifier.inspect(contract, backend.capabilities)
        if not report.compatible:
            raise RuntimeError(
                "sandbox backend is incompatible: " + "; ".join(report.reasons)
            )
        self.attestation = report
        self.binding = SandboxBinding(
            plan_fingerprint,
            contract.digest,
            backend.capabilities.digest,
        )

    @property
    def backend_id(self) -> str:
        return f"sandbox:{self.backend.backend_id}"

    def execute_plan(
        self,
        plan: ExecutionPlan,
        *,
        context: ExecutionContext,
    ) -> PlanExecutionReport:
        if plan.fingerprint != self.binding.plan_fingerprint:
            raise RuntimeError("sandbox backend is bound to a different plan")
        current = self.verifier.inspect(
            self.contract,
            self.backend.capabilities,
        )
        if not current.compatible:
            raise RuntimeError(
                "sandbox capabilities drifted: " + "; ".join(current.reasons)
            )
        if self.backend.capabilities.digest != self.binding.backend_capability_digest:
            raise RuntimeError("sandbox capability digest changed after binding")
        if self.contract.digest != self.binding.contract_digest:
            raise RuntimeError("sandbox contract changed after binding")
        return self.backend.execute_plan(
            plan,
            context=context,
            contract=self.contract,
        )

    def receipt_root(self) -> str:
        return self.backend.receipt_root()
