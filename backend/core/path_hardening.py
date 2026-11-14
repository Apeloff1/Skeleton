"""Bounded lexical and resolved-path/URL admission helpers.

These helpers do not open files or connect sockets. A successful check is
not a race-free filesystem lease or a DNS/redirect/SSRF authorization.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit

_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")
_ALLOWED_HOSTS = frozenset({"example.com", "localhost", "127.0.0.1"})
_RESERVED_WINDOWS = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
     *(f"LPT{i}" for i in range(1, 10))}
)


def validate_safe_identifier(name: str) -> str:
    if type(name) is not str or not _SAFE_IDENTIFIER.fullmatch(name):
        raise ValueError("invalid identifier")
    if name.endswith(".") or name.split(".", 1)[0].upper() in _RESERVED_WINDOWS:
        raise ValueError("reserved identifier")
    return name


def safe_join(root: Path, *parts: str) -> Path:
    """Return a resolved contained path; caller must secure actual opening.

    Only a sequence of individual portable names is accepted. Existing
    symlinks are resolved for containment, but may change after this check.
    """
    if not isinstance(root, Path) or len(parts) > 64:
        raise ValueError("invalid path root or component count")
    try:
        root = root.resolve()
        candidate = root
        for part in parts:
            name = validate_safe_identifier(part)
            if PureWindowsPath(name).is_reserved():
                raise ValueError("reserved path component")
            candidate = (candidate / name).resolve()
            candidate.relative_to(root)
        return candidate
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("invalid or escaping path") from exc


def _normalize_host(host: str) -> str:
    if (type(host) is not str or not host.isascii()
            or not _HOST.fullmatch(host.lower()) or ".." in host):
        raise ValueError("invalid allowlisted hostname")
    host = host.lower()
    if any(len(label) > 63 or label.startswith("-") or label.endswith("-")
           for label in host.split(".")):
        raise ValueError("invalid allowlisted hostname")
    return host


def validate_url_host(url: str, allowed: set[str] | None = None) -> str:
    """Check an exact configured HTTP(S) hostname, not network reachability.

    Callers making requests must independently enforce DNS/IP restrictions
    and redirect handling. Defaults remain for legacy local/test callers;
    an empty explicit allowlist denies every URL.
    """
    if (type(url) is not str or not 1 <= len(url) <= 8192
            or any(ord(char) <= 32 or ord(char) == 127 for char in url)
            or "\\" in url):
        raise ValueError("invalid URL")
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or "%" in parsed.netloc or parsed.netloc.endswith(":")):
            raise ValueError("invalid URL authority")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("invalid URL port")
        host = _normalize_host(parsed.hostname)
    except ValueError as exc:
        raise ValueError("invalid URL authority") from exc
    if allowed is None:
        allow = _ALLOWED_HOSTS
    else:
        if not isinstance(allowed, (set, frozenset)) or len(allowed) > 1024:
            raise ValueError("invalid hostname allowlist")
        allow = frozenset(_normalize_host(item) for item in allowed)
    if host not in allow:
        raise ValueError("host not allowed")
    return url


def audit_receipt(path: Path, action: str) -> dict:
    """Bind a declared action to its resolved path; not a signed proof."""
    if not isinstance(path, Path):
        raise ValueError("invalid receipt path")
    action = validate_safe_identifier(action)
    resolved = str(path.resolve())
    body = {"action": action, "path": resolved}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**body, "sha256": hashlib.sha256(encoded).hexdigest(), "stored_prose": 0}
