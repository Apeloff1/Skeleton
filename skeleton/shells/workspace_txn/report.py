"""Human/operator-facing transaction summaries without file content."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.workspace_txn.types import TransactionResult


@dataclass(frozen=True)
class TransactionSummary:
    transaction_id: str
    state: str
    execution_ok: bool
    policy_allowed: bool
    total_changes: int
    created: int
    modified: int
    deleted: int
    renamed: int
    bytes_added: int
    bytes_removed: int
    rollback_ok: bool | None
    highest_severity: str
    paths: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "transaction_id": self.transaction_id,
            "state": self.state,
            "execution_ok": self.execution_ok,
            "policy_allowed": self.policy_allowed,
            "total_changes": self.total_changes,
            "created": self.created,
            "modified": self.modified,
            "deleted": self.deleted,
            "renamed": self.renamed,
            "bytes_added": self.bytes_added,
            "bytes_removed": self.bytes_removed,
            "rollback_ok": self.rollback_ok,
            "highest_severity": self.highest_severity,
            "paths": list(self.paths),
        }


def summarize(result: TransactionResult, *, max_paths: int = 50) -> TransactionSummary:
    if isinstance(max_paths, bool) or max_paths < 0:
        raise ValueError("max_paths must be non-negative")
    severity_order = {"warning": 1, "error": 2, "critical": 3}
    highest = ""
    if result.decision.violations:
        highest = max(
            (violation.severity for violation in result.decision.violations),
            key=lambda value: severity_order[value],
        )
    stats = result.changes.statistics
    paths = tuple(change.path for change in result.changes.changes[:max_paths])
    return TransactionSummary(
        transaction_id=result.receipt.transaction_id,
        state=result.receipt.state.value,
        execution_ok=result.receipt.execution_ok,
        policy_allowed=result.receipt.policy_allowed,
        total_changes=stats.total_changes,
        created=stats.created,
        modified=stats.modified,
        deleted=stats.deleted,
        renamed=stats.renamed,
        bytes_added=stats.bytes_added,
        bytes_removed=stats.bytes_removed,
        rollback_ok=result.receipt.rollback_ok,
        highest_severity=highest,
        paths=paths,
    )


def format_text(result: TransactionResult, *, max_paths: int = 20) -> str:
    summary = summarize(result, max_paths=max_paths)
    lines = [
        f"transaction={summary.transaction_id}",
        f"state={summary.state}",
        f"execution_ok={summary.execution_ok}",
        f"policy_allowed={summary.policy_allowed}",
        f"changes={summary.total_changes}",
        (
            f"created={summary.created} modified={summary.modified} "
            f"deleted={summary.deleted} renamed={summary.renamed}"
        ),
        f"bytes_added={summary.bytes_added} bytes_removed={summary.bytes_removed}",
        f"rollback_ok={summary.rollback_ok}",
    ]
    if summary.highest_severity:
        lines.append(f"highest_violation_severity={summary.highest_severity}")
    for path in summary.paths:
        lines.append(f"path={path}")
    return "\n".join(lines)
