"""Deterministic scoped identifiers and collision-resistant content receipts."""
import hashlib
import re
from .errors import ContractError
_ID = re.compile('^[a-z][a-z0-9_-]{0,63}$')

def identifier(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ContractError('identifier must be lower-case ASCII and <=64 characters')
    return value

def scoped(namespace: str, name: str) -> str:
    return f'{identifier(namespace)}:{identifier(name)}'

def receipt(namespace: str, payload: bytes) -> str:
    identifier(namespace)
    if not isinstance(payload, bytes):
        raise ContractError('receipt input must be bytes')
    return f"{namespace}-{hashlib.sha256(namespace.encode() + b':' + payload).hexdigest()}"

def namespace_member(value: str, expected: str) -> str:
    prefix = identifier(expected) + ':'
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ContractError('foreign identifier namespace')
    identifier(value[len(prefix):])
    return value
