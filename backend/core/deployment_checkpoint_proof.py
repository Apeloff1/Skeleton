"""Portable membership proofs for deployment checkpoint publications.

These proofs answer one narrow question: did checkpoint publication N occur in the
append-only deployment checkpoint history whose head an external verifier pinned?
They intentionally do not upgrade a checkpoint with evidence gaps into deployment
authority; inclusion and authority remain separate properties.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hmac
import re
from typing import Any

from core.canonical_json import CanonicalJSONError, canonical_json_clone, canonical_json_sha256
from core.deployment_checkpoint_ledger import (
    DeploymentCheckpointLedger,
    DeploymentCheckpointLedgerError,
    DeploymentCheckpointPublication,
    _parse_utc,
    _restore_publication,
    _validate_evolution,
)

DEPLOYMENT_CHECKPOINT_PROOF_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointPublicationProof:
    version: int
    start_sequence: int
    end_sequence: int
    start_checkpoint_root_sha256: str
    end_checkpoint_root_sha256: str
    ledger_head_sha256: str
    publications: tuple[DeploymentCheckpointPublication, ...]
    proof_sha256: str


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _payload(proof: DeploymentCheckpointPublicationProof) -> dict[str, Any]:
    return {
        "version": proof.version,
        "start_sequence": proof.start_sequence,
        "end_sequence": proof.end_sequence,
        "start_checkpoint_root_sha256": proof.start_checkpoint_root_sha256,
        "end_checkpoint_root_sha256": proof.end_checkpoint_root_sha256,
        "ledger_head_sha256": proof.ledger_head_sha256,
        "publications": [asdict(row) for row in proof.publications],
    }


def _verified_publication(value: Any) -> DeploymentCheckpointPublication:
    """Round-trip a publication through the portable JSON representation.

    ``dataclasses.asdict`` preserves tuple containers. Durable publication JSON does
    not: tuple-valued fields such as ``release_channels`` are represented as arrays.
    Verification must therefore validate exactly the representation an external
    verifier receives instead of feeding Python-only container types into the strict
    persisted-schema parser.
    """
    if not isinstance(value, DeploymentCheckpointPublication):
        raise DeploymentCheckpointLedgerError("checkpoint proof publication type mismatch")
    try:
        portable = canonical_json_clone(asdict(value))
    except CanonicalJSONError as exc:
        raise DeploymentCheckpointLedgerError("checkpoint proof publication is not portable JSON") from exc
    restored = _restore_publication(portable)
    if restored != value:
        raise DeploymentCheckpointLedgerError("checkpoint proof publication round-trip mismatch")
    return restored


def _verify_suffix(publications: tuple[DeploymentCheckpointPublication, ...]) -> bool:
    if not isinstance(publications, tuple) or not publications:
        return False
    roots: set[str] = set()
    previous: DeploymentCheckpointPublication | None = None
    try:
        for publication in publications:
            current = _verified_publication(publication)
            if current.checkpoint_root_sha256 in roots:
                return False
            if previous is not None:
                if current.sequence != previous.sequence + 1:
                    return False
                if not hmac.compare_digest(current.previous_sha256, previous.sha256):
                    return False
                if not hmac.compare_digest(
                    current.previous_checkpoint_root_sha256,
                    previous.checkpoint_root_sha256,
                ):
                    return False
                if _parse_utc(current.published_at) < _parse_utc(previous.published_at):
                    return False
                _validate_evolution(previous.checkpoint, current.checkpoint)
            roots.add(current.checkpoint_root_sha256)
            previous = current
    except (CanonicalJSONError, DeploymentCheckpointLedgerError, TypeError, ValueError):
        return False
    return True


def build_deployment_checkpoint_publication_proof(
    ledger: DeploymentCheckpointLedger,
    sequence: int,
) -> DeploymentCheckpointPublicationProof:
    if type(sequence) is not int or sequence < 1:
        raise ValueError("checkpoint sequence must be a positive integer")
    history = ledger.history()
    if sequence > len(history):
        raise KeyError(sequence)
    publications = tuple(history[sequence - 1 :])
    if not publications or publications[0].sequence != sequence:
        raise DeploymentCheckpointLedgerError("checkpoint publication sequence missing from verified history")
    if not _verify_suffix(publications):
        raise DeploymentCheckpointLedgerError("checkpoint publication suffix failed verification")
    first = publications[0]
    last = publications[-1]
    draft = DeploymentCheckpointPublicationProof(
        version=DEPLOYMENT_CHECKPOINT_PROOF_VERSION,
        start_sequence=first.sequence,
        end_sequence=last.sequence,
        start_checkpoint_root_sha256=first.checkpoint_root_sha256,
        end_checkpoint_root_sha256=last.checkpoint_root_sha256,
        ledger_head_sha256=last.sha256,
        publications=publications,
        proof_sha256="",
    )
    digest = canonical_json_sha256(_payload(draft))
    return DeploymentCheckpointPublicationProof(
        draft.version,
        draft.start_sequence,
        draft.end_sequence,
        draft.start_checkpoint_root_sha256,
        draft.end_checkpoint_root_sha256,
        draft.ledger_head_sha256,
        draft.publications,
        digest,
    )


def build_deployment_checkpoint_publication_extension(
    ledger: DeploymentCheckpointLedger,
    previous_ledger_head_sha256: str,
) -> DeploymentCheckpointPublicationProof:
    """Build a suffix proof directly from a previously pinned publication head.

    The caller supplies only the externally retained old head. The ledger resolves
    its authenticated publication sequence internally and returns that anchor plus all
    later publications through the current head. This avoids trusting a server-side
    sequence number as part of the auditor's state.
    """
    if not _is_sha(previous_ledger_head_sha256):
        raise ValueError("previous deployment checkpoint ledger head must be lowercase sha256")
    history = ledger.history()
    anchor = next(
        (row for row in history if hmac.compare_digest(row.sha256, previous_ledger_head_sha256)),
        None,
    )
    if anchor is None:
        raise KeyError(previous_ledger_head_sha256)
    proof = build_deployment_checkpoint_publication_proof(ledger, anchor.sequence)
    if not verify_deployment_checkpoint_publication_extension(
        proof,
        expected_previous_ledger_head_sha256=previous_ledger_head_sha256,
        expected_current_ledger_head_sha256=proof.ledger_head_sha256,
    ):
        raise DeploymentCheckpointLedgerError("checkpoint publication extension failed verification")
    return proof


def verify_deployment_checkpoint_publication_proof(
    proof: DeploymentCheckpointPublicationProof,
    *,
    expected_ledger_head_sha256: str,
    expected_start_checkpoint_root_sha256: str | None = None,
    expected_start_publication_sha256: str | None = None,
) -> bool:
    """Verify membership against externally supplied current and optional prior pins.

    ``expected_ledger_head_sha256`` authenticates the current end of the publication
    history. Supplying ``expected_start_publication_sha256`` additionally turns the
    suffix into an append-only extension proof from a previously pinned publication
    head, allowing an auditor to advance trust without replaying ledger genesis.
    """
    try:
        if not isinstance(proof, DeploymentCheckpointPublicationProof):
            return False
        if type(proof.version) is not int or proof.version != DEPLOYMENT_CHECKPOINT_PROOF_VERSION:
            return False
        if type(proof.start_sequence) is not int or type(proof.end_sequence) is not int:
            return False
        if proof.start_sequence < 1 or proof.end_sequence < proof.start_sequence:
            return False
        if not all(_is_sha(value) for value in (
            proof.start_checkpoint_root_sha256,
            proof.end_checkpoint_root_sha256,
            proof.ledger_head_sha256,
            proof.proof_sha256,
            expected_ledger_head_sha256,
        )):
            return False
        if expected_start_checkpoint_root_sha256 is not None and not _is_sha(expected_start_checkpoint_root_sha256):
            return False
        if expected_start_publication_sha256 is not None and not _is_sha(expected_start_publication_sha256):
            return False
        if not hmac.compare_digest(proof.ledger_head_sha256, expected_ledger_head_sha256):
            return False
        if not isinstance(proof.publications, tuple) or not proof.publications:
            return False
        if len(proof.publications) != proof.end_sequence - proof.start_sequence + 1:
            return False
        first = proof.publications[0]
        last = proof.publications[-1]
        if first.sequence != proof.start_sequence or last.sequence != proof.end_sequence:
            return False
        if expected_start_checkpoint_root_sha256 is not None and not hmac.compare_digest(
            first.checkpoint_root_sha256,
            expected_start_checkpoint_root_sha256,
        ):
            return False
        if expected_start_publication_sha256 is not None and not hmac.compare_digest(
            first.sha256,
            expected_start_publication_sha256,
        ):
            return False
        if not hmac.compare_digest(first.checkpoint_root_sha256, proof.start_checkpoint_root_sha256):
            return False
        if not hmac.compare_digest(last.checkpoint_root_sha256, proof.end_checkpoint_root_sha256):
            return False
        if not hmac.compare_digest(last.sha256, proof.ledger_head_sha256):
            return False
        if not _verify_suffix(proof.publications):
            return False
        expected_proof = canonical_json_sha256(_payload(proof))
        return hmac.compare_digest(expected_proof, proof.proof_sha256)
    except (CanonicalJSONError, DeploymentCheckpointLedgerError, TypeError, ValueError):
        return False


def verify_deployment_checkpoint_publication_extension(
    proof: DeploymentCheckpointPublicationProof,
    *,
    expected_previous_ledger_head_sha256: str,
    expected_current_ledger_head_sha256: str,
) -> bool:
    """Verify an append-only extension from one externally pinned head to another."""
    return verify_deployment_checkpoint_publication_proof(
        proof,
        expected_ledger_head_sha256=expected_current_ledger_head_sha256,
        expected_start_publication_sha256=expected_previous_ledger_head_sha256,
    )
