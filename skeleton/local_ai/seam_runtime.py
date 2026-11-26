"""Bounded gate for the numbered local seams.

Each seam still returns ``seam``, ``ok``, and, on acceptance, the caller's
``data``. The gate adds a key count and a canonical SHA-256 so a caller can
see that the payload was checked. Nothing here loads a model, opens a file,
or leaves the process.
"""

from __future__ import annotations

import hashlib
import json
import math
import re

MAX_SEAM = 199
MAX_KEYS = 64
MAX_ITEMS = 64
MAX_DEPTH = 6
MAX_STRING = 2000
MAX_KEY = 128
MAX_INT = 10**12
MAX_BYTES = 16 * 1024
REFUSAL = "payload refused"

_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|secret|password|token|bearer)\b\s*[:=]"
)


class SeamRejected(ValueError):
    """The payload cannot pass the seam gate."""


def screen(data: object) -> dict:
    """Check a payload. A refusal carries no echo of the data."""
    try:
        _check(data, 0)
        if not isinstance(data, dict):
            raise SeamRejected("payload must be a dict")
        encoded = json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except SeamRejected:
        return {"ok": False, "error": REFUSAL}
    raw = encoded.encode("ascii")
    if len(raw) > MAX_BYTES:
        return {"ok": False, "error": REFUSAL}
    return {
        "ok": True,
        "data": data,
        "keys": len(data),
        "digest": hashlib.sha256(raw).hexdigest(),
    }


def apply(seam: int, data: object) -> dict:
    """Check one payload and return the seam record."""
    if type(seam) is not int or not 0 <= seam <= MAX_SEAM:
        raise SeamRejected("seam number is invalid")
    record = screen(data)
    record["seam"] = seam
    return record


def admit(card: str, data: object) -> dict | None:
    """Return a refusal record, or None when the card may publish."""
    if not isinstance(card, str) or not card:
        raise SeamRejected("card name is invalid")
    checked = screen(data)
    if not checked["ok"]:
        return {"ok": False, "error": REFUSAL, "card": card}
    return None


def stamp(card: str, data: object, body: dict) -> dict:
    """Publish a card record bound to the screened payload digest."""
    if not isinstance(card, str) or not card:
        raise SeamRejected("card name is invalid")
    checked = screen(data)
    if not checked["ok"]:
        return {"ok": False, "error": REFUSAL, "card": card}
    record: dict = {
        "ok": True,
        "card": card,
        "keys": checked["keys"],
        "digest": checked["digest"],
    }
    for key, value in body.items():
        if key in record:
            raise SeamRejected("card field collides with the gate")
        if isinstance(value, list):
            record[key] = list(value)
        elif isinstance(value, dict):
            record[key] = dict(value)
        else:
            record[key] = value
    return record


def _check(value: object, depth: int) -> None:
    if depth > MAX_DEPTH:
        raise SeamRejected("payload is too deep")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) > MAX_INT:
            raise SeamRejected("payload number is invalid")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SeamRejected("payload number is invalid")
        return
    if isinstance(value, str):
        if len(value) > MAX_STRING:
            raise SeamRejected("payload string is too long")
        if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value):
            raise SeamRejected("payload contains a control character")
        if _SECRET.search(value):
            raise SeamRejected("payload contains a secret")
        return
    if isinstance(value, list):
        if len(value) > MAX_ITEMS:
            raise SeamRejected("payload list is too long")
        for item in value:
            _check(item, depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_KEYS:
            raise SeamRejected("payload has too many keys")
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > MAX_KEY:
                raise SeamRejected("payload key is invalid")
            if _SECRET.search(key):
                raise SeamRejected("payload contains a secret")
            _check(item, depth + 1)
        return
    raise SeamRejected("payload type is refused")
