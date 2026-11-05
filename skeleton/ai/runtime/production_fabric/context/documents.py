"""Source-bound evidence documents with explicit provenance and trust labels."""
from dataclasses import dataclass
from ..contracts.errors import ContractError
from ..contracts.identity import identifier
from ..contracts.canonical import digest

@dataclass(frozen=True)
class Document:
    id: str
    text: str
    source: str
    trust: str
    sha256: str

def document(id: str, text: str, source: str, trust: str='untrusted') -> Document:
    identifier(id)
    if trust not in {'untrusted', 'operator-reviewed', 'system-authored'}:
        raise ContractError('unknown evidence trust label')
    if not isinstance(text, str) or not 1 <= len(text) <= 250000 or (not isinstance(source, str)) or (not 1 <= len(source) <= 256):
        raise ContractError('invalid document content/source')
    return Document(id, text, source, trust, digest({'text': text, 'source': source, 'trust': trust}))
