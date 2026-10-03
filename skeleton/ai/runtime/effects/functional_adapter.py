"""Adapter from the canonical VS-001 FunctionalAIRuntime into the effects plane."""
from __future__ import annotations

from typing import Any

from .contracts import CoreExecution


class FunctionalAIAdapter:
    """Preserves the existing AI runtime as the cognitive authority boundary.

    The adapter extracts only terminal output and evidence identity.  That output
    is still merely a proposal source; it cannot authorize an effect.
    """

    def __init__(self, runtime: Any) -> None:
        if runtime is None or not callable(getattr(runtime, "execute", None)):
            raise TypeError("runtime must provide async execute(request)")
        self.runtime = runtime

    async def run(self, request: Any) -> CoreExecution:
        run = await self.runtime.execute(request)
        terminal = getattr(run.execution, "result", None)
        if terminal is None or getattr(terminal, "final_output", None) is None:
            raise RuntimeError("functional AI produced no committed terminal output")
        evidence = run.evidence
        tenant_id = getattr(request, "tenant_id", None)
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise RuntimeError("functional AI request lost tenant identity")
        refs = tuple(getattr(evidence, "evidence_refs", ()))
        return CoreExecution(
            execution_id=str(evidence.execution_id),
            operation_id=str(evidence.operation_id),
            tenant_id=tenant_id,
            output_text=str(terminal.final_output),
            evidence_digest=str(evidence.result_digest),
            evidence_refs=refs,
        )
