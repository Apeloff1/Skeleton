"""Explicit tri-state values and schema compatibility fences."""
from dataclasses import dataclass
from typing import Any
from .errors import ContractError

@dataclass(frozen=True)
class Field:
    present: bool
    value: Any = None

def field(mapping: dict, key: str) -> Field:
    if not isinstance(mapping, dict) or not isinstance(key, str):
        raise ContractError('invalid field lookup')
    return Field(key in mapping, mapping.get(key))

def require_version(record: dict, version: int=1) -> dict:
    if not isinstance(record, dict) or type(record.get('schema_version')) is not int or record['schema_version'] != version:
        raise ContractError('unsupported schema version')
    return record

def exact_fields(record: dict, fields: set[str]) -> dict:
    if not isinstance(record, dict) or set(record) != fields:
        raise ContractError(f"unexpected or missing contract fields: {(set(record) if isinstance(record, dict) else 'not object')}")
    return record
