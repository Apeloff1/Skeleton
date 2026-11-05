"""Evidence lineage reporting and stale-source detection."""
from .documents import Document
from ..contracts.errors import ContractError

def lineage(documents: list[Document]) -> dict:
    if not isinstance(documents, list) or len(documents) > 100000:
        raise ContractError('too many documents')
    refs = {}
    for doc in documents:
        if doc.id in refs and refs[doc.id] != doc.sha256:
            raise ContractError('document ID collision')
        refs[doc.id] = doc.sha256
    return {'documents': len(documents), 'hashes': dict(sorted(refs.items())), 'provenance_verified': False}
