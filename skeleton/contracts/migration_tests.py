"""Contract migration checks for canonical automation boundaries."""

from __future__ import annotations

from .canonical import CanonicalEnvelope, EvidenceRef, Identity
from .task_identity import derive_task_identity
from .replay_guard import ReplayGuard


class MigrationContractError(AssertionError):
    pass


def build_sample_delegation() -> CanonicalEnvelope:
    return CanonicalEnvelope(
        schema_version=1,
        kind="delegation",
        identity=Identity(
            repository="Apeloff1/Skeleton",
            commit_sha="sample-sha",
            run_id="1",
            run_attempt="1",
        ),
        evidence=(
            EvidenceRef(
                source="repository_snapshot",
                digest="snapshot-digest",
            ),
        ),
        constraints=("planning_only",),
        payload={"objective": "validate migration"},
    )


def validate_migration_chain() -> str:
    envelope = build_sample_delegation()
    task_id = derive_task_identity(envelope)

    if not task_id:
        raise MigrationContractError("missing task identity")

    guard = ReplayGuard()
    if not guard.accept(envelope.digest):
        raise MigrationContractError("first envelope rejected")
    if guard.accept(envelope.digest):
        raise MigrationContractError("duplicate envelope accepted")

    return task_id
