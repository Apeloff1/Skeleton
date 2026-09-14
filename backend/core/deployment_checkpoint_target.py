"""Canonical signing targets for external deployment-checkpoint witnesses.

The server never signs on behalf of a witness. It only exports a self-verifying target
that binds the durable publication identity to its embedded deployment checkpoint.
External signers can independently inspect the publication, then sign the publication
head using the Ed25519 witness primitive.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hmac
import re
from typing import Any

from core.canonical_json import CanonicalJSONError, canonical_json_clone, canonical_json_sha256
from core.deployment_checkpoint_ledger import (
    DeploymentCheckpointPublication,
    DeploymentCheckpointLedgerError,
    _restore_publication,
)
from core.deployment_checkpoint_witness import DEPLOYMENT_CHECKPOINT_LOG_ID

DEPLOYMENT_CHECKPOINT_TARGET_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointWitnessTarget:
    version: int
    log_id: str
    tree_size: int
    publication_sha256: str
    checkpoint_root_sha256: str
    checkpoint_attestation_sha256: str
    target_sha256: str


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _payload(target: DeploymentCheckpointWitnessTarget) -> dict[str, Any]:
    return {
        "version": target.version,
        "log_id": target.log_id,
        "tree_size": target.tree_size,
        "publication_sha256": target.publication_sha256,
        "checkpoint_root_sha256": target.checkpoint_root_sha256,
        "checkpoint_attestation_sha256": target.checkpoint_attestation_sha256,
    }


def _verified_publication(publication: DeploymentCheckpointPublication) -> DeploymentCheckpointPublication:
    if not isinstance(publication, DeploymentCheckpointPublication):
        raise ValueError("checkpoint publication type mismatch")
    portable = canonical_json_clone(asdict(publication))
    restored = _restore_publication(portable)
    if restored != publication:
        raise ValueError("checkpoint publication round-trip mismatch")
    return restored


def build_deployment_checkpoint_witness_target(
    publication: DeploymentCheckpointPublication,
) -> DeploymentCheckpointWitnessTarget:
    publication = _verified_publication(publication)
    draft = DeploymentCheckpointWitnessTarget(
        version=DEPLOYMENT_CHECKPOINT_TARGET_VERSION,
        log_id=DEPLOYMENT_CHECKPOINT_LOG_ID,
        tree_size=publication.sequence,
        publication_sha256=publication.sha256,
        checkpoint_root_sha256=publication.checkpoint_root_sha256,
        checkpoint_attestation_sha256=publication.checkpoint_attestation_sha256,
        target_sha256="",
    )
    digest = canonical_json_sha256(_payload(draft))
    return DeploymentCheckpointWitnessTarget(
        draft.version,
        draft.log_id,
        draft.tree_size,
        draft.publication_sha256,
        draft.checkpoint_root_sha256,
        draft.checkpoint_attestation_sha256,
        digest,
    )


def verify_deployment_checkpoint_witness_target(
    target: DeploymentCheckpointWitnessTarget,
    *,
    publication: DeploymentCheckpointPublication,
) -> bool:
    try:
        if not isinstance(target, DeploymentCheckpointWitnessTarget):
            return False
        if type(target.version) is not int or target.version != DEPLOYMENT_CHECKPOINT_TARGET_VERSION:
            return False
        if target.log_id != DEPLOYMENT_CHECKPOINT_LOG_ID:
            return False
        if type(target.tree_size) is not int or target.tree_size < 1:
            return False
        if not all(_is_sha(value) for value in (
            target.publication_sha256,
            target.checkpoint_root_sha256,
            target.checkpoint_attestation_sha256,
            target.target_sha256,
        )):
            return False
        publication = _verified_publication(publication)
        if target.tree_size != publication.sequence:
            return False
        if not hmac.compare_digest(target.publication_sha256, publication.sha256):
            return False
        if not hmac.compare_digest(target.checkpoint_root_sha256, publication.checkpoint_root_sha256):
            return False
        if not hmac.compare_digest(
            target.checkpoint_attestation_sha256,
            publication.checkpoint_attestation_sha256,
        ):
            return False
        expected = canonical_json_sha256(_payload(target))
        return hmac.compare_digest(expected, target.target_sha256)
    except (CanonicalJSONError, DeploymentCheckpointLedgerError, TypeError, ValueError):
        return False
