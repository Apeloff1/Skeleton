"""Instruction/data trust boundary for retrieval, tools, models and collaborators."""
from dataclasses import dataclass
from ..contracts.errors import AuthorizationError, ContractError

@dataclass(frozen=True)
class Material:
    text: str
    origin: str
    trust: str

    def instruction(self) -> str:
        if self.trust != 'system':
            raise AuthorizationError('untrusted content has no instruction authority')
        return self.text

def material(text: str, origin: str, trust: str='external') -> Material:
    if trust not in {'system', 'operator', 'external', 'model', 'tool'} or not isinstance(text, str) or len(text) > 1000000 or (not isinstance(origin, str)) or (not origin):
        raise ContractError('invalid trust boundary input')
    return Material(text, origin, trust)
