"""Stable citation handles referencing exact source digests, not generated evidence."""
from .documents import Document
from ..contracts.errors import ContractError

def cite(document: Document, start: int, end: int) -> dict:
    if type(start) is not int or type(end) is not int or (not 0 <= start < end <= len(document.text)):
        raise ContractError('invalid citation offset')
    return {'id': document.id, 'sha256': document.sha256, 'source': document.source, 'span': [start, end], 'excerpt': document.text[start:end], 'trust': document.trust}
