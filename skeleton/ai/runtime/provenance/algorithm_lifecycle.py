"""Digest lifecycle policy for long-horizon receipt issuance and verification."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .execution_receipt import SUPPORTED_DIGESTS

@dataclass(frozen=True, slots=True)
class AlgorithmPolicy:
    algorithm: str
    issue_from: int
    issue_until: int | None = None
    verify_until: int | None = None

    def __post_init__(self) -> None:
        if self.algorithm not in SUPPORTED_DIGESTS:
            raise ValueError("unsupported algorithm policy")
        if self.issue_from < 2020:
            raise ValueError("issue_from predates supported horizon")
        if self.issue_until is not None and self.issue_until < self.issue_from:
            raise ValueError("issue_until precedes issue_from")
        if self.verify_until is not None and self.issue_until is not None and self.verify_until < self.issue_until:
            raise ValueError("verification cannot retire before issuance")

    def can_issue(self, year: int) -> bool:
        return year >= self.issue_from and (self.issue_until is None or year <= self.issue_until)

    def can_verify(self, year: int) -> bool:
        return year >= self.issue_from and (self.verify_until is None or year <= self.verify_until)

POLICIES: Final[dict[str,AlgorithmPolicy]] = {
    "sha256": AlgorithmPolicy("sha256",2020),
    "sha3-256": AlgorithmPolicy("sha3-256",2020),
    "blake2b-256": AlgorithmPolicy("blake2b-256",2020),
}

def algorithm_policy(algorithm: str) -> AlgorithmPolicy:
    try:
        return POLICIES[algorithm]
    except KeyError as exc:
        raise ValueError("unknown digest algorithm") from exc

def require_issuable(algorithm: str, year: int) -> None:
    if not isinstance(year,int) or isinstance(year,bool):
        raise TypeError("year must be an integer")
    if not algorithm_policy(algorithm).can_issue(year):
        raise ValueError("digest algorithm is retired for issuance")

def require_verifiable(algorithm: str, year: int) -> None:
    if not isinstance(year,int) or isinstance(year,bool):
        raise TypeError("year must be an integer")
    if not algorithm_policy(algorithm).can_verify(year):
        raise ValueError("digest algorithm is outside verification lifecycle")

__all__=["AlgorithmPolicy","POLICIES","algorithm_policy","require_issuable","require_verifiable"]
