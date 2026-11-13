"""Massive security augmentation layer.
Centralizes bounds, path containment, SSRF guards, and error redaction.
Import and use these helpers instead of raw open/subprocess/requests.
"""
from __future__ import annotations
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import socket
from typing import Any

MAX_INPUT_CHARS = 1_000_000
MAX_PATH_SEGMENT = 128

def bound_text(value: str, max_len: int = 10_000) -> str:
    """Truncate and strip control characters."""
    if not isinstance(value, str):
        return ""
    cleaned = "".join(c for c in value if ord(c) >= 32 or c in "\t\n\r")
    return cleaned[:max_len]

def safe_path(root: Path, *segments: str) -> Path:
    """Join and prove containment under root."""
    root_r = root.resolve()
    cand = root_r
    for seg in segments:
        if not isinstance(seg, str) or not seg or seg in (".", "..") or "/" in seg or "\\" in seg:
            raise ValueError("bad segment")
        if len(seg) > MAX_PATH_SEGMENT:
            raise ValueError("segment too long")
        cand = cand / seg
    cand = cand.resolve()
    try:
        cand.relative_to(root_r)
    except ValueError as exc:
        raise ValueError("path escape") from exc
    return cand

def ssrf_safe_url(url: str, allowed_hosts: set[str]) -> tuple[str, str]:
    """Return (origin, path+query) only if host is allowlisted and public."""
    if not isinstance(url, str) or len(url) > 4096:
        raise ValueError("bad url")
    p = urlsplit(url)
    host = (p.hostname or "").lower().rstrip(".")
    if p.scheme != "https" or not host or p.username or p.password or p.port not in (None, 443):
        raise ValueError("must be plain https")
    if host not in allowed_hosts:
        raise ValueError("host not allowlisted")
    try:
        addrs = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("resolve failed") from exc
    for a in addrs:
        ip = ipaddress.ip_address(a[4][0])
        if not ip.is_global:
            raise ValueError("non-public address")
    origin = f"https://{host}"
    target = "/" + (p.path or "").lstrip("/")
    if p.query:
        target += "?" + p.query
    return origin, target

def redact_error(exc: BaseException) -> str:
    """Return a safe client message. Never include traceback."""
    return "internal_error"

def is_safe_identifier(value: str) -> bool:
    return bool(value) and len(value) <= 128 and all(c.isalnum() or c in "_-" for c in value)
