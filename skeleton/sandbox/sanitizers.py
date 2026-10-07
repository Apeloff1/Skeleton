"""Sanitizers for untrusted text and structured data (B086).

All functions are pure and bounded.  They *normalise* rather than reject
where safe (stripping invisible/control characters, escaping markup) and
raise :class:`~.errors.SanitizerError` only when input cannot be made safe
(too large, too deep, wrong type).
"""
from __future__ import annotations

import html
import json
import re
import shlex
import unicodedata
from collections.abc import Mapping
from typing import Any

from .errors import SanitizerError

MAX_TEXT_CHARS = 1_000_000
MAX_JSON_DEPTH = 64
MAX_JSON_ITEMS = 100_000

# Bidi overrides/isolates ("Trojan Source"), zero-width and other invisibles.
BIDI_CONTROLS = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u200e\u200f\u061c")
INVISIBLES = frozenset("\u200b\u200c\u200d\u2060\u2061\u2062\u2063\u2064\ufeff\u00ad\u180e")
_ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[PX^_][^\x1b]*\x1b\\|[@-Z\\-_])")
_TAG_CHARS = range(0xE0000, 0xE0080)  # Unicode "tag" block used for hidden prompt smuggling

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}=*")),
    ("assignment", re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?[^\s'\"]{6,}")),
)


def _require_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        raise SanitizerError("expected text", context={"type": type(value).__name__})
    if len(value) > limit:
        raise SanitizerError("text too large", context={"length": len(value), "limit": limit})
    return value


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def sanitize_text(
    text: str,
    *,
    limit: int = MAX_TEXT_CHARS,
    keep_newlines: bool = True,
    normalize: str | None = "NFC",
) -> str:
    """Remove ANSI escapes, C0/C1 controls, bidi controls, invisibles, tag chars."""
    s = strip_ansi(_require_text(text, limit))
    out = []
    for ch in s:
        o = ord(ch)
        if ch in ("\n", "\t") and keep_newlines:
            out.append(ch)
        elif ch == "\r":
            continue
        elif o < 32 or 127 <= o < 160:
            continue
        elif ch in BIDI_CONTROLS or ch in INVISIBLES or o in _TAG_CHARS:
            continue
        elif 0xD800 <= o <= 0xDFFF:
            out.append("\ufffd")
        else:
            out.append(ch)
    result = "".join(out)
    return unicodedata.normalize(normalize, result) if normalize else result


def hidden_characters(text: str) -> list[dict[str, Any]]:
    """Report invisible/bidi/tag characters (for audit before stripping)."""
    found = []
    for i, ch in enumerate(_require_text(text, MAX_TEXT_CHARS)):
        o = ord(ch)
        if ch in BIDI_CONTROLS:
            kind = "bidi"
        elif ch in INVISIBLES:
            kind = "invisible"
        elif o in _TAG_CHARS:
            kind = "tag"
        else:
            continue
        found.append({"index": i, "codepoint": f"U+{o:04X}", "kind": kind})
    return found


def decode_tag_smuggling(text: str) -> str:
    """Recover ASCII hidden in Unicode tag characters (U+E0020..U+E007E)."""
    return "".join(chr(ord(ch) - 0xE0000) for ch in text if 0xE0020 <= ord(ch) <= 0xE007E)


def escape_html(text: str) -> str:
    return html.escape(_require_text(text, MAX_TEXT_CHARS), quote=True)


_FILENAME_BAD = re.compile(r"[\x00-\x1f\x7f/\\:*?\"<>|]")
_WIN_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.I)


def sanitize_filename(name: str, *, max_len: int = 128, replacement: str = "_") -> str:
    s = sanitize_text(_require_text(name, 4096), keep_newlines=False, normalize="NFKC")
    s = _FILENAME_BAD.sub(replacement, s).strip().strip(".")
    s = re.sub(r"\.{2,}", ".", s)
    if not s or _WIN_RESERVED.match(s):
        s = replacement + (s or "file")
    if len(s) > max_len:
        stem, dot, ext = s.rpartition(".")
        if dot and 0 < len(ext) <= 16:
            s = stem[: max_len - len(ext) - 1] + "." + ext
        else:
            s = s[:max_len]
    return s


