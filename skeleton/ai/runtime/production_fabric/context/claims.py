"""Source-qualified claims with bounded promotion and no trust amplification."""
from dataclasses import dataclass
from .documents import Document
from ..contracts.errors import ContractError
from ..contracts.identity import identifier

@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    evidence_ids: tuple[str, ...]
    status: str

def claim(id: str, text: str, documents: list[Document], *, status: str='proposed') -> Claim:
    identifier(id)
    if status not in {'proposed', 'contested', 'verified'} or not isinstance(text, str) or (not text.strip()):
        raise ContractError('invalid claim')
    refs = tuple(sorted({doc.id for doc in documents}))
    if status == 'verified' and (not refs or any((d.trust != 'operator-reviewed' for d in documents))):
        raise ContractError('untrusted documents cannot establish verified claims')
    return Claim(id, text, refs, status)
