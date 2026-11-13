"""Nonmalleable, size-bounded registry serialization and integrity digests."""
from __future__ import annotations
import hashlib
import json
from .contracts import AdmissionCorrupt


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AdmissionCorrupt('duplicate registry JSON key')
        result[key] = value
    return result


def canonical(value: object, *, maximum: int = 16_384) -> bytes:
    try:
        data = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                          separators=(',', ':')).encode('ascii')
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise AdmissionCorrupt('noncanonical model registry value') from exc
    if not 1 <= len(data) <= maximum:
        raise AdmissionCorrupt('model registry entry exceeds size budget')
    return data


def parse(data: bytes, *, maximum: int = 16_384):
    if type(data) is not bytes or not 1 <= len(data) <= maximum:
        raise AdmissionCorrupt('invalid model registry record size')
    try:
        decoded = json.loads(data.decode('ascii'), object_pairs_hook=_no_duplicates,
                             parse_constant=lambda _: (_ for _ in ()).throw(AdmissionCorrupt('nonfinite model registry value')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise AdmissionCorrupt('model registry JSON is corrupt') from exc
    if type(decoded) is not dict or canonical(decoded, maximum=maximum) != data:
        raise AdmissionCorrupt('noncanonical model registry bytes')
    return decoded


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()
