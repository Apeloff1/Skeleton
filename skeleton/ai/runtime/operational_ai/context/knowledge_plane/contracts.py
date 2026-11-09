"""Validated knowledge contracts; all dangerous inputs are bounded at entry."""
from __future__ import annotations
from dataclasses import dataclass
import re
from ...orchestration.execution_spine.contracts import identifier, hexdigest

_ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
_ALLOWED_RIGHTS = frozenset(('operator-authored', 'operator-licensed', 'public-domain'))
_ALLOWED_KINDS = frozenset(('text/plain', 'text/markdown', 'application/json', 'text/x-python'))

class KnowledgeError(RuntimeError):
    """Integrity, ownership, policy or source admission refusal."""


@dataclass(frozen=True, slots=True)
class KnowledgePolicy:
    max_document_bytes: int = 2 * 1024 * 1024
    max_documents: int = 2048
    max_total_bytes: int = 128 * 1024 * 1024
    max_chunks: int = 4096
    chunk_characters: int = 448
    chunk_overlap: int = 64
    max_hits: int = 6
    max_query_chars: int = 2048
    max_query_terms: int = 12
    max_title_chars: int = 160
    max_revisions: int = 64
    max_scan_rows: int = 65536

    def __post_init__(self) -> None:
        ranges = {
            'max_document_bytes': (1024, 16 * 1024 * 1024),
            'max_documents': (1, 100000),
            'max_total_bytes': (1024, 1024 * 1024 * 1024),
            'max_chunks': (1, 100000),
            'chunk_characters': (64, 4096),
            'chunk_overlap': (0, 1024),
            'max_hits': (1, 32),
            'max_query_chars': (1, 16384),
            'max_query_terms': (1, 64),
            'max_title_chars': (8, 512),
            'max_revisions': (1, 512),
            'max_scan_rows': (1, 1000000),
        }
        for field, (low, high) in ranges.items():
            value = getattr(self, field)
            if type(value) is not int or not low <= value <= high:
                raise KnowledgeError('invalid knowledge policy ' + field)
        if self.chunk_overlap * 2 >= self.chunk_characters:
            raise KnowledgeError('knowledge overlap must be less than half the chunk')
        if self.max_document_bytes > self.max_total_bytes:
            raise KnowledgeError('single document budget exceeds total corpus budget')


def document_id(value: str) -> str:
    try:
        return identifier(value, 'knowledge document')
    except Exception as exc:
        raise KnowledgeError('invalid document identifier') from exc


def source_path(value: str) -> str:
    if (type(value) is not str or len(value) > 512 or not value or '\\' in value
        or value.startswith('/') or value.startswith('-') or value.startswith('~')
        or any(c in value for c in ('\x00', '\r', '\n'))
        or any(part in ('', '.', '..') or part.startswith('.') for part in value.split('/'))):
        raise KnowledgeError('unsafe source-relative path')
    return value


def rights_tag(value: str) -> str:
    if type(value) is not str or value not in _ALLOWED_RIGHTS:
        raise KnowledgeError('source rights not independently approved')
    return value


def content_type(value: str) -> str:
    if type(value) is not str or value not in _ALLOWED_KINDS:
        raise KnowledgeError('unsupported source content type')
    return value


def title_text(value: str, *, policy: KnowledgePolicy) -> str:
    if (type(value) is not str or not value.strip()
        or len(value) > policy.max_title_chars or any(ord(c) < 32 for c in value)):
        raise KnowledgeError('invalid document title')
    return value


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    document_id: str
    revision: int
    document_sha256: str
    bytes: int
    chunks: int
    title: str
    rights: str
    active: bool
    content_type: str

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class SearchResult:
    source_id: str
    document_id: str
    revision: int
    document_sha256: str
    title: str
    char_start: int
    char_end: int
    passage: str
    passage_sha256: str
    rights: str
    score: float

    def __post_init__(self) -> None:
        document_id(self.document_id)
        identifier(self.source_id, 'knowledge source')
        hexdigest(self.document_sha256)
        hexdigest(self.passage_sha256)
        if type(self.revision) is not int or self.revision < 1:
            raise KnowledgeError('invalid retrieved revision')
        if type(self.char_start) is not int or type(self.char_end) is not int or self.char_end - self.char_start != len(self.passage):
            raise KnowledgeError('retrieved passage coordinate mismatch')

    def to_dict(self, *, include_text: bool = False) -> dict:
        result = {name: getattr(self, name) for name in self.__dataclass_fields__ if name != 'passage'}
        if include_text:
            result['passage'] = self.passage
        return result
