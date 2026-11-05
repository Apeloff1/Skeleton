"""Pure structured policy decisions independent of model-generated assertions."""
from dataclasses import dataclass
from .authority import Grant
from ..contracts.errors import ContractError, AuthorizationError

@dataclass(frozen=True)
class Decision:
    permitted: bool
    reason: str
    requires_approval: bool

def decide(grant: Grant | None, scope: str, logical_time: int, *, risk: str, approval: bool=False) -> Decision:
    if risk not in {'read', 'write', 'external'}:
        raise ContractError('unknown risk classification')
    try:
        if grant is None:
            raise AuthorizationError('no grant')
        grant.check(scope, logical_time)
    except (AuthorizationError, ContractError):
        return Decision(False, 'missing-authority', False)
    if risk == 'external' and (not approval):
        return Decision(False, 'external-approval-required', True)
    return Decision(True, 'policy-allow', False)
