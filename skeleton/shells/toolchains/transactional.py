"""Bridge logical toolchain contracts into workspace mutation transactions.

Every invocation is prepared by ToolchainExecutionPlane and executed exactly
once by WorkspaceTransactionManager using the same compiled ShellExecutor.
Mutation authority is selected from the contract's declared effects and can be
overridden by explicit contract-name routes without widening execution argv or
environment authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.retry import RetryPolicy
from skeleton.shells.session import ShellSession
from skeleton.shells.toolchains.execution import (
    PreparedToolchainInvocation,
    ToolchainExecutionPlane,
    ToolchainInvocation,
)
from skeleton.shells.toolchains.types import CommandEffect, LogicalCommandContract
from skeleton.shells.workspace_txn.policy import (
    WorkspaceMutationPolicy,
    generated_output_policy,
    source_edit_policy,
)
from skeleton.shells.workspace_txn.rules import MaxChangesRule
from skeleton.shells.workspace_txn.transaction import WorkspaceTransactionManager
from skeleton.shells.workspace_txn.types import TransactionResult


class TransactionalToolchainError(ValueError):
    pass


def zero_mutation_policy() -> WorkspaceMutationPolicy:
    """Require a contract invocation to leave the workspace byte-for-byte unchanged."""

    return WorkspaceMutationPolicy(
        rules=(MaxChangesRule(0),),
        name="toolchain-zero-mutation",
        fail_on_warning=True,
        metadata={
            "authority": "toolchain",
            "mutation": "none",
        },
    )


@dataclass(frozen=True)
class ToolchainMutationPolicyRouter:
    """Select filesystem mutation authority from declared command effects."""

    explicit: Mapping[str, WorkspaceMutationPolicy] = None
    read_policy: WorkspaceMutationPolicy | None = None
    source_policy: WorkspaceMutationPolicy | None = None
    generated_policy: WorkspaceMutationPolicy | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "explicit",
            MappingProxyType(dict(self.explicit or {})),
        )
        if self.read_policy is None:
            object.__setattr__(self, "read_policy", zero_mutation_policy())
        if self.source_policy is None:
            object.__setattr__(self, "source_policy", source_edit_policy())
        if self.generated_policy is None:
            object.__setattr__(self, "generated_policy", generated_output_policy())

    def select(
        self,
        contract: LogicalCommandContract,
    ) -> WorkspaceMutationPolicy:
        explicit = self.explicit.get(contract.name)
        if explicit is not None:
            return explicit

        effects = contract.effects
        if CommandEffect.WRITE not in effects:
            assert self.read_policy is not None
            return self.read_policy

        if (
            CommandEffect.BUILD in effects
            or CommandEffect.PACKAGE in effects
            or CommandEffect.CONTAINER in effects
        ):
            assert self.generated_policy is not None
            return self.generated_policy

        assert self.source_policy is not None
        return self.source_policy

    def explain(
        self,
        contract: LogicalCommandContract,
    ) -> dict[str, object]:
        policy = self.select(contract)
        return {
            "contract": contract.name,
            "effects": sorted(effect.value for effect in contract.effects),
            "policy_name": policy.name,
            "policy_digest": policy.digest,
            "explicit": contract.name in self.explicit,
        }


@dataclass(frozen=True)
class TransactionalToolchainResult:
    prepared: PreparedToolchainInvocation
    transaction: TransactionResult
    mutation_policy_name: str
    mutation_policy_digest: str

    @property
    def ok(self) -> bool:
        return self.transaction.accepted

    @property
    def execution_ok(self) -> bool:
        return self.transaction.receipt.execution_ok

    @property
    def policy_allowed(self) -> bool:
        return self.transaction.receipt.policy_allowed

    @property
    def rolled_back(self) -> bool:
        return self.transaction.receipt.rolled_back

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.prepared.contract.name,
            "correlation_id": self.prepared.correlation_id,
            "effects": sorted(
                effect.value for effect in self.prepared.contract.effects
            ),
            "risk": self.prepared.contract.risk.value,
            "mutation_policy_name": self.mutation_policy_name,
            "mutation_policy_digest": self.mutation_policy_digest,
            "transaction": self.transaction.to_dict(),
        }


class TransactionalToolchainExecutionPlane:
    """Execute compiled contracts with observed, reviewable workspace mutation."""

    def __init__(
        self,
        base: ToolchainExecutionPlane,
        transactions: WorkspaceTransactionManager,
        *,
        router: ToolchainMutationPolicyRouter | None = None,
    ) -> None:
        if transactions.executor is not base.compiled.executor:
            raise TransactionalToolchainError(
                "transaction manager must use the compiled toolchain executor"
            )
        self.base = base
        self.transactions = transactions
        self.router = router or ToolchainMutationPolicyRouter()

    def prepare(
        self,
        invocation: ToolchainInvocation,
    ) -> PreparedToolchainInvocation:
        return self.base.prepare(invocation)

    def execute(
        self,
        invocation: ToolchainInvocation,
        *,
        retry: RetryPolicy | None = None,
        session: ShellSession | None = None,
        principal: str = "toolchain-transaction",
    ) -> TransactionalToolchainResult:
        prepared = self.prepare(invocation)
        policy = self.router.select(prepared.contract)
        result = self.transactions.execute(
            prepared.command.cwd or self.base.compiled.roots[0],
            prepared.command,
            principal=principal,
            correlation_id=prepared.correlation_id,
            retry=retry,
            session=session,
            metadata={
                "toolchain_contract": prepared.contract.name,
                "toolchain_executable_key": prepared.contract.executable_key,
                "toolchain_risk": prepared.contract.risk.value,
                "toolchain_effects": ",".join(
                    sorted(effect.value for effect in prepared.contract.effects)
                ),
                "mutation_policy": policy.name,
            },
            policy=policy,
        )
        return TransactionalToolchainResult(
            prepared=prepared,
            transaction=result,
            mutation_policy_name=policy.name,
            mutation_policy_digest=policy.digest,
        )

    def explain(self, contract_name: str) -> dict[str, object]:
        contract = self.base.compiled.get(contract_name)
        base = self.base.explain(contract_name)
        base["transaction"] = self.router.explain(contract)
        return base

    def names(self) -> tuple[str, ...]:
        return self.base.names()
