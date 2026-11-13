"""Bounded explicit approvals with independent human principal identities."""
from dataclasses import dataclass
from ..contracts.identity import identifier
from ..contracts.errors import AuthorizationError, ContractError

@dataclass(frozen=True)
class Approval:
    operation_sha256: str
    reviewers: tuple[str, ...]
    reason: str

def approve(operation_sha256: str, reviewers: list[str], reason: str, *, quorum: int=2, initiator: str | None=None) -> Approval:
    if not isinstance(operation_sha256, str) or len(operation_sha256) != 64 or any((c not in '0123456789abcdef' for c in operation_sha256)):
        raise ContractError('operation must be hash-bound')
    if not isinstance(reviewers, list) or not 1 <= quorum <= 10 or (not isinstance(reason, str)) or (not reason.strip()):
        raise ContractError('invalid approval envelope')
    voters = tuple(sorted(set((identifier(x) for x in reviewers))))
    if len(voters) < quorum or (initiator is not None and initiator in voters):
        raise AuthorizationError('independent approval quorum unmet')
    return Approval(operation_sha256, voters, reason)