def shell_quote(args: list[str]) -> str:
    """Quote argv for display/logging only — never pass the result to a shell."""
    return " ".join(shlex.quote(str(a)) for a in args)


def redact_secrets(text: str, *, placeholder: str = "[REDACTED:{kind}]") -> tuple[str, list[str]]:
    """Replace credential-looking substrings; returns (text, kinds found)."""
    s = _require_text(text, MAX_TEXT_CHARS)
    kinds: list[str] = []
    for kind, pattern in SECRET_PATTERNS:
        def repl(m: re.Match[str], _kind: str = kind) -> str:
            kinds.append(_kind)
            if _kind == "assignment":
                return f"{m.group(1)}=" + placeholder.format(kind=_kind)
            return placeholder.format(kind=_kind)

        s = pattern.sub(repl, s)
    return s, sorted(set(kinds))


def safe_json_loads(raw: str | bytes, *, max_bytes: int = 4 * 1024 * 1024, max_depth: int = MAX_JSON_DEPTH, max_items: int = MAX_JSON_ITEMS) -> Any:
    """Parse JSON with size/depth/item bounds, duplicate-key and NaN refusal."""
    if isinstance(raw, bytes):
        if len(raw) > max_bytes:
            raise SanitizerError("JSON too large", context={"limit": max_bytes})
        raw = raw.decode("utf-8")
    text = _require_text(raw, max_bytes)
    depth = cur = 0
    in_str = esc = False
    for ch in text:  # cheap pre-scan so deeply nested input never reaches the parser
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            cur += 1
            depth = max(depth, cur)
            if depth > max_depth:
                raise SanitizerError("JSON nested too deeply", context={"limit": max_depth})
        elif ch in "]}":
            cur -= 1

    def no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise SanitizerError("duplicate JSON key", context={"key": k[:80]})
            out[k] = v
        return out

    def no_const(name: str) -> Any:
        raise SanitizerError("non-finite JSON number", context={"token": name})

    try:
        value = json.loads(text, object_pairs_hook=no_dupes, parse_constant=no_const)
    except json.JSONDecodeError as exc:
        raise SanitizerError("invalid JSON", context={"line": exc.lineno, "col": exc.colno}) from None
    count = [0]

    def walk(v: Any) -> None:
        count[0] += 1
        if count[0] > max_items:
            raise SanitizerError("JSON has too many items", context={"limit": max_items})
        if isinstance(v, Mapping):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(value)
    return value


def sanitize_structure(value: Any, *, max_depth: int = MAX_JSON_DEPTH, text_limit: int = 100_000) -> Any:
    """Deep-sanitize every string in a JSON-like structure (keys included)."""
    def go(v: Any, d: int) -> Any:
        if d > max_depth:
            raise SanitizerError("structure nested too deeply", context={"limit": max_depth})
        if isinstance(v, str):
            return sanitize_text(v[:text_limit])
        if isinstance(v, Mapping):
            return {go(str(k), d + 1): go(x, d + 1) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [go(x, d + 1) for x in v]
        if v is None or isinstance(v, (bool, int, float)):
            if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
                return None
            return v
        raise SanitizerError("unsupported value type", context={"type": type(v).__name__})

    return go(value, 0)


__all__ = [
    "BIDI_CONTROLS",
    "INVISIBLES",
    "SECRET_PATTERNS",
    "decode_tag_smuggling",
    "escape_html",
    "hidden_characters",
    "redact_secrets",
    "safe_json_loads",
    "sanitize_filename",
    "sanitize_structure",
    "sanitize_text",
    "shell_quote",
    "strip_ansi",
]
