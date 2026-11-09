"""Host and verified sandbox execution backend tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.execution_backend import (
    AIPlanExecutionBackend,
    ShellServiceExecutionBackend,
)
from skeleton.shells.ai.isolation_compiler import AIIsolationDecision
from skeleton.shells.ai.resource_profile import (
    AIResourceDecision,
    AIResourceProfile,
)
from skeleton.shells.ai.sandbox_attestation import SandboxCapabilities
from skeleton.shells.ai.sandbox_backend import (
    SandboxPlanExecutor,
    VerifiedSandboxExecutionBackend,
)
from skeleton.shells.ai.sandbox_contract import AISandboxContract
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.execution_plan import ExecutionPlan, PlanStep
from skeleton.shells.isolation import IsolationLevel, IsolationRequirement
from skeleton.shells.plan_executor import PlanExecutionReport, StepExecution, StepState
from skeleton.shells.runner import ShellCommand


def plan(arg="-V"):
    return ExecutionPlan(
        "plan",
        (
            PlanStep(
                "step",
                ShellCommand("python", (arg,)),
            ),
        ),
    )


def resource_profile():
    return AIResourceProfile(
        wall_seconds=10,
        cpu_seconds=5,
        memory_bytes=1024 * 1024,
        process_count=4,
        file_bytes=1024 * 1024,
        open_files=64,
        output_bytes=1024,
    )


def contract():
    profile = resource_profile()
    isolation = AIIsolationDecision(
        IsolationRequirement(
            level=IsolationLevel.SANDBOXED,
            require_private_tmp=True,
            require_clean_environment=True,
            require_readonly_source=True,
            allow_network=False,
            allow_home=False,
        ),
        (),
        ("test contract",),
    )
    resources = AIResourceDecision(
        profile,
        profile,
        ("test profile",),
    )
    return AISandboxContract(
        isolation,
        resources,
        require_process_group=True,
        require_no_new_privileges=True,
        require_syscall_filter=True,
        require_network_namespace=True,
    )


def capabilities(**changes):
    values = dict(
        backend_id="sandbox",
        backend_version="1",
        max_level=IsolationLevel.SANDBOXED,
        private_tmp=True,
        clean_environment=True,
        readonly_source=True,
        network_namespace=True,
        home_hiding=True,
        process_group=True,
        no_new_privileges=True,
        syscall_filter=True,
        resource_limits=True,
        max_profile=AIResourceProfile(
            wall_seconds=20,
            cpu_seconds=10,
            memory_bytes=2 * 1024 * 1024,
            process_count=8,
            file_bytes=2 * 1024 * 1024,
            open_files=128,
            output_bytes=2048,
        ),
    )
    values.update(changes)
    return SandboxCapabilities(**values)


def report(item_plan):
    return PlanExecutionReport(
        item_plan.plan_id,
        item_plan.fingerprint,
        (
            StepExecution(
                "step",
                StepState.SUCCEEDED,
                None,
                "",
                1.0,
                2.0,
            ),
        ),
        1.0,
        2.0,
    )


class FakeSandbox:
    def __init__(self, caps=None):
        self._capabilities = caps or capabilities()
        self.calls = []
        self.root = "a" * 64

    @property
    def backend_id(self):
        return "fake-sandbox"

    @property
    def capabilities(self):
        return self._capabilities

    def execute_plan(self, item_plan, *, context, contract):
        self.calls.append((item_plan, context, contract))
        return report(item_plan)

    def receipt_root(self):
        return self.root


def test_fake_sandbox_satisfies_protocol():
    assert isinstance(FakeSandbox(), SandboxPlanExecutor)


def test_verified_sandbox_satisfies_ai_backend_protocol():
    item_plan = plan()
    backend = VerifiedSandboxExecutionBackend(
        FakeSandbox(),
        contract(),
        plan_fingerprint=item_plan.fingerprint,
    )
    assert isinstance(backend, AIPlanExecutionBackend)
    assert backend.backend_id == "sandbox:fake-sandbox"


def test_verified_sandbox_executes_bound_plan():
    item_plan = plan()
    fake = FakeSandbox()
    backend = VerifiedSandboxExecutionBackend(
        fake,
        contract(),
        plan_fingerprint=item_plan.fingerprint,
    )
    context = ExecutionContext("c", principal="alice")
    result = backend.execute_plan(item_plan, context=context)
    assert result.ok
    assert fake.calls[0][0] == item_plan
    assert fake.calls[0][1] == context
    assert fake.calls[0][2] == contract()
    assert backend.receipt_root() == "a" * 64


def test_verified_sandbox_rejects_different_plan():
    first = plan("-V")
    second = plan("--help")
    backend = VerifiedSandboxExecutionBackend(
        FakeSandbox(),
        contract(),
        plan_fingerprint=first.fingerprint,
    )
    with pytest.raises(RuntimeError, match="different plan"):
        backend.execute_plan(
            second,
            context=ExecutionContext("c"),
        )


@pytest.mark.parametrize(
    "field,phrase",
    [
        ("syscall_filter", "syscall"),
        ("no_new_privileges", "no-new"),
        ("network_namespace", "network"),
        ("resource_limits", "resource"),
    ],
)
def test_verified_sandbox_rejects_missing_capability_at_binding(field, phrase):
    fake = FakeSandbox(capabilities(**{field: False}))
    with pytest.raises(RuntimeError, match="incompatible"):
        VerifiedSandboxExecutionBackend(
            fake,
            contract(),
            plan_fingerprint=plan().fingerprint,
        )


def test_verified_sandbox_detects_capability_digest_drift():
    item_plan = plan()
    fake = FakeSandbox()
    backend = VerifiedSandboxExecutionBackend(
        fake,
        contract(),
        plan_fingerprint=item_plan.fingerprint,
    )
    fake._capabilities = capabilities(backend_version="2")
    with pytest.raises(RuntimeError, match="digest changed"):
        backend.execute_plan(
            item_plan,
            context=ExecutionContext("c"),
        )


def test_verified_sandbox_detects_capability_becoming_incompatible():
    item_plan = plan()
    fake = FakeSandbox()
    backend = VerifiedSandboxExecutionBackend(
        fake,
        contract(),
        plan_fingerprint=item_plan.fingerprint,
    )
    fake._capabilities = capabilities(syscall_filter=False)
    with pytest.raises(RuntimeError, match="capabilities drifted"):
        backend.execute_plan(
            item_plan,
            context=ExecutionContext("c"),
        )


def test_verified_sandbox_binding_contains_exact_digests():
    item_plan = plan()
    fake = FakeSandbox()
    item_contract = contract()
    backend = VerifiedSandboxExecutionBackend(
        fake,
        item_contract,
        plan_fingerprint=item_plan.fingerprint,
    )
    assert backend.binding.plan_fingerprint == item_plan.fingerprint
    assert backend.binding.contract_digest == item_contract.digest
    assert backend.binding.backend_capability_digest == fake.capabilities.digest


class FakeShellService:
    def __init__(self):
        self.calls = []

        class Receipts:
            def root_hash(inner):
                return "b" * 64

        self.receipts = Receipts()

    def execute_plan(self, item_plan, *, context):
        self.calls.append((item_plan, context))
        return report(item_plan)


def test_shell_service_execution_backend_delegates_plan_only():
    service = FakeShellService()
    backend = ShellServiceExecutionBackend(service)
    item_plan = plan()
    context = ExecutionContext("c")
    result = backend.execute_plan(item_plan, context=context)
    assert result.ok
    assert service.calls == [(item_plan, context)]
    assert backend.receipt_root() == "b" * 64
    assert backend.backend_id == "shell-service-host"


def test_sandbox_contract_must_fit_resource_capabilities():
    tiny = resource_profile()
    constrained = capabilities(
        max_profile=AIResourceProfile(
            wall_seconds=1,
            cpu_seconds=1,
            memory_bytes=1,
            process_count=1,
            file_bytes=1,
            open_files=1,
            output_bytes=1,
        )
    )
    with pytest.raises(RuntimeError, match="resource"):
        VerifiedSandboxExecutionBackend(
            FakeSandbox(constrained),
            contract(),
            plan_fingerprint=plan().fingerprint,
        )
