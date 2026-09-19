"""Durable AI execution-attempt ledger and boundary tracking tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttempt,
    AIExecutionAttemptStore,
    AttemptTrackingExecutionBackend,
    ExecutionAttemptConflict,
    ExecutionAttemptRecovery,
    ExecutionAttemptSessionHead,
    ExecutionAttemptState,
)
from skeleton.shells.ai.execution_backend import AIPlanExecutionBackend
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.execution_plan import ExecutionPlan, PlanStep
from skeleton.shells.plan_executor import (
    PlanExecutionReport,
    StepExecution,
    StepState,
)
from skeleton.shells.runner import ShellCommand


def fp(char: str) -> str:
    return hashlib.sha256(char.encode()).hexdigest()


def plan(*, plan_id: str = "plan") -> ExecutionPlan:
    return ExecutionPlan(
        plan_id,
        (
            PlanStep(
                "step",
                ShellCommand(
                    "python",
                    ("-V",),
                    timeout=2,
                ),
            ),
        ),
    )


def report(item_plan: ExecutionPlan, *, ok: bool = True) -> PlanExecutionReport:
    return PlanExecutionReport(
        item_plan.plan_id,
        item_plan.fingerprint,
        (
            StepExecution(
                "step",
                StepState.SUCCEEDED if ok else StepState.FAILED,
                None,
                "",
                1.0,
                2.0,
            ),
        ),
        1.0,
        2.0,
    )


class FakeBinding:
    def __init__(self, digest: str = fp("b")) -> None:
        self.digest = digest


class FakeBackend:
    def __init__(
        self,
        *,
        backend_id: str = "fake",
        raises: BaseException | None = None,
        item_binding=None,
    ) -> None:
        self._backend_id = backend_id
        self.raises = raises
        self.calls = []
        self.root = fp("r")
        self.binding = item_binding

    @property
    def backend_id(self) -> str:
        return self._backend_id

    def execute_plan(self, item_plan, *, context):
        self.calls.append((item_plan, context))
        if self.raises is not None:
            raise self.raises
        return report(item_plan)

    def receipt_root(self) -> str:
        return self.root


def reserve(
    store: AIExecutionAttemptStore,
    *,
    attempt_id: str = "seal-1",
    session_id: str = "session",
    principal: str = "alice",
    worker_id: str = "worker-1",
    item_plan: ExecutionPlan | None = None,
    execution_seal_id: str = "seal-1",
    execution_fence_digest: str = "",
    fencing_token: int | None = None,
    runtime_trust_digest: str = fp("t"),
    release_evidence_digest: str = fp("r"),
    execution_backend_id: str = "fake",
):
    item_plan = item_plan or plan()
    return store.reserve(
        attempt_id=attempt_id,
        session_id=session_id,
        principal=principal,
        worker_id=worker_id,
        plan_fingerprint=item_plan.fingerprint,
        execution_seal_id=execution_seal_id,
        execution_fence_digest=execution_fence_digest,
        fencing_token=fencing_token,
        runtime_trust_digest=runtime_trust_digest,
        release_evidence_digest=release_evidence_digest,
        execution_backend_id=execution_backend_id,
    )


def test_attempt_reserve_happy_path():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    stored = reserve(store)
    assert stored.revision == 1
    assert stored.attempt.state is ExecutionAttemptState.AUTHORIZED
    assert stored.attempt.recovery is ExecutionAttemptRecovery.NOT_STARTED
    assert len(stored.attempt.authority_digest) == 64


def test_attempt_reserve_same_authority_is_idempotent():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    first = reserve(store)
    second = reserve(store)
    assert second.revision == first.revision
    assert second.attempt == first.attempt


@pytest.mark.parametrize(
    "change",
    [
        {"session_id": "other"},
        {"principal": "bob"},
        {"worker_id": "worker-2"},
        {"execution_seal_id": "seal-2"},
        {"runtime_trust_digest": fp("x")},
        {"release_evidence_digest": fp("x")},
        {"execution_backend_id": "other"},
    ],
)
def test_attempt_id_cannot_be_rebound(change):
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    reserve(store)
    with pytest.raises(ExecutionAttemptConflict, match="different authority"):
        reserve(store, **change)


def test_attempt_plan_fingerprint_is_authority():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    reserve(store, item_plan=plan(plan_id="one"))
    with pytest.raises(ExecutionAttemptConflict):
        reserve(store, item_plan=plan(plan_id="two"))


def test_attempt_fence_digest_and_token_are_authority():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    reserve(
        store,
        execution_fence_digest=fp("f"),
        fencing_token=7,
    )
    with pytest.raises(ExecutionAttemptConflict):
        reserve(
            store,
            execution_fence_digest=fp("f"),
            fencing_token=8,
        )


def test_attempt_enter_boundary_advances_revision():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    first = reserve(store)
    second = store.enter_boundary(first.attempt)
    assert second.revision == 2
    assert second.attempt.state is ExecutionAttemptState.BOUNDARY_ENTERED
    assert (
        second.attempt.recovery
        is ExecutionAttemptRecovery.REQUIRE_VERIFICATION
    )
    assert second.attempt.authority_digest == first.attempt.authority_digest


def test_attempt_boundary_transition_is_idempotent():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    first = reserve(store)
    second = store.enter_boundary(first.attempt)
    again = store.enter_boundary(second.attempt)
    assert again.revision == second.revision
    assert again.attempt == second.attempt


def test_attempt_success_requires_boundary_entry():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    first = reserve(store)
    with pytest.raises(ExecutionAttemptConflict, match="cannot move"):
        store.succeed(
            first.attempt,
            terminal_evidence_digest=fp("e"),
        )


def test_attempt_success_terminal_state():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    item = store.enter_boundary(reserve(store).attempt)
    done = store.succeed(
        item.attempt,
        terminal_evidence_digest=fp("e"),
    )
    assert done.revision == 3
    assert done.attempt.state is ExecutionAttemptState.SUCCEEDED
    assert done.attempt.terminal
    assert (
        done.attempt.recovery
        is ExecutionAttemptRecovery.TERMINAL_SUCCESS
    )
    assert done.attempt.terminal_evidence_digest == fp("e")


def test_attempt_success_is_idempotent_for_same_evidence():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    item = store.enter_boundary(reserve(store).attempt)
    done = store.succeed(
        item.attempt,
        terminal_evidence_digest=fp("e"),
    )
    again = store.succeed(
        done.attempt,
        terminal_evidence_digest=fp("e"),
    )
    assert again.revision == done.revision
    assert again.attempt == done.attempt


def test_attempt_success_cannot_change_terminal_evidence():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    item = store.enter_boundary(reserve(store).attempt)
    done = store.succeed(
        item.attempt,
        terminal_evidence_digest=fp("e"),
    )
    with pytest.raises(ExecutionAttemptConflict, match="terminal state differs"):
        store.succeed(
            done.attempt,
            terminal_evidence_digest=fp("x"),
        )


def test_attempt_failed_terminal_state():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    item = store.enter_boundary(reserve(store).attempt)
    failed = store.fail(
        item.attempt,
        error_type="RuntimeError",
        terminal_evidence_digest=fp("e"),
    )
    assert failed.attempt.state is ExecutionAttemptState.FAILED
    assert failed.attempt.error_type == "RuntimeError"
    assert failed.attempt.terminal_evidence_digest == fp("e")
    assert (
        failed.attempt.recovery
        is ExecutionAttemptRecovery.TERMINAL_FAILURE
    )


def test_attempt_failed_without_terminal_digest_is_supported():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    item = store.enter_boundary(reserve(store).attempt)
    failed = store.fail(
        item.attempt,
        error_type="BackendCrashed",
    )
    assert failed.attempt.state is ExecutionAttemptState.FAILED
    assert failed.attempt.terminal_evidence_digest == ""


def test_attempt_failure_requires_error_type():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    item = store.enter_boundary(reserve(store).attempt)
    with pytest.raises(ValueError, match="error_type"):
        store.fail(item.attempt, error_type="")


def test_attempt_abandon_only_before_boundary():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    item = reserve(store)
    abandoned = store.abandon(item.attempt)
    assert abandoned.attempt.state is ExecutionAttemptState.ABANDONED
    assert abandoned.attempt.recovery is ExecutionAttemptRecovery.ABANDONED


def test_attempt_cannot_abandon_after_boundary():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    item = store.enter_boundary(reserve(store).attempt)
    with pytest.raises(ExecutionAttemptConflict, match="cannot move"):
        store.abandon(item.attempt)


@pytest.mark.parametrize(
    "terminal",
    [
        ExecutionAttemptState.SUCCEEDED,
        ExecutionAttemptState.FAILED,
        ExecutionAttemptState.ABANDONED,
    ],
)
def test_terminal_attempt_cannot_reenter_boundary(terminal):
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    item = reserve(store)
    if terminal is ExecutionAttemptState.ABANDONED:
        item = store.abandon(item.attempt)
    else:
        item = store.enter_boundary(item.attempt)
        if terminal is ExecutionAttemptState.SUCCEEDED:
            item = store.succeed(
                item.attempt,
                terminal_evidence_digest=fp("e"),
            )
        else:
            item = store.fail(
                item.attempt,
                error_type="Failure",
            )
    with pytest.raises(ExecutionAttemptConflict):
        store.enter_boundary(item.attempt)


def test_attempt_current_survives_store_reconstruction():
    backend = InMemoryFencedStore()
    first = AIExecutionAttemptStore(backend)
    original = reserve(first)
    second = AIExecutionAttemptStore(backend)
    current = second.current(original.attempt.attempt_id)
    assert current == original


def test_attempt_missing_recovery_rejected():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    with pytest.raises(ExecutionAttemptConflict, match="missing"):
        store.require_recovery("missing")


@pytest.mark.parametrize(
    "state,recovery",
    [
        (
            ExecutionAttemptState.AUTHORIZED,
            ExecutionAttemptRecovery.NOT_STARTED,
        ),
        (
            ExecutionAttemptState.BOUNDARY_ENTERED,
            ExecutionAttemptRecovery.REQUIRE_VERIFICATION,
        ),
        (
            ExecutionAttemptState.SUCCEEDED,
            ExecutionAttemptRecovery.TERMINAL_SUCCESS,
        ),
        (
            ExecutionAttemptState.FAILED,
            ExecutionAttemptRecovery.TERMINAL_FAILURE,
        ),
        (
            ExecutionAttemptState.ABANDONED,
            ExecutionAttemptRecovery.ABANDONED,
        ),
    ],
)
def test_attempt_recovery_mapping(state, recovery):
    base = AIExecutionAttempt(
        1,
        "a",
        "s",
        "p",
        "w",
        fp("p"),
        "seal",
        state,
        1.0,
        1.0,
        terminal_evidence_digest=(
            fp("e") if state is ExecutionAttemptState.SUCCEEDED else ""
        ),
        error_type=(
            "Failure" if state is ExecutionAttemptState.FAILED else ""
        ),
    )
    assert base.recovery is recovery


def test_attempt_authority_digest_excludes_state_and_timestamps():
    base = AIExecutionAttempt(
        1,
        "a",
        "s",
        "p",
        "w",
        fp("p"),
        "seal",
        ExecutionAttemptState.AUTHORIZED,
        1.0,
        1.0,
    )
    boundary = replace(
        base,
        state=ExecutionAttemptState.BOUNDARY_ENTERED,
        updated_at=2.0,
    )
    assert base.authority_digest == boundary.authority_digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("principal", "other"),
        ("worker_id", "other"),
        ("plan_fingerprint", fp("x")),
        ("execution_seal_id", "other"),
        ("runtime_trust_digest", fp("x")),
        ("release_evidence_digest", fp("x")),
        ("execution_backend_id", "other"),
    ],
)
def test_attempt_authority_digest_changes_with_authority_field(field, value):
    base = AIExecutionAttempt(
        1,
        "a",
        "s",
        "p",
        "w",
        fp("p"),
        "seal",
        ExecutionAttemptState.AUTHORIZED,
        1.0,
        1.0,
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
        execution_backend_id="backend",
    )
    changed = replace(base, **{field: value})
    assert base.authority_digest != changed.authority_digest


def test_attempt_authority_digest_changes_with_fencing_token():
    first = AIExecutionAttempt(
        1,
        "a",
        "s",
        "p",
        "w",
        fp("p"),
        "seal",
        ExecutionAttemptState.AUTHORIZED,
        1.0,
        1.0,
        execution_fence_digest=fp("f"),
        fencing_token=1,
    )
    second = replace(first, fencing_token=2)
    assert first.authority_digest != second.authority_digest


@pytest.mark.parametrize(
    "kwargs",
    [
        {"schema_version": 2},
        {"attempt_id": ""},
        {"session_id": ""},
        {"principal": ""},
        {"worker_id": ""},
        {"plan_fingerprint": "bad"},
        {"execution_seal_id": ""},
        {"runtime_trust_digest": "bad"},
        {"release_evidence_digest": "bad"},
        {"terminal_evidence_digest": "bad"},
        {"created_at": -1},
        {"updated_at": -1},
    ],
)
def test_attempt_dataclass_validation(kwargs):
    values = dict(
        schema_version=1,
        attempt_id="a",
        session_id="s",
        principal="p",
        worker_id="w",
        plan_fingerprint=fp("p"),
        execution_seal_id="seal",
        state=ExecutionAttemptState.AUTHORIZED,
        created_at=1.0,
        updated_at=1.0,
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        AIExecutionAttempt(**values)


def test_attempt_rejects_update_before_creation():
    with pytest.raises(ValueError, match="precedes"):
        AIExecutionAttempt(
            1,
            "a",
            "s",
            "p",
            "w",
            fp("p"),
            "seal",
            ExecutionAttemptState.AUTHORIZED,
            2.0,
            1.0,
        )


@pytest.mark.parametrize("token", [0, -1, True])
def test_attempt_fencing_token_validation(token):
    with pytest.raises(ValueError, match="fencing_token"):
        AIExecutionAttempt(
            1,
            "a",
            "s",
            "p",
            "w",
            fp("p"),
            "seal",
            ExecutionAttemptState.AUTHORIZED,
            1.0,
            1.0,
            execution_fence_digest=fp("f"),
            fencing_token=token,
        )


def test_attempt_fence_digest_requires_token():
    with pytest.raises(ValueError, match="configured together"):
        AIExecutionAttempt(
            1,
            "a",
            "s",
            "p",
            "w",
            fp("p"),
            "seal",
            ExecutionAttemptState.AUTHORIZED,
            1.0,
            1.0,
            execution_fence_digest=fp("f"),
        )


def test_attempt_token_requires_fence_digest():
    with pytest.raises(ValueError, match="configured together"):
        AIExecutionAttempt(
            1,
            "a",
            "s",
            "p",
            "w",
            fp("p"),
            "seal",
            ExecutionAttemptState.AUTHORIZED,
            1.0,
            1.0,
            fencing_token=1,
        )


def test_success_state_requires_terminal_evidence():
    with pytest.raises(ValueError, match="terminal evidence"):
        AIExecutionAttempt(
            1,
            "a",
            "s",
            "p",
            "w",
            fp("p"),
            "seal",
            ExecutionAttemptState.SUCCEEDED,
            1.0,
            1.0,
        )


def test_failed_state_requires_error_type():
    with pytest.raises(ValueError, match="error_type"):
        AIExecutionAttempt(
            1,
            "a",
            "s",
            "p",
            "w",
            fp("p"),
            "seal",
            ExecutionAttemptState.FAILED,
            1.0,
            1.0,
        )


def test_authorized_state_rejects_terminal_evidence():
    with pytest.raises(ValueError, match="non-terminal"):
        AIExecutionAttempt(
            1,
            "a",
            "s",
            "p",
            "w",
            fp("p"),
            "seal",
            ExecutionAttemptState.AUTHORIZED,
            1.0,
            1.0,
            terminal_evidence_digest=fp("e"),
        )


def test_attempt_store_rejects_invalid_namespace():
    with pytest.raises(ValueError, match="namespace"):
        AIExecutionAttemptStore(
            InMemoryFencedStore(),
            namespace="",
        )


@pytest.mark.parametrize("retries", [0, 65, True])
def test_attempt_store_retry_bound_validation(retries):
    with pytest.raises(ValueError, match="max_retries"):
        AIExecutionAttemptStore(
            InMemoryFencedStore(),
            max_retries=retries,
        )


class ConflictOnceBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()
        self.conflicted = False

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
        return self.store.put_if_absent(namespace, key, value)

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if not self.conflicted:
            self.conflicted = True
            raise DistributedStateConflict("synthetic race")
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )

    def delete(self, namespace, key, *, expected_revision):
        return self.store.delete(
            namespace,
            key,
            expected_revision=expected_revision,
        )


def test_attempt_transition_retries_one_cas_conflict():
    store = AIExecutionAttemptStore(ConflictOnceBackend())
    first = reserve(store)
    boundary = store.enter_boundary(first.attempt)
    assert boundary.attempt.state is ExecutionAttemptState.BOUNDARY_ENTERED
    assert boundary.revision == 2


def test_attempt_transition_rejects_stale_authority_object():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    first = reserve(store)
    boundary = store.enter_boundary(first.attempt)
    stale = replace(first.attempt, principal="mallory")
    with pytest.raises(ExecutionAttemptConflict, match="authority"):
        store.succeed(
            stale,
            terminal_evidence_digest=fp("e"),
        )
    assert store.current(first.attempt.attempt_id) == boundary


def test_tracking_backend_satisfies_backend_protocol():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    attempt = reserve(store).attempt
    backend = AttemptTrackingExecutionBackend(
        store,
        attempt,
        FakeBackend(),
    )
    assert isinstance(backend, AIPlanExecutionBackend)


def test_tracking_backend_enters_boundary_before_delegate_call():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    attempt = reserve(store).attempt

    class InspectingBackend(FakeBackend):
        def execute_plan(self, item_plan, *, context):
            current = store.current(attempt.attempt_id)
            assert (
                current.attempt.state
                is ExecutionAttemptState.BOUNDARY_ENTERED
            )
            return super().execute_plan(item_plan, context=context)

    delegate = InspectingBackend()
    backend = AttemptTrackingExecutionBackend(store, attempt, delegate)
    result = backend.execute_plan(
        plan(),
        context=ExecutionContext("c", principal="alice"),
    )
    assert result.ok
    assert backend.boundary_entered
    assert backend.attempt.state is ExecutionAttemptState.BOUNDARY_ENTERED
    assert len(delegate.calls) == 1


def test_tracking_backend_crash_leaves_boundary_visible():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    attempt = reserve(store).attempt
    backend = AttemptTrackingExecutionBackend(
        store,
        attempt,
        FakeBackend(raises=RuntimeError("crash")),
    )
    with pytest.raises(RuntimeError, match="crash"):
        backend.execute_plan(
            plan(),
            context=ExecutionContext("c", principal="alice"),
        )
    current = store.current(attempt.attempt_id)
    assert current.attempt.state is ExecutionAttemptState.BOUNDARY_ENTERED
    assert (
        current.attempt.recovery
        is ExecutionAttemptRecovery.REQUIRE_VERIFICATION
    )


def test_tracking_backend_refuses_second_boundary_crossing():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    attempt = reserve(store).attempt
    backend = AttemptTrackingExecutionBackend(
        store,
        attempt,
        FakeBackend(),
    )
    backend.execute_plan(
        plan(),
        context=ExecutionContext("c", principal="alice"),
    )
    with pytest.raises(ExecutionAttemptConflict, match="only once"):
        backend.execute_plan(
            plan(),
            context=ExecutionContext("c", principal="alice"),
        )


def test_tracking_backend_preserves_delegate_identity_and_receipt_root():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    attempt = reserve(store).attempt
    delegate = FakeBackend(backend_id="sandbox:one")
    backend = AttemptTrackingExecutionBackend(store, attempt, delegate)
    assert backend.backend_id == "sandbox:one"
    assert backend.assurance_backend is delegate
    assert backend.receipt_root() == fp("r")


def test_tracking_backend_preserves_optional_sandbox_binding():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    attempt = reserve(store).attempt
    binding = FakeBinding()
    delegate = FakeBackend(item_binding=binding)
    backend = AttemptTrackingExecutionBackend(store, attempt, delegate)
    assert backend.binding is binding
    assert backend.binding.digest == fp("b")


def test_tracking_backend_without_delegate_binding_returns_none():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    attempt = reserve(store).attempt
    delegate = FakeBackend()
    del delegate.binding
    backend = AttemptTrackingExecutionBackend(store, attempt, delegate)
    assert backend.binding is None


def test_tracking_backend_requires_authorized_attempt():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    attempt = store.enter_boundary(reserve(store).attempt).attempt
    with pytest.raises(ValueError, match="authorized"):
        AttemptTrackingExecutionBackend(
            store,
            attempt,
            FakeBackend(),
        )


def test_attempt_to_dict_is_json_shaped():
    attempt = reserve(
        AIExecutionAttemptStore(InMemoryFencedStore()),
        execution_fence_digest=fp("f"),
        fencing_token=3,
    ).attempt
    data = attempt.to_dict()
    assert data["state"] == "authorized"
    assert data["recovery"] == "not_started"
    assert data["fencing_token"] == 3
    assert data["authority_digest"] == attempt.authority_digest


def test_stored_attempt_to_dict_includes_revision():
    stored = reserve(AIExecutionAttemptStore(InMemoryFencedStore()))
    data = stored.to_dict()
    assert data["revision"] == 1
    assert data["attempt"]["attempt_id"] == "seal-1"


def test_attempt_reserve_creates_session_head():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    stored = reserve(store)
    head = store.session_head(stored.attempt.session_id)
    assert head is not None
    assert head.session_id == stored.attempt.session_id
    assert head.attempt_id == stored.attempt.attempt_id
    assert head.authority_digest == stored.attempt.authority_digest


def test_attempt_current_for_session_resolves_canonical_attempt():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    stored = reserve(store)
    current = store.current_for_session(stored.attempt.session_id)
    assert current == stored


def test_attempt_current_for_unknown_session_is_none():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    assert store.current_for_session("missing") is None
    assert store.session_head("missing") is None


def test_attempt_session_head_survives_store_reconstruction():
    backend = InMemoryFencedStore()
    first = AIExecutionAttemptStore(backend)
    stored = reserve(first)
    second = AIExecutionAttemptStore(backend)
    assert second.current_for_session("session") == stored
    assert second.session_head("session").authority_digest == (
        stored.attempt.authority_digest
    )


def test_attempt_identical_reserve_keeps_same_session_head():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    first = reserve(store)
    head_before = store.session_head("session")
    second = reserve(store)
    head_after = store.session_head("session")
    assert second == first
    assert head_after == head_before


def test_attempt_competing_attempt_for_same_session_is_rejected_and_abandoned():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    winner = reserve(
        store,
        attempt_id="winner",
        execution_seal_id="winner",
    )
    with pytest.raises(
        ExecutionAttemptConflict,
        match="session already binds",
    ):
        reserve(
            store,
            attempt_id="loser",
            execution_seal_id="loser",
        )
    assert store.current_for_session("session") == winner
    loser = store.current("loser")
    assert loser is not None
    assert loser.attempt.state is ExecutionAttemptState.ABANDONED
    assert loser.attempt.recovery is ExecutionAttemptRecovery.ABANDONED


def test_attempt_different_sessions_can_reserve_independently():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    first = reserve(
        store,
        attempt_id="one",
        execution_seal_id="one",
        session_id="session-one",
    )
    second = reserve(
        store,
        attempt_id="two",
        execution_seal_id="two",
        session_id="session-two",
    )
    assert store.current_for_session("session-one") == first
    assert store.current_for_session("session-two") == second


def test_attempt_session_head_authority_tamper_is_detected():
    backend = InMemoryFencedStore()
    store = AIExecutionAttemptStore(backend)
    stored = reserve(store)
    key = store.session_key("session")
    record = backend.get(store.namespace, key)
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=ExecutionAttemptSessionHead(
            "session",
            stored.attempt.attempt_id,
            fp("x"),
        ),
    )
    with pytest.raises(
        ExecutionAttemptConflict,
        match="authority mismatch",
    ):
        store.current_for_session("session")


def test_attempt_session_head_missing_attempt_is_detected():
    backend = InMemoryFencedStore()
    store = AIExecutionAttemptStore(backend)
    stored = reserve(store)
    attempt_key = store.key(stored.attempt.attempt_id)
    record = backend.get(store.namespace, attempt_key)
    backend.delete(
        store.namespace,
        attempt_key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        ExecutionAttemptConflict,
        match="missing attempt",
    ):
        store.current_for_session("session")


def test_attempt_session_head_wrong_session_is_detected():
    backend = InMemoryFencedStore()
    store = AIExecutionAttemptStore(backend)
    stored = reserve(store)
    key = store.session_key("session")
    record = backend.get(store.namespace, key)
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=ExecutionAttemptSessionHead(
            "other-session",
            stored.attempt.attempt_id,
            stored.attempt.authority_digest,
        ),
    )
    with pytest.raises(RuntimeError, match="identity mismatch"):
        store.session_head("session")


def test_attempt_session_head_wrong_type_is_detected():
    backend = InMemoryFencedStore()
    store = AIExecutionAttemptStore(backend)
    reserve(store)
    key = store.session_key("session")
    record = backend.get(store.namespace, key)
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value={"bad": "head"},
    )
    with pytest.raises(RuntimeError, match="type mismatch"):
        store.session_head("session")


def test_attempt_session_head_to_dict():
    head = ExecutionAttemptSessionHead(
        "session",
        "attempt",
        fp("a"),
    )
    assert head.to_dict() == {
        "session_id": "session",
        "attempt_id": "attempt",
        "authority_digest": fp("a"),
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"session_id": ""},
        {"attempt_id": ""},
        {"authority_digest": "bad"},
        {"session_id": "x" * 257},
        {"attempt_id": "x" * 257},
    ],
)
def test_attempt_session_head_validation(kwargs):
    values = {
        "session_id": "session",
        "attempt_id": "attempt",
        "authority_digest": fp("a"),
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        ExecutionAttemptSessionHead(**values)


def test_attempt_session_key_is_stable_and_distinct():
    assert (
        AIExecutionAttemptStore.session_key("session")
        == AIExecutionAttemptStore.session_key("session")
    )
    assert (
        AIExecutionAttemptStore.session_key("session-a")
        != AIExecutionAttemptStore.session_key("session-b")
    )
    assert AIExecutionAttemptStore.session_key("session").startswith(
        "session:"
    )


@pytest.mark.parametrize("session_id", ["", "x" * 257])
def test_attempt_session_key_validation(session_id):
    with pytest.raises(ValueError, match="session_id"):
        AIExecutionAttemptStore.session_key(session_id)


def test_attempt_session_head_prevents_second_worker_authority_for_same_session():
    backend = InMemoryFencedStore()
    worker_one = AIExecutionAttemptStore(backend)
    worker_two = AIExecutionAttemptStore(backend)
    first = reserve(
        worker_one,
        attempt_id="worker-one-seal",
        execution_seal_id="worker-one-seal",
        worker_id="worker-one",
    )
    with pytest.raises(ExecutionAttemptConflict):
        reserve(
            worker_two,
            attempt_id="worker-two-seal",
            execution_seal_id="worker-two-seal",
            worker_id="worker-two",
        )
    assert worker_two.current_for_session("session") == first


def test_attempt_session_head_remains_after_terminal_success():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    stored = reserve(store)
    boundary = store.enter_boundary(stored.attempt)
    done = store.succeed(
        boundary.attempt,
        terminal_evidence_digest=fp("e"),
    )
    assert store.current_for_session("session") == done
    assert store.session_head("session").attempt_id == "seal-1"


def test_attempt_session_head_remains_after_abandon():
    store = AIExecutionAttemptStore(InMemoryFencedStore())
    stored = reserve(store)
    abandoned = store.abandon(stored.attempt)
    assert store.current_for_session("session") == abandoned
    assert (
        store.current_for_session("session").attempt.state
        is ExecutionAttemptState.ABANDONED
    )
