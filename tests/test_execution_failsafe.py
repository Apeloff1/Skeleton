from __future__ import annotations

import copy

import pytest

from skeleton.automation import secretary
from skeleton.automation.execution_failsafe import (
    FailureKind,
    attach_retry_history,
    classify_result,
    retry_allowed,
    retry_delay_seconds,
    retry_token,
    summarize_results,
)
from skeleton.automation.supervisor_runtime import ExecutionIdentity

EXECUTION = ExecutionIdentity(
    repository="Apeloff1/Skeleton",
    base_sha="a" * 40,
    default_branch="main",
    run_id="123",
    run_attempt="1",
)


def result(
    *,
    returncode: int = 1,
    status: str | None = None,
    failure_kind: str | None = None,
    attempt: int = 1,
) -> dict[str, object]:
    value: dict[str, object] = {
        "bot": "feature-builder",
        "returncode": returncode,
        "attempt": attempt,
    }
    if status is not None:
        value["evidence"] = {"status": status}
    if failure_kind is not None:
        value["failure_kind"] = failure_kind
    return value


@pytest.mark.parametrize(
    ("status", "kind"),
    (
        ("pull-request-created", FailureKind.SUCCESS),
        ("pull-request-updated", FailureKind.SUCCESS),
        ("no-change", FailureKind.NO_CHANGE),
        ("existing-pr", FailureKind.EXISTING_PR),
    ),
)
def test_success_vocabulary_is_closed(status: str, kind: FailureKind) -> None:
    outcome = classify_result(result(returncode=0, status=status))
    assert outcome.kind is kind
    assert outcome.terminal is True
    assert outcome.retryable is False


def test_zero_exit_without_admitted_status_fails_closed() -> None:
    outcome = classify_result(result(returncode=0))
    assert outcome.kind is FailureKind.INVALID_EVIDENCE
    assert outcome.terminal is True


@pytest.mark.parametrize(
    "kind",
    (
        "worker-failure",
        "worker-timeout",
        "invalid-evidence",
        "custody-failure",
        "policy-failure",
        "unknown-failure",
    ),
)
def test_post_start_or_ambiguous_failure_never_retries(kind: str) -> None:
    value = result(failure_kind=kind)
    assert retry_allowed(value) is False
    assert classify_result(value).terminal is True


def test_only_first_setup_failure_is_retryable() -> None:
    first = result(failure_kind="setup-failure", attempt=1)
    second = result(failure_kind="setup-failure", attempt=2)
    assert retry_allowed(first) is True
    assert classify_result(first).terminal is False
    assert retry_allowed(second) is False
    assert classify_result(second).terminal is True


def test_model_cannot_invent_retryable_failure_kind() -> None:
    outcome = classify_result(result(failure_kind="please-retry-me"))
    assert outcome.kind is FailureKind.UNKNOWN_FAILURE
    assert outcome.retryable is False


@pytest.mark.parametrize(
    "override",
    (
        {"bot": ""},
        {"bot": "Feature_Builder"},
        {"returncode": True},
        {"returncode": "1"},
        {"attempt": 0},
        {"attempt": 3},
        {"attempt": True},
    ),
)
def test_malformed_outcomes_fail_closed(override: dict[str, object]) -> None:
    value = result()
    value.update(override)
    with pytest.raises(ValueError):
        classify_result(value)


def test_summary_is_deterministic_and_bounded() -> None:
    values = [
        result(returncode=0, status="pull-request-created"),
        result(failure_kind="worker-timeout"),
    ]
    first = summarize_results(values)
    second = summarize_results(copy.deepcopy(values))
    assert first == second
    assert first["terminal_failures"] == 1
    assert first["retryable_count"] == 0
    assert first["counts"] == {
        "success": 1,
        "worker-timeout": 1,
    }
    assert len(first["summary_digest"]) == 64


def test_failure_digest_excludes_free_form_failure_text() -> None:
    first = result(failure_kind="worker-failure")
    second = dict(first)
    first["stderr"] = "secret-shaped attacker controlled output"
    second["stderr"] = "different output"
    assert classify_result(first).failure_digest == classify_result(second).failure_digest


