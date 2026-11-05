"""Least-authority grants created by an operator policy, never inferred from text."""
from dataclasses import dataclass
from ..contracts.errors import ContractError, AuthorizationError
from ..contracts.identity import identifier

@dataclass(frozen=True)
class Grant:
    principal: str
    scopes: frozenset[str]
    expires_at: int
    issuer: str

    def check(self, scope: str, logical_time: int) -> bool:
        identifier(scope)
        if type(logical_time) is not int or logical_time < 0 or logical_time >= self.expires_at or (scope not in self.scopes):
            raise AuthorizationError('scope denied or grant expired')
        return True

    def attenuate(self, scopes: set[str], expires_at: int) -> 'Grant':
        if not scopes.issubset(self.scopes) or not 0 < expires_at <= self.expires_at:
            raise AuthorizationError('child would exceed parent authority')
        return Grant(self.principal, frozenset(scopes), expires_at, self.issuer)

def issue(*, principal: str, scopes: set[str], expires_at: int, issuer: str, operator_authorized: bool=False) -> Grant:
    identifier(principal)
    identifier(issuer)
    if not operator_authorized:
        raise AuthorizationError('operator authorization required')
    if not isinstance(scopes, set) or not scopes or len(scopes) > 64 or (type(expires_at) is not int) or (expires_at <= 0):
        raise ContractError('invalid authority grant')
    for scope in scopes:
        identifier(scope)
    return Grant(principal, frozenset(scopes), expires_at, issuer)
