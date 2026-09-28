"""Lifecycle instrumentation helpers for command execution.

Keeps execution tracking separate from command handlers. Transports and
handlers remain unaware of retry policy while the runtime can attach evidence
and reconciliation metadata around CommandService execution.
"""

from __future__ import annotations

from typing import Any, Mapping

from .execution_ledger import ExecutionLedger


class CommandExecutionLifecycle:
    """Small adapter around the execution ledger boundary."""

    def __init__(self, ledger: ExecutionLedger | None = None) -> None:
        self.ledger = ledger or ExecutionLedger()

    def begin(
        self,
        command: str,
        payload: Mapping[str, Any] | None = None,
    ) -> str:
        # Payload content belongs to command evidence, not ledger identity.
        # The ledger owns execution identity and returns the canonical record.
        _ = payload
        record = self.ledger.begin(command=command)
        return record.execution_id

    def succeed(
        self,
        execution_id: str,
        result: Mapping[str, Any],
    ) -> None:
        self.ledger.complete(
            execution_id,
            success=True,
            evidence={"result_keys": sorted(result.keys())},
        )

    def fail(
        self,
        execution_id: str,
        error: str,
        *,
        retryable: bool = False,
    ) -> None:
        self.ledger.complete(
            execution_id,
            success=False,
            retryable=retryable,
            evidence={"error": error},
        )
