"""Publish-path secret guard for realtime payloads (repo rule #3637).

Realtime payloads fan out to every subscriber and sit in the replay buffer,
so they must never carry secrets or tokens. The guard reuses the shared
telemetry redaction (``skeleton.observability.redaction``) for sensitive keys
and inline ``key=value`` credentials, then the sandbox credential patterns
(GitHub/OpenAI/AWS/Slack/JWT/PEM/bearer) for free-standing token shapes.

Hardening (Jenkins S2-3, #4128 review):

* key names are normalised (case-insensitive; camelCase, kebab-case and
  snake_case collapse to ``snake_case``) and matched on *substring tokens*
  (``token``, ``secret``, ``password`` ...), so ``accessToken``,
  ``aws_secret_access_key`` and ``X-Session-Id`` are all caught;
* string values that hold JSON objects/arrays are parsed and scanned
  recursively (a scrubbed value is re-serialised);
* percent-encoded and base64-looking values are decoded, interleaved, in
  one bounded loop (max 3 layers); a value that still decodes past the bound
  is redacted whole (refused in reject mode). Decoding happens before the credential
  patterns run; a hit replaces the whole encoded value;
* non-string scalars (``int``, ``float``, ``bool``) are scanned by their
  ``str()`` form; any other non-JSON-native type is refused with
  :class:`RealtimeSecretError` rather than being stringified later.

``mode="redact"`` (default) replaces offending values and reports how many
were scrubbed; ``mode="reject"`` refuses the publish instead.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
from html import unescape as html_unescape
from collections.abc import Mapping
from typing import Any, Optional, Tuple
from urllib.parse import unquote

from skeleton.observability.redaction import REDACTED, SENSITIVE_KEYS, redact_text

# Realtime-specific additions on top of the shared telemetry key set.
EXTRA_SENSITIVE_KEYS = frozenset(
    {
        "seal",
        "x_gf_seal",
        "gf_seal_secret",
        "private_key",
        "id_token",
        "session_token",
        "bearer",
        "auth_token",
        "github_token",
        "service_token",
    }
)
#: Substring tokens: a normalised key containing any of these is sensitive.
SENSITIVE_KEY_TOKENS: Tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "authorization",
    "cookie",
    "session",
    "credential",
    "seal",
    "bearer",
)
_KEYS = frozenset(SENSITIVE_KEYS) | EXTRA_SENSITIVE_KEYS
_MAX_DEPTH = 8
_MAX_DECODE_CHARS = 16_384
_CAMEL_1 = re.compile(r"([A-Z]+)([A-Z][a-z])")
_CAMEL_2 = re.compile(r"([a-z0-9])([A-Z])")
_SEP = re.compile(r"[^a-z0-9]+")
_B64_RE = re.compile(r"^[A-Za-z0-9+/_-]{16,}={0,2}$")
_PCT_RE = re.compile(r"%[0-9A-Fa-f]{2}")
# Character references can encode a credential a byte at a time.
_ENTITY_RE = re.compile(r"&(?:\#(?:[xX][0-9A-Fa-f]+|[0-9]+)|[A-Za-z][A-Za-z0-9]+);?")
#: Max percent-decode rounds (``%253D`` -> ``%3D`` -> ``=``); decode stops
#: early at a fixpoint (Jenkins #4253 review, blocker 1).
_MAX_DECODE_ROUNDS = 3
#: Realtime-local token-prefix shapes with *no* leading ``\b`` so a token glued
#: to a preceding alphanumeric (``xghp_...``, ``tokenghp_...``) still matches.
_TOKEN_PREFIX_PATTERNS: Tuple[Any, ...] = (
    re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})"),
    # sk- keeps a leading boundary: ``ask-...`` / ``risk-...`` are prose.
    re.compile(r"(?<![A-Za-z0-9])sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
)


class RealtimeSecretError(ValueError):
    """A payload contained secret material (reject mode) or a non-JSON value."""


def _normalize_key(key: object) -> str:
    """``accessToken`` / ``Access-Token`` / ``ACCESS_TOKEN`` -> ``access_token``."""
    text = str(key).strip()
    text = _CAMEL_2.sub(r"\1_\2", _CAMEL_1.sub(r"\1_\2", text))
    return _SEP.sub("_", text.lower()).strip("_")


def is_sensitive_key(key: object) -> bool:
    norm = _normalize_key(key)
    if norm in _KEYS:
        return True
    squashed = norm.replace("_", "")
    for token in SENSITIVE_KEY_TOKENS:
        if token in norm or token.replace("_", "") in squashed:
            return True
    return False


def _patterns_hit(value: str) -> Tuple[str, int]:
    from skeleton.sandbox.sanitizers import redact_secrets

    cleaned = redact_text(value)
    hits = 1 if cleaned != value else 0
    try:
        cleaned2, kinds = redact_secrets(cleaned)
    except Exception:  # oversized text: fail closed rather than leak
        return REDACTED, 1
    if kinds and cleaned2 != cleaned:
        hits += len(kinds)
    for pattern in _TOKEN_PREFIX_PATTERNS:
        cleaned2, n = pattern.subn(REDACTED, cleaned2)
        hits += n
    return cleaned2, hits


def _b64_step(value: str) -> Optional[str]:
    compact = value.strip()
    if not _B64_RE.match(compact):
        return None
    padded = compact + "=" * (-len(compact) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            raw = decoder(padded)
        except (binascii.Error, ValueError):
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if text and text.isprintable() and text != value:
            return text
    return None


def _decode_step(value: str) -> Optional[str]:
    """One decode layer (percent first, else base64), or ``None`` at a fixpoint."""
    if _PCT_RE.search(value):
        decoded = unquote(value)
        if decoded != value:
            return decoded
    if _ENTITY_RE.search(value):
        decoded = html_unescape(value)
        if decoded != value:
            return decoded
    return _b64_step(value)


def _decode_chain(value: str) -> Tuple[list, bool]:
    """Interleaved percent/base64 decode layers of ``value``, bounded.

    Returns ``(variants, exhausted)``; ``exhausted`` is ``True`` when the value
    still decodes after :data:`_MAX_DECODE_ROUNDS` layers, or is too large to
    decode. Such values are never stored in cleartext (Jenkins #4253 review).
    """
    out: list = []
    if len(value) > _MAX_DECODE_CHARS:
        # Decoding or recursively inspecting an oversized value is unsafe:
        # fail closed even when its encoding is not recognisable.
        return out, True
    current = value
    for _ in range(_MAX_DECODE_ROUNDS):
        nxt = _decode_step(current)
        if nxt is None:
            return out, False
        out.append(nxt)
        current = nxt
    return out, _decode_step(current) is not None


def _decoded_variants(value: str) -> list:
    """Decoded forms of ``value`` worth re-scanning (see :func:`_decode_chain`)."""
    return _decode_chain(value)[0]


class PayloadSecretGuard:
    """Scrub (or reject) secret material before an event is stored."""

    def __init__(self, mode: str = "redact") -> None:
        if mode not in ("redact", "reject"):
            raise ValueError("mode must be 'redact' or 'reject'")
        self.mode = mode

    def scrub(self, payload: Mapping[str, Any]) -> Tuple[dict, int]:
        """Return ``(clean_payload, redaction_count)``.

        Raises :class:`RealtimeSecretError` for non-JSON-native values, and in
        reject mode whenever anything would have been redacted.
        """
        hits = 0

        def scan_text(item: str, depth: int) -> str:
            nonlocal hits
            stripped = item.strip()
            if stripped[:1] in ("{", "[") and depth + 1 >= _MAX_DEPTH:
                hits += 1
                return REDACTED
            if stripped[:1] in ("{", "[") and depth + 1 < _MAX_DEPTH:
                try:
                    embedded = json.loads(stripped)
                except ValueError:
                    embedded = None
                if isinstance(embedded, (dict, list)):
                    before = hits
                    cleaned_obj = visit(embedded, depth + 1)
                    if hits != before:
                        return json.dumps(
                            cleaned_obj, separators=(",", ":"), sort_keys=True
                        )
                    return item
            cleaned, n = _patterns_hit(item)
            if n:
                hits += n
                return cleaned
            variants, exhausted = _decode_chain(item)
            if exhausted:
                # Still changing after the decode bound: never store as-is.
                hits += 1
                return REDACTED
            for variant in variants:
                if variant.strip()[:1] in ("{", "["):
                    if depth + 1 >= _MAX_DEPTH:
                        hits += 1
                        return REDACTED
                    before = hits
                    scan_text(variant, depth + 1)
                    if hits != before:
                        return REDACTED
                _, n = _patterns_hit(variant)
                if n:
                    hits += n
                    return REDACTED
            return item

        def visit(item: Any, depth: int) -> Any:
            nonlocal hits
            if depth >= _MAX_DEPTH:
                # Truncation is a security decision, not a clean payload.
                # Count it so reject mode never publishes unchecked subtrees.
                hits += 1
                return REDACTED
            if item is None:
                return None
            if isinstance(item, str):
                return scan_text(item, depth)
            if isinstance(item, bool):
                return item
            if isinstance(item, (int, float)):
                if isinstance(item, float) and not math.isfinite(item):
                    hits += 1
                    return REDACTED
                _, n = _patterns_hit(str(item))
                if n:
                    hits += n
                    return REDACTED
                return item
            if isinstance(item, Mapping):
                if not isinstance(item, dict):
                    raise RealtimeSecretError(
                        "payload mappings must be JSON-native dictionaries"
                    )
                out = {}
                for key, child in item.items():
                    if not isinstance(key, str):
                        raise RealtimeSecretError(
                            f"payload keys must be strings, got {type(key).__name__}"
                        )
                    if is_sensitive_key(key):
                        # Avoid invoking user-defined equality on untrusted values.
                        if child is not None and not (isinstance(child, str) and child in ("", REDACTED)):
                            hits += 1
                        out[key] = REDACTED
                    else:
                        out[key] = visit(child, depth + 1)
                return out
            if isinstance(item, list):
                return [visit(child, depth + 1) for child in item]
            raise RealtimeSecretError(
                f"payload value of type {type(item).__name__} is not JSON-native; convert it before publishing"
            )

        if not isinstance(payload, dict):
            raise RealtimeSecretError("realtime payload must be a JSON-native dictionary")
        clean = visit(payload, 0)
        if hits and self.mode == "reject":
            raise RealtimeSecretError(
                f"payload carried {hits} secret value(s); publish refused"
            )
        return clean, hits


__all__ = [
    "EXTRA_SENSITIVE_KEYS",
    "PayloadSecretGuard",
    "RealtimeSecretError",
    "SENSITIVE_KEY_TOKENS",
    "is_sensitive_key",
]
