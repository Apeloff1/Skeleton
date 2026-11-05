"""Strict bounded JSON input with duplicate-key and non-finite-number rejection."""
from __future__ import annotations
import hashlib
import json
from typing import Any
from .errors import ContractError
MAX_JSON_BYTES = 2000000
MAX_DEPTH = 48
MAX_ITEMS = 100000

def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in items:
        if key in output:
            raise ContractError(f'duplicate object key: {key}')
        output[key] = value
    return output

def _reject_constant(value: str) -> None:
    raise ContractError(f'non-finite number: {value}')

def _bounded(value: Any, depth: int=0, counter: list[int] | None=None) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if depth > MAX_DEPTH or counter[0] > MAX_ITEMS:
        raise ContractError('JSON structure limit exceeded')
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ContractError('non-string object key')
            _bounded(child, depth + 1, counter)
    elif isinstance(value, list):
        for child in value:
            _bounded(child, depth + 1, counter)
    elif isinstance(value, float):
        import math
        if not math.isfinite(value):
            raise ContractError('non-finite float')
    elif value is not None and (not isinstance(value, (str, bool, int))):
        raise ContractError('unsupported JSON type')

def loads(raw: str | bytes, *, max_bytes: int=MAX_JSON_BYTES) -> Any:
    if isinstance(raw, bytes):
        if len(raw) > max_bytes:
            raise ContractError('input exceeds byte limit')
        try:
            raw = raw.decode('utf-8', errors='strict')
        except UnicodeError as exc:
            raise ContractError('invalid UTF-8') from exc
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > max_bytes:
        raise ContractError('invalid or oversized input')
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:
        raise ContractError(f'invalid JSON: {exc}') from exc
    _bounded(value)
    return value

def dumps(value: Any) -> bytes:
    _bounded(value)
    try:
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    except (ValueError, TypeError, RecursionError) as exc:
        raise ContractError(f'noncanonical JSON: {exc}') from exc

def digest(value: Any) -> str:
    return hashlib.sha256(dumps(value)).hexdigest()
