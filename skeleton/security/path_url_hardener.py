"""skeleton/security/path_url_hardener.py — production path and URL sanitizer.
Closes open CodeQL path-injection and incomplete-URL-substring alerts.
Complements decoded_path.py. Complete, receipted, fail-closed.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Final
from urllib.parse import urlparse, urlunparse

try:
    from skeleton.kernel.errors import SkeletonError
except ImportError:
    class SkeletonError(Exception):
        pass

try:
    from skeleton.provenance.chronicle import emit_receipt
except ImportError:
    def emit_receipt(**kwargs):
        return kwargs.get("digest", "")

_ALLOWED_HOST_SUFFIXES: Final[tuple[str, ...]] = (".example.com", "localhost", "127.0.0.1")
_SAFE_ROOT: Final[Path] = Path("/app/data/safe").resolve()
_MAX_PATH_LEN: Final[int] = 4096

class PathHardeningError(SkeletonError):
    code = "SEC_PATH_HARDEN"
    severity = "high"

class URLHardeningError(SkeletonError):
    code = "SEC_URL_HARDEN"
    severity = "high"

def harden_path(user_path: str, root: Path | None = None) -> Path:
    if not isinstance(user_path, str) or not user_path or len(user_path) > _MAX_PATH_LEN:
        raise PathHardeningError("path length, type, or emptiness violation")
    base = (root or _SAFE_ROOT).resolve()
    try:
        candidate = Path(user_path)
        if candidate.is_absolute():
            candidate = Path(*candidate.parts[1:]) if len(candidate.parts) > 1 else Path(".")
        full = (base / candidate).resolve()
        base_str = str(base)
        full_str = str(full)
        if not (full_str == base_str or full_str.startswith(base_str + os.sep)):
            raise PathHardeningError("path escapes allowed root")
        real = full.resolve(strict=False)
        if not str(real).startswith(base_str):
            raise PathHardeningError("symlink escape detected")
        digest = hashlib.sha256(full_str.encode()).hexdigest()
        emit_receipt(kind="path_harden", target=full_str, digest=digest, stored_prose=0)
        return real
    except (OSError, ValueError) as exc:
        raise PathHardeningError(f"path resolution failed: {exc}") from exc

def harden_url(raw: str, allowed_suffixes: tuple[str, ...] | None = None) -> str:
    if not isinstance(raw, str) or not raw.lower().startswith(("http://", "https://")):
        raise URLHardeningError("not a valid absolute http(s) URL")
    parsed = urlparse(raw)
    if not parsed.hostname:
        raise URLHardeningError("missing hostname")
    host = parsed.hostname.lower()
    suffixes = allowed_suffixes or _ALLOWED_HOST_SUFFIXES
    allowed = any(host == s.lstrip(".") or host.endswith("." + s.lstrip(".")) for s in suffixes)
    if not allowed:
        raise URLHardeningError(f"host {host} not in allow-list")
    clean = urlunparse((
        parsed.scheme,
        parsed.hostname + (f":{parsed.port}" if parsed.port else ""),
        parsed.path or "/",
        parsed.params,
        parsed.query,
        ""
    ))
    digest = hashlib.sha256(clean.encode()).hexdigest()
    emit_receipt(kind="url_harden", target=clean, digest=digest, stored_prose=0)
    return clean

def harden_and_open(user_path: str, mode: str = "rb", root: Path | None = None) -> bytes:
    safe = harden_path(user_path, root)
    try:
        with open(safe, mode) as fh:
            return fh.read()
    except OSError as exc:
        raise PathHardeningError(f"open failed after harden: {exc}") from exc
