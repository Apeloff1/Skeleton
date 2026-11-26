"""Conservative path and URL admission for local vault callers.

These helpers validate names and return candidate paths; they do not grant
filesystem authority. A caller opening a file in a mutable/untrusted tree must
use descriptor-relative no-follow operations and validate the opened handle.
URL admission is syntactic, not an SSRF defense: network callers must enforce
resolved-address, redirect, peer, timeout and response-size policy separately.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit

_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_ALLOWED_HOSTS = frozenset({"example.com", "localhost", "127.0.0.1"})
_LOOPBACK_HTTP = frozenset({"localhost", "127.0.0.1", "::1"})
_RESERVED = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
})


def _reserved_component(name: str) -> bool:
    return name.split(".", 1)[0].rstrip(" ").upper() in _RESERVED


def validate_safe_identifier(name: str) -> str:
    """Require a bounded, portable identifier (not a filesystem path)."""
    if (
        not isinstance(name, str)
        or not _SAFE_IDENTIFIER.fullmatch(name)
        or name.endswith(".")
        or _reserved_component(name)
    ):
        raise ValueError("invalid portable identifier")
    return name


def _validate_component(part: str) -> None:
    if (
        not isinstance(part, str)
        or not part
        or len(part) > 255
        or part in {".", ".."}
        or part.endswith((".", " "))
        or any(c in part for c in '/\\:<>|"*?')
        or any(ord(c) < 32 or ord(c) == 127 for c in part)
        or PureWindowsPath(part).drive
        or PureWindowsPath(part).root
        or _reserved_component(part)
    ):
        raise ValueError("invalid portable path component")


def safe_join(root: Path, *parts: str) -> Path:
    """Join portable components without accepting traversal or observed links.

    This is a preflight check, not race-free open/create custody.
    """
    if not isinstance(root, Path) or not 1 <= len(parts) <= 64:
        raise ValueError("invalid path root or component count")
    try:
        root_junction = getattr(root, "is_junction", None)
        if root.is_symlink() or (root_junction is not None and root_junction()):
            raise ValueError("symbolic-link root is not allowed")
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("root must be an existing directory")
        candidate = root
        for part in parts:
            _validate_component(part)
            candidate = candidate / part
            if candidate.is_symlink():
                raise ValueError("symbolic-link component is not allowed")
            # Windows directory junctions can redirect without is_symlink().
            is_junction = getattr(candidate, "is_junction", None)
            if is_junction is not None and is_junction():
                raise ValueError("junction component is not allowed")
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
        return resolved
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("path rejected by containment preflight") from exc


def _normalize_host(value: str) -> str:
    if not isinstance(value, str) or not value or not value.isascii():
        raise ValueError("invalid allowlisted host")
    host = value.lower()
    if host == "::1":
        return host
    if len(host) > 253 or any(not _DNS_LABEL.fullmatch(label) for label in host.split(".")):
        raise ValueError("invalid allowlisted host")
    return host


def validate_url_host(url: str, allowed: set[str] | None = None) -> str:
    """Admit an exact configured host; reject ambiguous URL authorities.

    HTTP is permitted only for explicitly admitted loopback host names.
    No wildcard/subdomain inheritance or implicit fallback on an empty list.
    """
    if (
        not isinstance(url, str)
        or not url
        or len(url) > 8192
        or not url.isascii()
        or "\\" in url
        or any(ord(c) <= 32 or ord(c) == 127 for c in url)
    ):
        raise ValueError("invalid URL")
    try:
        parsed = urlsplit(url)
        host = _normalize_host(parsed.hostname or "")
        port = parsed.port
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority += f":{port}"
        if (
            parsed.scheme not in {"https", "http"}
            or parsed.netloc.lower() != authority
            or parsed.username is not None
            or parsed.password is not None
            or "%" in parsed.netloc
            or parsed.netloc.endswith(":")
            or (port is not None and not 1 <= port <= 65535)
            or (parsed.scheme == "http" and host not in _LOOPBACK_HTTP)
        ):
            raise ValueError("unsupported URL authority")
        if allowed is not None and (
            not isinstance(allowed, (set, frozenset)) or len(allowed) > 1024
        ):
            raise ValueError("invalid bounded hostname allowlist")
        admitted = {_normalize_host(item) for item in (_ALLOWED_HOSTS if allowed is None else allowed)}
        if host not in admitted:
            raise ValueError("URL host is not explicitly allowed")
    except (TypeError, ValueError) as exc:
        raise ValueError("URL rejected by host admission") from exc
    return url


def audit_receipt(path: Path, action: str) -> dict:
    """Return an identifier for an action/path pair, not file-content proof."""
    if not isinstance(action, str) or not action or len(action) > 128 or any(
        ord(c) < 32 or ord(c) == 127 for c in action
    ):
        raise ValueError("invalid audit action")
    resolved = str(path.resolve())
    action_bytes = action.encode("utf-8")
    path_bytes = resolved.encode("utf-8", errors="surrogatepass")
    digest = hashlib.sha256(
        b"skeleton-path-receipt-v2\0"
        + len(action_bytes).to_bytes(4, "big")
        + action_bytes
        + path_bytes
    ).hexdigest()
    return {"action": action, "path": str(path), "sha256": digest, "stored_prose": 0}
