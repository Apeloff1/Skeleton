from dataclasses import dataclass
from typing import Any

from .canonical import CanonicalEnvelope, EvidenceRef, Identity


class ResultContractError(ValueError):
    pass


@dataclass(frozen=True)
class WorkerResult:
    task_id: str
    changed_files: tuple[str, ...]
    tests_run: tuple[str, ...]
    validation_status: str
    evidence: tuple[EvidenceRef, ...]


def result_to_canonical(
    result: WorkerResult,
    identity: Identity,
) -> CanonicalEnvelope:
    if not result.task_id:
        raise ResultContractError("missing task identity")

    if result.validation_status not in {
        "passed",
        "failed",
        "partial",
    }:
        raise ResultContractError("invalid validation state")

    return CanonicalEnvelope(
        schema_version=1,
        kind="execution_result",
        identity=identity,
        evidence=result.evidence,
        constraints=(
            "validated_output_only",
            "no_authority_expansion",
        ),
        payload={
            "task_id": result.task_id,
            "changed_files": list(result.changed_files),
            "tests_run": list(result.tests_run),
            "validation_status": result.validation_status,
        },
    )
