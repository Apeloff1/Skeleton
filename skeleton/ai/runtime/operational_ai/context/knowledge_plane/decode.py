"""Strict document decoding with no binary/HTML/PDF magic bypass."""
from __future__ import annotations
import json
import unicodedata
from .contracts import KnowledgeError, content_type


def decode_source(data: bytes, kind: str) -> str:
    content_type(kind)
    if type(data) is not bytes or not data:
        raise KnowledgeError('document bytes required')
    if data[:4] in (b'GGUF', b'PK\x03\x04', b'%PDF', b'\x7fELF'):
        raise KnowledgeError('binary or archive is not a source document')
    try:
        text = data.decode('utf-8', errors='strict')
    except UnicodeError as exc:
        raise KnowledgeError('document is not strict UTF-8') from exc
    if any(ch == '\x00' or (ord(ch) < 32 and ch not in '\n\t\r') for ch in text):
        raise KnowledgeError('document contains forbidden control characters')
    if '<!doctype html' in text.lower()[:256] or '<html' in text.lower()[:256]:
        raise KnowledgeError('active HTML cannot enter passive knowledge corpus')
    if kind == 'application/json':
        def unique(pairs):
            out = {}
            for key, value in pairs:
                if key in out: raise KnowledgeError('duplicate JSON source keys')
                out[key] = value
            return out
        def reject_constant(value):
            raise KnowledgeError('nonfinite JSON source number')
        try:
            obj = json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant)
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise KnowledgeError('invalid JSON source') from exc
        if type(obj) not in (dict, list):
            raise KnowledgeError('JSON source must be an object or array')
    if not text.strip(): raise KnowledgeError('document is blank')
    # Normalize newline only when the original digest remains bound to raw bytes;
    # output excerpts must have coordinates into this normalized stored document.
    return text.replace('\r\n','\n').replace('\r','\n')
