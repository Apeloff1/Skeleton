"""Regression coverage for transactional creator previews (#807 B015)."""

from __future__ import annotations

from dataclasses import replace
import ast
import json
import math
from pathlib import Path

import pytest

from skeleton.forge.creator.intent_compiler import (
    EDIT_SCHEMA,
    compile_intent,
)
from skeleton.forge.creator.preview_transaction import (
    EXECUTION_PHASES,
    PREVIEW_PHASES,
    PREVIEW_SCHEMA,
    PREVIEW_VERSION,
    PreviewRollbackError,
    PreviewStepResult,
    PreviewTransactionError,
    execute_preview_transaction,
    make_preview_step_result,
    serialize_preview_outcome,
    serialize_preview_transaction,
    stage_preview_transaction,
    validate_prepared_preview,
    validate_preview_outcome,
    validate_preview_step_result,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "intent_compiler"
MODULE_PATH = Path(__file__).resolve().parents[1] / "forge" / "creator" / "preview_transaction.py"


def _request() -> dict[str, object]:
    return json.loads(
        (FIXTURES / "harbor_heist_v1.json").read_text(encoding="utf-8")
    )


def _plan():
    return compile_intent(_request())


def _edit(
    *,
    edit_id: str = "e_preview_title",
    value: str = "Preview stealth loop",
) -> dict[str, object]:
    return {
        "schema": EDIT_SCHEMA,
        "schema_version": 1,
        "edit_id": edit_id,
        "op": "set_field",
        "node_id": "n_stealth",
        "field": "title",
        "value": value,
    }


class FakeBackend:
    def __init__(
        self,
        *,
        fail_phase: str | None = None,
        raise_phase: str | None = None,
        wrong_phase: str | None = None,
        rollback_ok: bool = True,
        rollback_raise: bool = False,
        rollback_wrong_phase: bool = False,
    ) -> None:
        self.fail_phase = fail_phase
        self.raise_phase = raise_phase
        self.wrong_phase = wrong_phase
        self.rollback_ok = rollback_ok
        self.rollback_raise = rollback_raise
        self.rollback_wrong_phase = rollback_wrong_phase
        self.calls: list[str] = []
        self.applied_state_digest: str | None = None
        self.rollback_context: tuple[str, str] | None = None

    def _result(self, phase: str, **extra: object) -> PreviewStepResult:
        if self.raise_phase == phase:
            raise RuntimeError(f"{phase} backend explosion")
        result_phase = (
            "begin"
            if self.wrong_phase == phase and phase != "begin"
            else "compile"
            if self.wrong_phase == phase
            else phase
        )
        return make_preview_step_result(
            result_phase,
            ok=phase != self.fail_phase,
            evidence={"phase": phase, **extra},
            diagnostics=(f"{phase} evidence",),
        )

    def begin(self, transaction):
        self.calls.append("begin")
        return self._result("begin", transaction=transaction.digest)

    def apply(self, transaction, staged_plan):
        self.calls.append("apply")
        self.applied_state_digest = transaction.staged_state_digest
        return self._result(
            "apply",
            transaction=transaction.digest,
            staged_revision=staged_plan.revision,
        )

    def compile(self, transaction):
        self.calls.append("compile")
        return self._result("compile", transaction=transaction.digest)

    def runtime(self, transaction):
        self.calls.append("runtime")
        return self._result("runtime", transaction=transaction.digest)

    def commit(self, transaction):
        self.calls.append("commit")
        return self._result("commit", transaction=transaction.digest)

    def rollback(self, transaction, *, failed_phase: str, reason: str):
        self.calls.append("rollback")
        self.rollback_context = (failed_phase, reason)
        if self.rollback_raise:
            raise RuntimeError("rollback explosion")
        phase = "begin" if self.rollback_wrong_phase else "rollback"
        return make_preview_step_result(
            phase,
            ok=self.rollback_ok,
            evidence={
                "transaction": transaction.digest,
                "failed_phase": failed_phase,
                "reason": reason,
            },
            diagnostics=("rollback evidence",),
        )


class NonReceiptBackend(FakeBackend):
    def compile(self, transaction):
        self.calls.append("compile")
        return {"ok": True}


def test_schema_and_phase_contract_are_stable() -> None:
    assert PREVIEW_SCHEMA == "creator.preview_transaction.v1"
    assert PREVIEW_VERSION == 1
    assert PREVIEW_PHASES == (
        "begin",
        "apply",
        "compile",
        "runtime",
        "commit",
        "rollback",
    )
    assert EXECUTION_PHASES == PREVIEW_PHASES[:-1]


def test_staging_is_immutable_and_binds_exact_b011_state() -> None:
    base = _plan()
    base_json = base.canonical_json()

    prepared = stage_preview_transaction(
        base,
        (_edit(),),
        transaction_id="preview-alpha",
    )

    assert base.canonical_json() == base_json
    assert prepared.base_plan is base
    assert prepared.staged_plan is not base
    assert prepared.staged_plan.revision == base.revision + 1
    assert prepared.staged_plan.node_map()["n_stealth"].title == "Preview stealth loop"
    assert prepared.transaction.base_graph_digest == base.digest()
    assert prepared.transaction.staged_graph_digest == prepared.staged_plan.digest()
    assert prepared.transaction.base_state_digest != prepared.transaction.staged_state_digest
    assert prepared.transaction.edit_ids == ("e_preview_title",)
    assert len(prepared.transaction.edit_digests[0]) == 64
    assert len(prepared.transaction.digest) == 64
    validate_prepared_preview(prepared)


def test_staging_is_deterministic_for_identical_inputs() -> None:
    base = _plan()
    first = stage_preview_transaction(
        base,
        (_edit(),),
        transaction_id="preview-alpha",
    )
    second = stage_preview_transaction(
        base,
        (_edit(),),
        transaction_id="preview-alpha",
    )

    assert first.transaction == second.transaction
    assert first.staged_plan.canonical_json() == second.staged_plan.canonical_json()


def test_different_edit_changes_transaction_identity() -> None:
    base = _plan()
    first = stage_preview_transaction(
        base,
        (_edit(value="Preview A"),),
        transaction_id="preview-alpha",
    )
    second = stage_preview_transaction(
        base,
        (_edit(value="Preview B"),),
        transaction_id="preview-alpha",
    )

    assert first.transaction.digest != second.transaction.digest
    assert first.transaction.staged_state_digest != second.transaction.staged_state_digest


@pytest.mark.parametrize(
    "transaction_id",
    ["", " preview", "preview ", "../preview", "preview/path", "bad preview"],
)
def test_transaction_id_is_canonical(transaction_id: str) -> None:
    with pytest.raises(PreviewTransactionError):
        stage_preview_transaction(
            _plan(),
            (_edit(),),
            transaction_id=transaction_id,
        )


def test_empty_and_oversized_edit_sets_fail_closed() -> None:
    with pytest.raises(PreviewTransactionError) as caught:
        stage_preview_transaction(
            _plan(),
            (),
            transaction_id="preview-alpha",
        )
    assert caught.value.context["reason"] == "empty_edits"

    edits = tuple(
        _edit(edit_id=f"e_{index}", value=f"Title {index}")
        for index in range(33)
    )
    with pytest.raises(PreviewTransactionError) as caught:
        stage_preview_transaction(
            _plan(),
            edits,
            transaction_id="preview-alpha",
        )
    assert caught.value.context["reason"] == "bound"


def test_invalid_b011_edit_is_reported_as_staging_failure() -> None:
    invalid = _edit()
    invalid["node_id"] = "n_missing"

    with pytest.raises(PreviewTransactionError) as caught:
        stage_preview_transaction(
            _plan(),
            (invalid,),
            transaction_id="preview-alpha",
        )

    assert caught.value.context["reason"] == "staging_failure"
    assert caught.value.context["index"] == 0


def test_successful_preview_runs_all_phases_and_commits_staged_plan() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    backend = FakeBackend()

    resulting, outcome = execute_preview_transaction(prepared, backend)

    assert backend.calls == list(EXECUTION_PHASES)
    assert resulting.canonical_json() == prepared.staged_plan.canonical_json()
    assert outcome.status == "committed"
    assert outcome.failure_phase is None
    assert outcome.failure_reason is None
    assert outcome.rollback is None
    assert tuple(step.phase for step in outcome.steps) == EXECUTION_PHASES
    assert all(step.ok for step in outcome.steps)
    assert outcome.resulting_state_digest == prepared.transaction.staged_state_digest
    validate_preview_outcome(outcome, prepared, resulting_plan=resulting)


@pytest.mark.parametrize("phase", ("begin", "apply", "compile", "runtime", "commit"))
def test_failed_phase_rolls_back_and_returns_original_plan(phase: str) -> None:
    base = _plan()
    prepared = stage_preview_transaction(
        base,
        (_edit(),),
        transaction_id="preview-alpha",
    )
    backend = FakeBackend(fail_phase=phase)

    resulting, outcome = execute_preview_transaction(prepared, backend)

    failure_index = EXECUTION_PHASES.index(phase)
    assert backend.calls == [*EXECUTION_PHASES[: failure_index + 1], "rollback"]
    assert resulting is base
    assert resulting.canonical_json() == base.canonical_json()
    assert outcome.status == "rolled_back"
    assert outcome.failure_phase == phase
    assert outcome.failure_reason == "step_failed"
    assert outcome.rollback is not None
    assert outcome.rollback.ok is True
    assert outcome.resulting_state_digest == prepared.transaction.base_state_digest
    assert backend.rollback_context == (phase, "step_failed")


@pytest.mark.parametrize("phase", ("begin", "apply", "compile", "runtime", "commit"))
def test_backend_exception_rolls_back_without_leaking_exception_message(phase: str) -> None:
    base = _plan()
    prepared = stage_preview_transaction(
        base,
        (_edit(),),
        transaction_id="preview-alpha",
    )
    backend = FakeBackend(raise_phase=phase)

    resulting, outcome = execute_preview_transaction(prepared, backend)

    assert resulting is base
    assert outcome.status == "rolled_back"
    assert outcome.failure_phase == phase
    assert outcome.failure_reason == "backend_exception:RuntimeError"
    assert "explosion" not in outcome.failure_reason
    assert backend.calls[-1] == "rollback"


def test_compile_failure_never_reaches_runtime_or_commit() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    backend = FakeBackend(fail_phase="compile")

    execute_preview_transaction(prepared, backend)

    assert backend.calls == ["begin", "apply", "compile", "rollback"]
    assert "runtime" not in backend.calls
    assert "commit" not in backend.calls


def test_runtime_failure_never_reaches_commit() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    backend = FakeBackend(fail_phase="runtime")

    execute_preview_transaction(prepared, backend)

    assert backend.calls == ["begin", "apply", "compile", "runtime", "rollback"]
    assert "commit" not in backend.calls


def test_success_never_calls_rollback() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    backend = FakeBackend()

    execute_preview_transaction(prepared, backend)

    assert "rollback" not in backend.calls


def test_wrong_phase_backend_receipt_triggers_rollback() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    backend = FakeBackend(wrong_phase="compile")

    resulting, outcome = execute_preview_transaction(prepared, backend)

    assert resulting is prepared.base_plan
    assert outcome.status == "rolled_back"
    assert outcome.failure_phase == "compile"
    assert outcome.failure_reason == "backend_contract"
    assert backend.calls == ["begin", "apply", "compile", "rollback"]


def test_non_receipt_backend_result_triggers_rollback() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    backend = NonReceiptBackend()

    resulting, outcome = execute_preview_transaction(prepared, backend)

    assert resulting is prepared.base_plan
    assert outcome.failure_phase == "compile"
    assert outcome.failure_reason == "backend_contract"
    assert backend.calls[-1] == "rollback"


def test_failed_rollback_fails_closed_instead_of_claiming_clean_state() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    backend = FakeBackend(
        fail_phase="runtime",
        rollback_ok=False,
    )

    with pytest.raises(PreviewRollbackError) as caught:
        execute_preview_transaction(prepared, backend)

    assert caught.value.context["reason"] == "rollback_failed"


def test_rollback_exception_fails_closed() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    backend = FakeBackend(
        fail_phase="runtime",
        rollback_raise=True,
    )

    with pytest.raises(PreviewRollbackError) as caught:
        execute_preview_transaction(prepared, backend)

    assert caught.value.context["reason"] == "rollback_exception"


def test_wrong_phase_rollback_evidence_fails_closed() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    backend = FakeBackend(
        fail_phase="runtime",
        rollback_wrong_phase=True,
    )

    with pytest.raises(PreviewRollbackError) as caught:
        execute_preview_transaction(prepared, backend)

    assert caught.value.context["reason"] == "rollback_contract"


def test_step_receipt_builder_canonicalizes_diagnostics() -> None:
    result = make_preview_step_result(
        "compile",
        ok=True,
        evidence={"artifact": "abc", "warnings": 0},
        diagnostics=("z warning", "a warning"),
    )

    assert result.diagnostics == ("a warning", "z warning")
    validate_preview_step_result(result, expected_phase="compile")


def test_duplicate_diagnostics_fail_closed() -> None:
    with pytest.raises(PreviewTransactionError) as caught:
        make_preview_step_result(
            "compile",
            ok=True,
            evidence={"artifact": "abc"},
            diagnostics=("same", "same"),
        )
    assert caught.value.context["reason"] == "duplicate"


@pytest.mark.parametrize("value", (math.nan, math.inf, -math.inf))
def test_non_finite_backend_evidence_fails_closed(value: float) -> None:
    with pytest.raises(PreviewTransactionError):
        make_preview_step_result(
            "compile",
            ok=True,
            evidence={"metric": value},
        )


def test_unknown_step_phase_fails_closed() -> None:
    with pytest.raises(PreviewTransactionError):
        make_preview_step_result(
            "publish",
            ok=True,
            evidence={"ok": True},
        )


def test_hand_constructed_invalid_step_receipt_is_rejected() -> None:
    forged = PreviewStepResult(
        phase="compile",
        ok=True,
        evidence_digest="0" * 63,
        diagnostics=(),
    )

    with pytest.raises(PreviewTransactionError):
        validate_preview_step_result(forged, expected_phase="compile")


def test_prepared_transaction_digest_tamper_fails_closed() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    forged = replace(
        prepared,
        transaction=replace(
            prepared.transaction,
            digest="0" * 64,
        ),
    )

    with pytest.raises(PreviewTransactionError) as caught:
        validate_prepared_preview(forged)
    assert caught.value.context["reason"] == "digest_mismatch"


def test_staged_plan_substitution_fails_closed() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    forged = replace(
        prepared,
        staged_plan=prepared.base_plan,
    )

    with pytest.raises(PreviewTransactionError) as caught:
        validate_prepared_preview(forged)
    assert caught.value.context["reason"] == "plan_integrity"


def test_transaction_serialization_is_canonical() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )

    raw = serialize_preview_transaction(prepared)

    assert raw == json.dumps(
        json.loads(raw),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert json.loads(raw)["digest"] == prepared.transaction.digest


def test_outcome_serialization_is_canonical() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    resulting, outcome = execute_preview_transaction(
        prepared,
        FakeBackend(),
    )

    raw = serialize_preview_outcome(
        outcome,
        prepared,
        resulting_plan=resulting,
    )

    assert raw == json.dumps(
        json.loads(raw),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert json.loads(raw)["digest"] == outcome.digest


def test_outcome_digest_tamper_fails_closed() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    resulting, outcome = execute_preview_transaction(
        prepared,
        FakeBackend(),
    )

    with pytest.raises(PreviewTransactionError) as caught:
        validate_preview_outcome(
            replace(outcome, digest="0" * 64),
            prepared,
            resulting_plan=resulting,
        )
    assert caught.value.context["reason"] == "digest_mismatch"


def test_outcome_cannot_be_reused_for_another_transaction() -> None:
    base = _plan()
    first = stage_preview_transaction(
        base,
        (_edit(value="Preview A"),),
        transaction_id="preview-a",
    )
    second = stage_preview_transaction(
        base,
        (_edit(value="Preview B"),),
        transaction_id="preview-b",
    )
    resulting, outcome = execute_preview_transaction(
        first,
        FakeBackend(),
    )

    with pytest.raises(PreviewTransactionError) as caught:
        validate_preview_outcome(
            outcome,
            second,
            resulting_plan=resulting,
        )
    assert caught.value.context["reason"] == "transaction_mismatch"


def test_committed_outcome_requires_all_execution_phases() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    resulting, outcome = execute_preview_transaction(
        prepared,
        FakeBackend(),
    )
    forged = replace(
        outcome,
        steps=outcome.steps[:-1],
    )

    with pytest.raises(PreviewTransactionError) as caught:
        validate_preview_outcome(
            forged,
            prepared,
            resulting_plan=resulting,
        )
    assert caught.value.context["reason"] == "outcome_evidence"


def test_rolled_back_outcome_cannot_claim_staged_plan() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    _base, outcome = execute_preview_transaction(
        prepared,
        FakeBackend(fail_phase="runtime"),
    )

    with pytest.raises(PreviewTransactionError) as caught:
        validate_preview_outcome(
            outcome,
            prepared,
            resulting_plan=prepared.staged_plan,
        )
    assert caught.value.context["reason"] == "digest_mismatch"


def test_backend_apply_receives_exact_staged_state_identity() -> None:
    prepared = stage_preview_transaction(
        _plan(),
        (_edit(),),
        transaction_id="preview-alpha",
    )
    backend = FakeBackend()

    execute_preview_transaction(prepared, backend)

    assert backend.applied_state_digest == prepared.transaction.staged_state_digest


def test_preview_module_has_no_engine_process_network_or_filesystem_authority() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden_modules = {
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "pathlib",
        "os",
        "shutil",
        "tempfile",
        "godot",
    }
    forbidden_calls = {
        "eval",
        "exec",
        "compile",
        "open",
        "system",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {
                alias.name.split(".")[0]
                for alias in node.names
            }.isdisjoint(forbidden_modules)
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden_modules
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls
