"""Fail-closed checks for paths whose meaning changes after percent decoding."""

from __future__ import annotations

import re
from urllib.parse import unquote_to_bytes


class DecodedPathError(ValueError):
    """Raised when percent decoding changes path security semantics."""


_PERCENT_ESCAPE = re.compile(r"%(?:[0-9A-Fa-f]{2})")
_DRIVE = re.compile(r"^[A-Za-z]:")


def _decode_once(value: str) -> str:
    try:
        return unquote_to_bytes(value).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DecodedPathError("percent-encoded path is not valid UTF-8") from exc


def _structural_signature(value: str) -> tuple[bool, bool, bool, tuple[str, ...]]:
    normalized = value.replace("\\", "/")
    parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
    absolute = (
        normalized.startswith("/")
        or normalized.startswith("//")
        or normalized.startswith("~")
        or _DRIVE.match(normalized) is not None
    )
    has_parent = any(part == ".." for part in parts)
    has_nul = "\x00" in normalized
    return absolute, has_parent, has_nul, parts


def reject_decoded_path_ambiguity(value: str, *, max_rounds: int = 4) -> str:
    """Reject paths that become structurally dangerous after URL decoding.

    Filesystem APIs in this repository expect already-decoded logical paths.
    A later web/framework decode must therefore never be able to reveal a new
    separator, parent segment, absolute path, drive prefix, or NUL byte.
    Nested encodings are peeled up to a bounded depth; encodings that remain
    transformable beyond that bound fail closed.
    """
    if not isinstance(value, str):
        raise DecodedPathError("path must be text")
    if max_rounds <= 0:
        raise ValueError("max_rounds must be positive")

    current = value
    for _ in range(max_rounds):
        if _PERCENT_ESCAPE.search(current) is None:
            return value
        decoded = _decode_once(current)
        if decoded == current:
            return value

        before_norm = current.replace("\\", "/")
        after_norm = decoded.replace("\\", "/")
        before_sig = _structural_signature(current)
        after_sig = _structural_signature(decoded)

        introduced_separator = after_norm.count("/") > before_norm.count("/")
        introduced_backslash = "\\" in decoded and "\\" not in current
        if (
            introduced_separator
            or introduced_backslash
            or after_sig[0]
            or after_sig[1]
            or after_sig[2]
        ):
            raise DecodedPathError(
                "percent decoding changes path structure or reveals traversal"
            )
        current = decoded

    if _PERCENT_ESCAPE.search(current) is not None and _decode_once(current) != current:
        raise DecodedPathError("percent-encoded path nesting exceeds safety bound")
    return value


__all__ = ["DecodedPathError", "reject_decoded_path_ambiguity"]