def test_dispatch_retries_one_pre_execution_setup_failure(monkeypatch) -> None:
    attempts: list[int] = []

    def fake_dispatch(*_args, **kwargs):
        attempt = kwargs.get("attempt", 1)
        attempts.append(attempt)
        if attempt == 1:
            return result(failure_kind="setup-failure", attempt=1)
        return result(returncode=0, status="no-change", attempt=2)

    monkeypatch.setattr(secretary, "_dispatch_one", fake_dispatch)
    monkeypatch.setattr(secretary.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(secretary, "require_exact_head", lambda _sha: None)
    monkeypatch.setattr(secretary, "require_remote_base_unchanged", lambda _execution: None)
    results = secretary.dispatch(
        "repair CI",
        ["root-cause"],
        "b" * 64,
        EXECUTION,
    )
    assert attempts == [1, 2]
    assert results[0]["evidence"]["status"] == "no-change"
    assert [item["attempt"] for item in results[0]["attempt_history"]] == [1, 2]
    assert len(results[0]["retry_chain_digest"]) == 64


@pytest.mark.parametrize(
    "failure_kind",
    ("worker-timeout", "worker-failure", "invalid-evidence"),
)
def test_dispatch_does_not_retry_ambiguous_failure(monkeypatch, failure_kind: str) -> None:
    calls = 0

    def fake_dispatch(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return result(failure_kind=failure_kind)

    monkeypatch.setattr(secretary, "_dispatch_one", fake_dispatch)
    results = secretary.dispatch(
        "repair CI",
        ["root-cause"],
        "b" * 64,
        EXECUTION,
    )
    assert calls == 1
    assert results[0]["failure_kind"] == failure_kind


def test_step_summary_is_bounded_and_contains_custody(tmp_path, monkeypatch) -> None:
    path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))
    summary = summarize_results([result(failure_kind="worker-timeout")])
    secretary._append_step_summary(
        execution=EXECUTION,
        assignments=["root-cause"],
        failsafe_summary=summary,
    )
    rendered = path.read_text(encoding="utf-8")
    assert EXECUTION.base_sha in rendered
    assert EXECUTION.fingerprint in rendered
    assert summary["summary_digest"] in rendered
    assert "worker-timeout" in rendered


def test_step_summary_rejects_symlink(tmp_path, monkeypatch) -> None:
    target = tmp_path / "target.md"
    target.write_text("untouched\n", encoding="utf-8")
    link = tmp_path / "summary.md"
    link.symlink_to(target)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(link))
    with pytest.raises(secretary.SecretaryAdmissionError, match="unsafe"):
        secretary._append_step_summary(
            execution=EXECUTION,
            assignments=[],
            failsafe_summary=None,
        )
    assert target.read_text(encoding="utf-8") == "untouched\n"


def test_retry_token_is_deterministic_and_custody_bound() -> None:
    first = retry_token(
        worker="feature-builder",
        attempt=1,
        execution_fingerprint="a" * 64,
        snapshot_fingerprint="b" * 64,
    )
    same = retry_token(
        worker="feature-builder",
        attempt=1,
        execution_fingerprint="a" * 64,
        snapshot_fingerprint="b" * 64,
    )
    next_attempt = retry_token(
        worker="feature-builder",
        attempt=2,
        execution_fingerprint="a" * 64,
        snapshot_fingerprint="b" * 64,
    )
    assert first == same
    assert first != next_attempt
    assert len(first) == 64


def test_retry_backoff_is_deterministic_and_bounded() -> None:
    token = retry_token(
        worker="root-cause",
        attempt=2,
        execution_fingerprint="a" * 64,
        snapshot_fingerprint="b" * 64,
    )
    delay = retry_delay_seconds(2, token)
    assert delay == retry_delay_seconds(2, token)
    assert 1 <= delay <= 8


def test_retry_history_rejects_noncontiguous_attempts() -> None:
    first = result(failure_kind="setup-failure", attempt=1)
    third = result(returncode=0, status="no-change", attempt=2)
    third["attempt"] = 1
    with pytest.raises(ValueError, match="contiguous"):
        attach_retry_history(
            third,
            [first, third],
            execution_fingerprint="a" * 64,
            snapshot_fingerprint="b" * 64,
        )


def test_retry_history_rejects_transition_after_terminal_failure() -> None:
    first = result(failure_kind="worker-timeout", attempt=1)
    second = result(returncode=0, status="no-change", attempt=2)
    with pytest.raises(ValueError, match="unauthorized transition"):
        attach_retry_history(
            second,
            [first, second],
            execution_fingerprint="a" * 64,
            snapshot_fingerprint="b" * 64,
        )
