"""Reporting, checkpoint, and human-readable diagnostics for runner v2.

The runner emits two complementary artifacts:

* canonical JSON suitable for machine ingestion and later replay analysis;
* concise Markdown suitable for GitHub step summaries.

This module contains no GitHub mutations.  Reports are derived only from typed
runner contracts and may therefore be rendered offline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .runner_contracts import (
    MutationReceipt,
    MutationState,
    RunnerReport,
    TargetResult,
    TransportSummary,
    WorkState,
    canonical_json,
    parse_time,
)


def write_json(path: str | Path, value: object) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            default=str,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def write_report_json(path: str | Path, report: RunnerReport) -> Path:
    return write_json(path, asdict(report))


def write_transport_json(
    path: str | Path,
    transport: TransportSummary,
) -> Path:
    return write_json(path, asdict(transport))


def _escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _short_sha(value: str | None) -> str:
    if not value:
        return "-"
    return value[:12]


def _duration(start: str, finish: str) -> str:
    left = parse_time(start)
    right = parse_time(finish)
    if left is None or right is None:
        return "unknown"
    ms = max(0, int((right - left).total_seconds() * 1000))
    if ms < 1000:
        return f"{ms} ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f} s"
    return f"{seconds / 60:.1f} min"


def result_counts(
    results: Iterable[TargetResult],
) -> Mapping[str, int]:
    counts = {state.value: 0 for state in WorkState}
    for result in results:
        counts[result.state.value] += 1
    return {name: count for name, count in counts.items() if count}


def mutation_counts(
    results: Iterable[TargetResult],
) -> Mapping[str, int]:
    counts = {state.value: 0 for state in MutationState}
    for result in results:
        for receipt in result.mutations:
            counts[receipt.state.value] += 1
    return {name: count for name, count in counts.items() if count}


def markdown_summary(report: RunnerReport) -> str:
    lines = [
        "# PR automation runner v2",
        "",
        f"- Repository: `{report.identity.repository}`",
        f"- Trigger: `{report.identity.trigger.value}`",
        f"- Admission: `{report.admission.state.value}`",
        f"- Mutation authority: `{str(report.admission.mutation_authorized).lower()}`",
        f"- Duration: {_duration(report.started_at, report.finished_at)}",
        f"- Targets discovered: {len(report.targets.targets)}",
        f"- Mutations attempted: {report.mutations_attempted}",
        f"- Mutations applied: {report.mutations_applied}",
        f"- Failures: {report.failures}",
        f"- Deferred: {report.deferred}",
        f"- Requests: {report.transport.requests}",
        f"- GraphQL requests: {report.transport.graphql_requests}",
        f"- Retries: {report.transport.retries}",
        f"- Bytes received: {report.transport.bytes_received}",
        "",
        "## Target results",
        "",
        "| PR | State | Decision | Requests | Duration | Reasons |",
        "| ---: | --- | --- | ---: | ---: | --- |",
    ]
    for result in sorted(report.results, key=lambda item: item.number):
        reasons = "; ".join(result.reasons) or "-"
        lines.append(
            f"| #{result.number} | {result.state.value} | "
            f"{result.decision.value} | {result.request_count} | "
            f"{result.duration_ms} ms | {_escape(reasons)} |"
        )

    lines.extend(
        [
            "",
            "## Mutation receipts",
            "",
            "| PR | State | Head | Base | Merge SHA | Failed preconditions |",
            "| ---: | --- | --- | --- | --- | --- |",
        ]
    )
    receipts = [
        receipt
        for result in report.results
        for receipt in result.mutations
    ]
    if not receipts:
        lines.append("| - | - | - | - | - | - |")
    for receipt in receipts:
        failed = (
            ",".join(receipt.preconditions.failed())
            if receipt.preconditions is not None
            else "-"
        )
        lines.append(
            f"| #{receipt.intent.pr_number} | {receipt.state.value} | "
            f"`{_short_sha(receipt.observed_head_sha)}` | "
            f"`{_short_sha(receipt.observed_base_sha)}` | "
            f"`{_short_sha(receipt.merge_sha)}` | {_escape(failed)} |"
        )

    lines.extend(
        [
            "",
            "## Transport",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Requests | {report.transport.requests} |",
            f"| GraphQL | {report.transport.graphql_requests} |",
            f"| Retries | {report.transport.retries} |",
            f"| Rate limited | {report.transport.rate_limited} |",
            f"| Failures | {report.transport.failures} |",
            f"| Bytes | {report.transport.bytes_received} |",
            f"| Minimum rate remaining | {report.transport.minimum_remaining_seen if report.transport.minimum_remaining_seen is not None else '-'} |",
            "",
        ]
    )
    return "\n".join(lines)


def append_step_summary(text: str, env: Mapping[str, str]) -> bool:
    path = env.get("GITHUB_STEP_SUMMARY")
    if not path:
        return False
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")
    return True


def compact_report(report: RunnerReport) -> Mapping[str, Any]:
    return {
        "repository": report.identity.repository,
        "delivery_id": report.identity.delivery_id,
        "trigger": report.identity.trigger.value,
        "admission": report.admission.state.value,
        "mutation_authorized": report.admission.mutation_authorized,
        "policy_fingerprint": report.policy_fingerprint,
        "targets": len(report.targets.targets),
        "result_counts": result_counts(report.results),
        "mutation_counts": mutation_counts(report.results),
        "requests": report.transport.requests,
        "graphql_requests": report.transport.graphql_requests,
        "retries": report.transport.retries,
        "bytes_received": report.transport.bytes_received,
        "mutations_attempted": report.mutations_attempted,
        "mutations_applied": report.mutations_applied,
        "failures": report.failures,
        "deferred": report.deferred,
        "final_queue_depth": report.final_queue_depth,
        "final_rate_remaining": report.final_rate_remaining,
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "fingerprint": report.fingerprint(),
    }


def report_exit_code(report: RunnerReport) -> int:
    """Return process exit code without treating policy holds as errors."""
    if report.failures:
        return 1
    return 0


def receipts_for_pr(
    report: RunnerReport,
    pr_number: int,
) -> tuple[MutationReceipt, ...]:
    return tuple(
        receipt
        for result in report.results
        if result.number == pr_number
        for receipt in result.mutations
    )


def applied_merge_shas(report: RunnerReport) -> tuple[str, ...]:
    return tuple(
        receipt.merge_sha
        for result in report.results
        for receipt in result.mutations
        if receipt.state is MutationState.APPLIED
        and receipt.merge_sha is not None
    )


def failed_results(report: RunnerReport) -> tuple[TargetResult, ...]:
    return tuple(
        result
        for result in report.results
        if result.state is WorkState.FAILED
        or result.error is not None
    )


def deferred_results(report: RunnerReport) -> tuple[TargetResult, ...]:
    return tuple(
        result
        for result in report.results
        if result.state is WorkState.DEFERRED
    )


def ready_without_mutation(report: RunnerReport) -> tuple[TargetResult, ...]:
    return tuple(
        result
        for result in report.results
        if result.state is WorkState.READY
        and not result.mutations
    )


def report_invariants(report: RunnerReport) -> tuple[str, ...]:
    problems: list[str] = []
    result_numbers = [result.number for result in report.results]
    if len(result_numbers) != len(set(result_numbers)):
        problems.append("duplicate_target_result")
    discovered = {target.number for target in report.targets.targets}
    if not set(result_numbers).issubset(discovered):
        problems.append("result_for_undiscovered_target")

    attempts = sum(
        len(result.mutations)
        for result in report.results
    )
    applied = sum(
        receipt.state is MutationState.APPLIED
        for result in report.results
        for receipt in result.mutations
    )
    failures = sum(
        result.state is WorkState.FAILED or result.error is not None
        for result in report.results
    )
    deferred = sum(
        result.state is WorkState.DEFERRED
        for result in report.results
    )
    if attempts != report.mutations_attempted:
        problems.append("mutation_attempt_count_mismatch")
    if applied != report.mutations_applied:
        problems.append("mutation_applied_count_mismatch")
    if failures != report.failures:
        problems.append("failure_count_mismatch")
    if deferred != report.deferred:
        problems.append("deferred_count_mismatch")
    if report.mutations_applied > report.mutations_attempted:
        problems.append("applied_exceeds_attempted")
    if report.admission.mutation_authorized is False and report.mutations_attempted:
        problems.append("mutation_without_authority")
    return tuple(problems)


def assert_report_invariants(report: RunnerReport) -> None:
    problems = report_invariants(report)
    if problems:
        raise ValueError(
            "runner report invariants failed: " + ",".join(problems)
        )


@dataclass(frozen=True, slots=True)
class Checkpoint:
    delivery_id: str
    repository: str
    policy_fingerprint: str
    completed_targets: tuple[int, ...]
    mutation_keys: tuple[str, ...]
    report_fingerprint: str | None
    updated_at: str

    def to_json(self) -> str:
        return canonical_json(asdict(self))



def load_checkpoint(path: str | Path) -> Checkpoint | None:
    target = Path(path)
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid runner checkpoint: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("runner checkpoint must be a JSON object")
    completed = payload.get("completed_targets", [])
    keys = payload.get("mutation_keys", [])
    if not isinstance(completed, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) and item > 0
        for item in completed
    ):
        raise ValueError("checkpoint completed_targets are invalid")
    if not isinstance(keys, list) or not all(
        isinstance(item, str) and len(item) == 64
        for item in keys
    ):
        raise ValueError("checkpoint mutation_keys are invalid")
    return Checkpoint(
        delivery_id=str(payload.get("delivery_id") or ""),
        repository=str(payload.get("repository") or ""),
        policy_fingerprint=str(payload.get("policy_fingerprint") or ""),
        completed_targets=tuple(completed),
        mutation_keys=tuple(keys),
        report_fingerprint=(
            str(payload.get("report_fingerprint"))
            if payload.get("report_fingerprint") is not None
            else None
        ),
        updated_at=str(payload.get("updated_at") or ""),
    )


def save_checkpoint(path: str | Path, checkpoint: Checkpoint) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(checkpoint), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def checkpoint_from_report(report: RunnerReport) -> Checkpoint:
    return Checkpoint(
        delivery_id=report.identity.delivery_id,
        repository=report.identity.repository,
        policy_fingerprint=report.policy_fingerprint,
        completed_targets=tuple(
            sorted(result.number for result in report.results)
        ),
        mutation_keys=tuple(
            receipt.intent.key
            for result in report.results
            for receipt in result.mutations
        ),
        report_fingerprint=report.fingerprint(),
        updated_at=report.finished_at,
    )


def checkpoint_compatible(
    checkpoint: Checkpoint,
    *,
    repository: str,
    delivery_id: str,
    policy_fingerprint: str,
) -> bool:
    return (
        checkpoint.repository == repository
        and checkpoint.delivery_id == delivery_id
        and checkpoint.policy_fingerprint == policy_fingerprint
    )


__all__ = [
    "Checkpoint",
    "append_step_summary",
    "applied_merge_shas",
    "assert_report_invariants",
    "checkpoint_compatible",
    "checkpoint_from_report",
    "compact_report",
    "deferred_results",
    "failed_results",
    "load_checkpoint",
    "markdown_summary",
    "mutation_counts",
    "ready_without_mutation",
    "receipts_for_pr",
    "report_exit_code",
    "report_invariants",
    "result_counts",
    "save_checkpoint",
    "write_json",
    "write_report_json",
    "write_transport_json",
]
