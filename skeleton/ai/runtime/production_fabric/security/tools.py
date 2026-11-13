"""Explicitly registered callbacks with scope/risk policy and no dynamic import."""
from collections.abc import Callable
from .authority import Grant
from .policy import decide
from ..contracts.errors import AuthorizationError, ContractError
from ..contracts.identity import identifier
from ..contracts.canonical import dumps

class Tools:

    def __init__(self):
        self._tools: dict[str, tuple[Callable, str, str]] = {}

    def register(self, name: str, callback: Callable, scope: str, *, risk: str='read') -> None:
        identifier(name)
        identifier(scope)
        if not callable(callback) or name in self._tools or risk not in {'read', 'write', 'external'}:
            raise ContractError('invalid tool registration')
        self._tools[name] = (callback, scope, risk)

    def call(self, name: str, payload: dict, grant: Grant | None, logical_time: int, *, approved: bool=False) -> dict:
        identifier(name)
        dumps(payload)
        if name not in self._tools:
            raise AuthorizationError('unregistered tool')
        callback, scope, risk = self._tools[name]
        decision = decide(grant, scope, logical_time, risk=risk, approval=approved)
        if not decision.permitted:
            raise AuthorizationError(decision.reason)
        value = callback(dict(payload))
        if not isinstance(value, dict):
            raise ContractError('tool result must be JSON object')
        dumps(value)
        return value
