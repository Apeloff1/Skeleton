"""Bounded deterministic JSON evidence for trusted local workflows."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat

HEX = re.compile(r"[a-f0-9]{64}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
MAX_BYTES = 8 * 1024 * 1024


class EvidenceError(ValueError):
    pass


def identifier(value):
    if type(value) is not str or not ID.fullmatch(value):
        raise EvidenceError("invalid identifier")
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise EvidenceError("integer outside bound")
    return value


def text(value, limit=400):
    if type(value) is not str or not 1 <= len(value) <= limit or any(
        ord(ch) < 32 or ord(ch) == 127 for ch in value
    ):
        raise EvidenceError("invalid text")
    return value


def fields(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise EvidenceError("unexpected object fields")
    return value


def array(value, low, high):
    if type(value) is not list or not low <= len(value) <= high:
        raise EvidenceError("array outside bound")
    return value


def canonical(value):
    try:
        raw = json.dumps(value, ensure_ascii=True, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise EvidenceError("invalid JSON") from exc
    if len(raw) > MAX_BYTES:
        raise EvidenceError("evidence byte ceiling")
    return raw


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def pin(actual, expected):
    if type(expected) is not str or not HEX.fullmatch(expected):
        raise EvidenceError("independent SHA-256 required")
    if not hmac.compare_digest(actual, expected):
        raise EvidenceError("independent SHA-256 mismatch")


def seal(body):
    if "digest" in body:
        raise EvidenceError("reserved digest field")
    return {**body, "digest": digest(body)}


def verify(value, expected):
    if type(value) is not dict:
        raise EvidenceError("sealed object required")
    pin(digest({k: v for k, v in value.items() if k != "digest"}), value.get("digest"))
    pin(value["digest"], expected)


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError("duplicate property")
        out[key] = value
    return out


def _reject(_):
    raise EvidenceError("nonfinite number")


def parse(raw):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise EvidenceError("input byte ceiling")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject)
        stack, count = [(value, 0)], 0
        while stack:
            item, depth = stack.pop()
            count += 1
            if count > 200_000 or depth > 48:
                raise EvidenceError("tree ceiling")
            if type(item) is dict:
                stack.extend((v, depth+1) for v in item.values())
            elif type(item) is list:
                stack.extend((v, depth+1) for v in item)
        canonical(value)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise EvidenceError("invalid bounded document") from exc
    if type(value) is not dict:
        raise EvidenceError("object required")
    return value


def read_document(path):
    """Read one stable regular file; not a hostile-parent directory sandbox."""
    path = Path(path)
    def identity(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
    fd = None
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise EvidenceError("unsafe input file")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or identity(opened) != identity(before):
            raise EvidenceError("source changed before read")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(MAX_BYTES+1)
        if (len(raw) != opened.st_size or len(raw) > MAX_BYTES
                or identity(os.fstat(fd)) != identity(opened)
                or identity(path.lstat()) != identity(opened)):
            raise EvidenceError("source changed during read")
        return parse(raw), hashlib.sha256(raw).hexdigest()
    except OSError as exc:
        raise EvidenceError("source read rejected") from exc
    finally:
        if fd is not None:
            os.close(fd)
