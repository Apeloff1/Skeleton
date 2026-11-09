"""Bounded machine-readable attestations for the repository contract plane."""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Mapping

MAX_ATTESTATION_BYTES = 64_000
ATTESTATION_VERSION = 1


@dataclass(frozen=True, slots=True)
class ContractAttestation:
    repository: str
    commit_sha: str
    catalog_digest: str
    execution_order: tuple[str, ...]
    contract_fingerprints: Mapping[str, str]
    version: int = ATTESTATION_VERSION

    def payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "repository": self.repository,
            "commit_sha": self.commit_sha.lower(),
            "catalog_digest": self.catalog_digest.lower(),
            "execution_order": list(self.execution_order),
            "contract_fingerprints": dict(sorted(self.contract_fingerprints.items())),
        }

    def canonical_bytes(self) -> bytes:
        raw = json.dumps(
            self.payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(raw) > MAX_ATTESTATION_BYTES:
            raise ValueError("contract attestation exceeds byte budget")
        return raw

    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def validate_attestation(attestation: ContractAttestation) -> None:
    if attestation.version != ATTESTATION_VERSION:
        raise ValueError("unsupported contract attestation version")
    if (
        not attestation.repository
        or attestation.repository.count("/") != 1
        or len(attestation.repository) > 200
    ):
        raise ValueError("invalid attestation repository")
    if len(attestation.commit_sha) != 40 or any(
        char not in "0123456789abcdefABCDEF" for char in attestation.commit_sha
    ):
        raise ValueError("invalid attestation commit sha")
    if len(attestation.catalog_digest) != 64 or any(
        char not in "0123456789abcdefABCDEF" for char in attestation.catalog_digest
    ):
        raise ValueError("invalid attestation catalog digest")
    if not attestation.execution_order or len(attestation.execution_order) > 64:
        raise ValueError("invalid attestation execution order")
    if len(set(attestation.execution_order)) != len(attestation.execution_order):
        raise ValueError("duplicate contract in attestation execution order")
    if set(attestation.execution_order) != set(attestation.contract_fingerprints):
        raise ValueError("attestation fingerprint coverage mismatch")
    for contract_id, digest in attestation.contract_fingerprints.items():
        if not contract_id or len(contract_id) > 80:
            raise ValueError("invalid attestation contract id")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError(f"invalid contract fingerprint: {contract_id}")
    attestation.canonical_bytes()


def verify_digest(attestation: ContractAttestation, expected_digest: str) -> bool:
    validate_attestation(attestation)
    if len(expected_digest) != 64:
        return False
    return hmac.compare_digest(attestation.digest(), expected_digest.lower())


@dataclass(frozen=True, slots=True)
class AttestationChain:
    attestations: tuple[ContractAttestation, ...]
    previous_digests: tuple[str | None, ...]

    def validate(self) -> None:
        if not self.attestations:
            raise ValueError("attestation chain is empty")
        if len(self.attestations) != len(self.previous_digests):
            raise ValueError("attestation chain length mismatch")
        if len(self.attestations) > 256:
            raise ValueError("attestation chain exceeds length budget")
        seen_commits: set[str] = set()
        for index, attestation in enumerate(self.attestations):
            validate_attestation(attestation)
            commit = attestation.commit_sha.lower()
            if commit in seen_commits:
                raise ValueError("duplicate commit in attestation chain")
            seen_commits.add(commit)
            previous = self.previous_digests[index]
            if index == 0:
                if previous is not None:
                    raise ValueError("attestation chain root must not have predecessor")
                continue
            expected = self.attestations[index - 1].digest()
            if previous is None or not hmac.compare_digest(previous.lower(), expected):
                raise ValueError(f"attestation chain discontinuity at index {index}")

    def head_digest(self) -> str:
        self.validate()
        return self.attestations[-1].digest()


def append_attestation(
    chain: AttestationChain | None,
    attestation: ContractAttestation,
) -> AttestationChain:
    validate_attestation(attestation)
    if chain is None:
        result = AttestationChain((attestation,), (None,))
        result.validate()
        return result
    chain.validate()
    result = AttestationChain(
        chain.attestations + (attestation,),
        chain.previous_digests + (chain.head_digest(),),
    )
    result.validate()
    return result


@dataclass(frozen=True, slots=True)
class AttestationCheckpoint:
    head_digest: str
    length: int
    repository: str
    head_commit_sha: str


def checkpoint(chain: AttestationChain) -> AttestationCheckpoint:
    chain.validate()
    head = chain.attestations[-1]
    return AttestationCheckpoint(
        head_digest=chain.head_digest(),
        length=len(chain.attestations),
        repository=head.repository,
        head_commit_sha=head.commit_sha.lower(),
    )


def verify_checkpoint(
    chain: AttestationChain,
    expected: AttestationCheckpoint,
) -> bool:
    try:
        actual = checkpoint(chain)
    except ValueError:
        return False
    return (
        actual.length == expected.length
        and actual.repository == expected.repository
        and actual.head_commit_sha == expected.head_commit_sha.lower()
        and hmac.compare_digest(actual.head_digest, expected.head_digest.lower())
    )


def verify_extension(
    trusted: AttestationCheckpoint,
    candidate: AttestationChain,
) -> bool:
    """Prove candidate preserves a trusted checkpoint as an exact prefix."""
    try:
        candidate.validate()
    except ValueError:
        return False
    if trusted.length < 1 or trusted.length > len(candidate.attestations):
        return False
    prefix = AttestationChain(
        candidate.attestations[: trusted.length],
        candidate.previous_digests[: trusted.length],
    )
    if not verify_checkpoint(prefix, trusted):
        return False
    return (
        candidate.attestations[-1].repository == trusted.repository
        and len(candidate.attestations) >= trusted.length
    )


@dataclass(frozen=True, slots=True)
class AttestationQuorum:
    checkpoint: AttestationCheckpoint
    witnesses: tuple[str, ...]
    threshold: int


def validate_quorum(quorum: AttestationQuorum) -> None:
    if not isinstance(quorum.threshold, int) or isinstance(quorum.threshold, bool):
        raise ValueError("invalid quorum threshold")
    if quorum.threshold < 1 or quorum.threshold > len(quorum.witnesses):
        raise ValueError("quorum threshold outside witness set")
    if len(quorum.witnesses) > 64:
        raise ValueError("quorum witness budget exceeded")
    if len(set(quorum.witnesses)) != len(quorum.witnesses):
        raise ValueError("duplicate quorum witness")
    for witness in quorum.witnesses:
        if (
            not witness
            or len(witness) > 80
            or witness.lower() != witness
            or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789._:-" for char in witness)
        ):
            raise ValueError(f"invalid quorum witness: {witness!r}")


def quorum_digest(quorum: AttestationQuorum) -> str:
    validate_quorum(quorum)
    payload = {
        "checkpoint": {
            "head_digest": quorum.checkpoint.head_digest.lower(),
            "length": quorum.checkpoint.length,
            "repository": quorum.checkpoint.repository,
            "head_commit_sha": quorum.checkpoint.head_commit_sha.lower(),
        },
        "witnesses": sorted(quorum.witnesses),
        "threshold": quorum.threshold,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def quorum_satisfied(
    quorum: AttestationQuorum,
    approvals: Mapping[str, str],
) -> bool:
    """Require threshold distinct witnesses to attest the exact quorum digest."""
    validate_quorum(quorum)
    expected = quorum_digest(quorum)
    accepted = 0
    for witness in quorum.witnesses:
        supplied = approvals.get(witness)
        if supplied is None or len(supplied) != 64:
            continue
        if hmac.compare_digest(supplied.lower(), expected):
            accepted += 1
    return accepted >= quorum.threshold
