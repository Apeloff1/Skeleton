"""Target checks for browser capture tooling (port of ``browser-guard.mjs``).

Capture tools run Chromium with ``--no-sandbox`` and take URL/output path from
argv; unchecked they could render ``file:///root/...`` into a PNG or write
anywhere. These raise :class:`GuardError` instead of exiting, so callers decide.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlsplit

LOOPBACK_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
ALLOW_EXTERNAL_ENV = "BROWSER_ALLOW_EXTERNAL_HOST"


class GuardError(ValueError):
    """A capture target failed a safety check."""


def checked_url(url: str, env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError as exc:
        raise GuardError(f"not a valid URL: {url}") from exc
    if parts.scheme not in ("http", "https"):
        raise GuardError(
            f"only http/https URLs are allowed, got {parts.scheme or '(none)'}: in {url}"
        )
    if not host:
        raise GuardError(f"not a valid URL: {url}")
    if host not in LOOPBACK_HOSTNAMES and env.get(ALLOW_EXTERNAL_ENV) != "1":
        raise GuardError(
            f"{host} is not a loopback host; capture tools screenshot the local dev "
            f"server. Set {ALLOW_EXTERNAL_ENV}=1 to override."
        )
    return url


def checked_output_path(
    target: str | os.PathLike[str],
    allowed_dirs: Iterable[str | os.PathLike[str]],
    label: str = "screenshot",
) -> Path:
    """Absolute ``target`` if strictly inside one of ``allowed_dirs``.

    Paths are resolved (``..`` and symlinks) before comparison so traversal
    cannot slip past a prefix check.
    """
    abs_target = Path(os.path.realpath(os.fspath(target)))
    dirs = [Path(os.path.realpath(os.fspath(d))) for d in allowed_dirs]
    for d in dirs:
        if abs_target != d and d in abs_target.parents:
            return abs_target
    raise GuardError(
        f"{label} path must be under {' or '.join(map(str, dirs))}, got {abs_target}"
    )
