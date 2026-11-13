"""Immutable source-bound operation receipts; digests do not claim authorization."""
from dataclasses import dataclass
from .canonical import digest
from .errors import ContractError
from .identity import identifier

@dataclass(frozen=True)
class Receipt:
    operation: str
    input_sha256: str
    output_sha256: str
    revision: int
    status: str

    def to_data(self) -> dict:
        return {'operation': self.operation, 'input_sha256': self.input_sha256, 'output_sha256': self.output_sha256, 'revision': self.revision, 'status': self.status}

def receipt(operation: str, source: dict, result: dict, revision: int, *, status: str='committed') -> Receipt:
    identifier(operation)
    if status not in {'committed', 'denied', 'abstained', 'failed'} or not isinstance(revision, int) or revision < 0:
        raise ContractError('invalid receipt metadata')
    return Receipt(operation, digest(source), digest(result), revision, status)
