"""Safe canonical data and digest bindings shared with the native candidate source."""
from __future__ import annotations
from .errors import refuse
from ..native_candidate.strict import digest, bytes_sha as bytes_sha


def required_sha(value: object, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(
        c not in "0123456789abcdef" for c in value
    ):
        refuse("invalid-" + label)
    return value


def required_id(value: object, label: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 96 or
            value[0] not in "abcdefghijklmnopqrstuvwxyz" or
            any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in value)):
        refuse("invalid-" + label)
    return value


def required_int(value: object, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        refuse("invalid-" + label)
    return value


def source_digest(records: list[dict]) -> str:
    if type(records) is not list or len(records) > 576:
        refuse("invalid-source-set")
    return digest(records)
