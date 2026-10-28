"""Read-only crash/recovery diagnosis for independently witnessed archives.

No implicit repairs: changing external monotonic state requires a separately
reviewed, authorized operator workflow with durable audit evidence. A database
commit alone cannot attest that a witness update was acknowledged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.context.sealed_memento import MementoCatalogHead, SealedMementoArchive
from skeleton.context.sealed_sandwich import SealedContextReplayError
from skeleton.persistence.sealed_memento_witness import (
    IndependentMementoWitness,
    MementoWitnessDivergence,
    MementoWitnessUnavailable,
    WitnessPosition,
    _binding_digest,
)


@dataclass(frozen=True, slots=True)
class MementoRecoveryInspection:
    """Non-privileged metadata; NEVER authorizes changing the witnessed head."""

    classification: str
    witness_revision: int
    witness_serial: int
    mongo_serial: int | None
    candidate_serial: int | None
    source_thread_version: int | None
    manual_intervention_required: bool


async def inspect_memento_recovery(
    *, archive: SealedMementoArchive, mongo: Any,
    witness: IndependentMementoWitness,
) -> MementoRecoveryInspection:
    """Classify a crash window without releasing plaintext or modifying state.

    A one-frame database lead is checked by re-decrypting its verified suffix,
    proving candidate bytes were durably visible. That is a *candidate*, not
    a permit to force an external CAS. Multi-frame or forked states are denied.
    """
    scope = _binding_digest(archive)
    try:
        pinned = await witness.read(binding_digest=scope)
    except Exception as exc:
        raise MementoWitnessUnavailable("recovery witness unavailable") from exc
    if not isinstance(pinned, WitnessPosition) or pinned.binding_digest != scope:
        raise MementoWitnessUnavailable("external recovery position not provisioned")
    if pinned.retired:
        return MementoRecoveryInspection(
            "retired", pinned.revision, pinned.head.serial, None, None, None, True,
        )
    try:
        db_head = await mongo.trusted_head(archive=archive)
    except Exception as exc:
        raise MementoWitnessUnavailable("canonical Mongo recovery state unavailable") from exc
    if not isinstance(db_head, MementoCatalogHead):
        raise MementoWitnessUnavailable("invalid canonical recovery head")
    candidate: int | None = None
    version: int | None = None
    if db_head == pinned.head:
        state = "consistent"
    elif db_head.serial < pinned.head.serial:
        state = "database_rollback_or_loss"
    elif db_head.serial == pinned.head.serial:
        state = "same_serial_fork_or_corruption"
    elif db_head.serial > pinned.head.serial + 1:
        state = "unwitnessed_multiple_commits"
    else:
        # Mongo's possibly durable frame from an interrupted handoff.
        # Reader must verify the exact authenticated successor and its head.
        try:
            page = await mongo.read_window(
                archive=archive, after_serial=pinned.head.serial,
                limit=1, expected_starting_head=pinned.head,
            )
        except Exception as exc:
            raise MementoWitnessDivergence("indeterminate recovery suffix not authenticated") from exc
        if (page.starting_head != pinned.head or page.verified_head != db_head
                or page.authoritative_head != db_head
                or type(page.source_thread_version) is not int
                or page.source_thread_version < 1
                or len(page.records) != 1
                or page.records[0].serial != db_head.serial):
            raise MementoWitnessDivergence("recovery suffix or canonical version failed verification")
        candidate = db_head.serial
        version = page.source_thread_version
        state = "single_verified_unwitnessed_commit"
    try:
        after = await witness.read(binding_digest=scope)
        final_mongo = await mongo.trusted_head(archive=archive)
    except Exception as exc:
        raise MementoWitnessUnavailable("recovery stability recheck unavailable") from exc
    if after != pinned or final_mongo != db_head:
        raise SealedContextReplayError("recovery authority changed during inspection")
    return MementoRecoveryInspection(
        state, pinned.revision, pinned.head.serial, db_head.serial,
        candidate, version, state != "consistent",
    )
