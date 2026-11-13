"""Deterministic bounded portable replay exports without system secrets."""
from ..contracts.canonical import digest, dumps, loads
from ..contracts.errors import IntegrityError, ContractError
from .journal import Journal

def export_stream(journal: Journal, stream: str, limit: int=10000) -> bytes:
    entries = journal.replay(stream, max_events=limit)
    payload = {'schema_version': 1, 'stream': stream, 'events': entries, 'head': list(journal.head(stream))}
    return dumps({'payload': payload, 'sha256': digest(payload)})

def validate_export(raw: bytes, *, max_bytes: int=10000000) -> dict:
    value = loads(raw, max_bytes=max_bytes)
    if not isinstance(value, dict) or set(value) != {'payload', 'sha256'} or digest(value['payload']) != value['sha256']:
        raise IntegrityError('invalid portable stream export')
    payload = value['payload']
    if payload.get('schema_version') != 1 or not isinstance(payload.get('events'), list):
        raise ContractError('unsupported export schema')
    return payload
