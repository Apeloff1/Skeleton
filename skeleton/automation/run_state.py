"""Fail-closed classification of GitHub Actions run observations.

The classifier exists so automation can pre-empt retries, intake, and
repair on superseded or in-flight runs instead of treating every terminal
event as a fresh defect.
"""

from __future__ import annotations

from typing import Final

RUN_STATE_IN_FLIGHT: Final = "in_flight"
RUN_STATE_SUPERSEDED: Final = "superseded"
RUN_STATE_RETRYABLE: Final = "retryable"
RUN_STATE_AUTHORITATIVE_FAILURE: Final = "authoritative_failure"
RUN_STATE_SUCCESS: Final = "success"
RUN_STATE_NON_SUCCESS: Final = "non_success"
RUN_STATE_UNKNOWN: Final = "unknown"

_IN_FLIGHT_STATUSES = frozenset(
    {"queued", "waiting", "pending", "in_progress", "requested"}
)
_RETRYABLE_CONCLUSIONS = frozenset({"cancelled", "timed_out"})
_NON_SUCCESS_CONCLUSIONS = frozenset(
    {"skipped", "neutral", "stale", "startup_failure", "action_required"}
)


def _required_token(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def classify_run_state(
    *,
    status: str,
    conclusion: str | None,
    is_current_head: bool,
) -> str:
    """Classify one workflow-run observation without inspecting logs or code.

    Queued or cancelled results are never treated as success. A completed
    failure on a SHA that is no longer the branch tip is superseded, not a
    new repair.
    """

    if not isinstance(is_current_head, bool):
        raise TypeError("is_current_head must be a bool")

    try:
        normalized_status = _required_token(status, "status")
    except (TypeError, ValueError):
        return RUN_STATE_UNKNOWN

    if not is_current_head:
        return RUN_STATE_SUPERSEDED

    if normalized_status in _IN_FLIGHT_STATUSES:
        return RUN_STATE_IN_FLIGHT
    if normalized_status != "completed":
        return RUN_STATE_UNKNOWN

    if conclusion is None:
        return RUN_STATE_UNKNOWN
    try:
        normalized_conclusion = _required_token(conclusion, "conclusion")
    except (TypeError, ValueError):
        return RUN_STATE_UNKNOWN

    if normalized_conclusion == "success":
        return RUN_STATE_SUCCESS
    if normalized_conclusion == "failure":
        return RUN_STATE_AUTHORITATIVE_FAILURE
    if normalized_conclusion in _RETRYABLE_CONCLUSIONS:
        return RUN_STATE_RETRYABLE
    if normalized_conclusion in _NON_SUCCESS_CONCLUSIONS:
        return RUN_STATE_NON_SUCCESS
    return RUN_STATE_UNKNOWN
