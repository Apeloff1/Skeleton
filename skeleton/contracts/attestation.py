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
