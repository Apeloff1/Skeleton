"""
Advanced path and URL hardening for Skeleton.
Fail-closed, no stubs. SHA-bound receipts for audits.
Extends compressed_vault safety. Parent cite #80. stored_prose=0.
"""
from __future__ import annotations
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_ALLOWED_HOSTS = {"example.com", "localhost", "127.0.0.1"}  # extend via config

def validate_safe_identifier(name: str) -> str:
    if not isinstance(name, str) or not _SAFE_IDENTIFIER.fullmatch(name):
        raise ValueError("invalid identifier: must be short ASCII alnum with limited punctuation")
    if name in {".", ".."} or "/" in name or "\\" in name or name.endswith("."):
        raise ValueError("invalid identifier: path-like or reserved")
    return name

def safe_join(root: Path, *parts: str) -> Path:
    """Fail-closed path join: normalize and ensure contained in root."""
    root = root.resolve()
    candidate = root
    for part in parts:
        if not part or not isinstance(part, str):
            raise ValueError("invalid path part")
        candidate = (candidate / part).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path escapes root: {part}") from exc
    return candidate

def validate_url_host(url: str, allowed: Optional[set[str]] = None) -> str:
    """Parse and check hostname against allowlist. No substring checks."""
    if not isinstance(url, str) or not url:
        raise ValueError("invalid URL")
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError("URL missing hostname")
    allow = allowed or _ALLOWED_HOSTS
    if host not in allow and not any(host.endswith("." + a) for a in allow if not a.startswith(".")):
        # strict endswith only after parse
        raise ValueError(f"host not allowed: {host}")
    return url

def audit_receipt(path: Path, action: str) -> dict:
    """SHA-256 bound receipt for path operations."""
    import hashlib
    data = f"{action}:{path.resolve()}".encode()
    return {
        "action": action,
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "stored_prose": 0,
    }
