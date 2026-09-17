import pytest

from skeleton.automation.run_state import (
    RUN_STATE_AUTHORITATIVE_FAILURE,
    RUN_STATE_IN_FLIGHT,
    RUN_STATE_NON_SUCCESS,
    RUN_STATE_RETRYABLE,
    RUN_STATE_SUCCESS,
    RUN_STATE_SUPERSEDED,
    RUN_STATE_UNKNOWN,
    classify_run_state,
)


def test_completed_failure_on_current_head_is_authoritative() -> None:
    assert (
        classify_run_state(
            status="completed",
            conclusion="FAILURE",
            is_current_head=True,
        )
        == RUN_STATE_AUTHORITATIVE_FAILURE
    )


def test_stale_sha_is_superseded_even_when_the_run_failed() -> None:
    assert (
        classify_run_state(
            status="completed",
            conclusion="failure",
            is_current_head=False,
        )
        == RUN_STATE_SUPERSEDED
    )
    assert (
        classify_run_state(
            status="queued",
            conclusion=None,
            is_current_head=False,
        )
        == RUN_STATE_SUPERSEDED
    )


def test_queued_cancelled_and_skipped_never_count_as_success() -> None:
    assert (
        classify_run_state(
            status="queued",
            conclusion=None,
            is_current_head=True,
        )
        == RUN_STATE_IN_FLIGHT
    )
    assert (
        classify_run_state(
            status="completed",
            conclusion="cancelled",
            is_current_head=True,
        )
        == RUN_STATE_RETRYABLE
    )
    assert (
        classify_run_state(
            status="completed",
            conclusion="timed_out",
            is_current_head=True,
        )
        == RUN_STATE_RETRYABLE
    )
    assert (
        classify_run_state(
            status="completed",
            conclusion="skipped",
            is_current_head=True,
        )
        == RUN_STATE_NON_SUCCESS
    )
    assert (
        classify_run_state(
            status="completed",
            conclusion="success",
            is_current_head=True,
        )
        == RUN_STATE_SUCCESS
    )


def test_unknown_or_malformed_observations_fail_closed() -> None:
    assert (
        classify_run_state(
            status="mystery",
            conclusion="failure",
            is_current_head=True,
        )
        == RUN_STATE_UNKNOWN
    )
    assert (
        classify_run_state(
            status="completed",
            conclusion=None,
            is_current_head=True,
        )
        == RUN_STATE_UNKNOWN
    )
    with pytest.raises(TypeError, match="is_current_head"):
        classify_run_state(
            status="completed",
            conclusion="failure",
            is_current_head=None,  # type: ignore[arg-type]
        )
