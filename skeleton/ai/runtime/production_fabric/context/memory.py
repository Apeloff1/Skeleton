"""Scope-separated append-only user/world memory with explicit provenance."""
from dataclasses import dataclass
from ..contracts.identity import identifier
from ..contracts.canonical import digest
from ..contracts.errors import ContractError

@dataclass(frozen=True)
class Memory:
    scope: str
    key: str
    value: str
    evidence: str
    revision: int
    sha256: str

class MemoryBook:

    def __init__(self):
        self._entries: dict[tuple[str, str], list[Memory]] = {}

    def append(self, scope: str, key: str, value: str, evidence: str) -> Memory:
        identifier(scope)
        identifier(key)
        if not isinstance(value, str) or not 1 <= len(value) <= 16384 or (not isinstance(evidence, str)) or (not evidence):
            raise ContractError('memory requires bounded content and evidence')
        old = self._entries.get((scope, key), [])
        revision = len(old) + 1
        memory = Memory(scope, key, value, evidence, revision, digest({'scope': scope, 'key': key, 'value': value, 'evidence': evidence, 'revision': revision}))
        self._entries.setdefault((scope, key), []).append(memory)
        return memory

    def read(self, scope: str, key: str) -> Memory | None:
        identifier(scope)
        identifier(key)
        history = self._entries.get((scope, key), [])
        return history[-1] if history else None

    def history(self, scope: str, key: str) -> tuple[Memory, ...]:
        identifier(scope)
        identifier(key)
        return tuple(self._entries.get((scope, key), []))
