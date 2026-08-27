"""API versioning — negotiate semantic versions from header or path.

Routes stay thin; this extracts a requested (major, minor) from either
the ``X-API-Version`` header or a ``/vN[/M]`` path prefix and compares
it against the supported set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

from skeleton.api.middleware import MiddlewareError


class VersionError(MiddlewareError):
    code = "API.VERSION"
    http_status = 400


@dataclass(frozen=True)
class Version:
    major: int
    minor: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"


_VERSION_PATTERN = re.compile(r"/v(\d+)(?:\.(\d+))?")


def extract(*, path: str = "", header: Optional[str] = None) -> Version:
    """Header wins; otherwise the first /vN segment; otherwise 1.0."""
    if header:
        try:
            parts = header.split(".")
            return Version(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (ValueError, IndexError):
            raise VersionError("malformed version header", context={"header": header})
    match = _VERSION_PATTERN.search(path)
    if match:
        return Version(int(match.group(1)), int(match.group(2) or 0))
    return Version(1, 0)


def negotiate(
    supported: Tuple[Version, ...], requested: Version
) -> Version:
    """Pick the best supported version ≤ requested, or raise."""
    eligible = [v for v in supported if v.major == requested.major]
    if not eligible:
        raise VersionError(
            "unsupported major version",
            context={"requested": str(requested), "supported": [str(v) for v in supported]},
        )
    best = max(eligible, key=lambda v: v.minor)
    return best


SUPPORTED: Tuple[Version, ...] = (Version(1, 0),)
