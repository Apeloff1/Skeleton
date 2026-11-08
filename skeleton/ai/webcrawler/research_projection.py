"""Finite, non-authoritative text projections for external research artifacts.

No networking, filesystem access, executable decoding, permission upgrades,
record creation or source-rights inference occurs in this module.
"""
from __future__ import annotations

from dataclasses import dataclass


class ResearchFormatError(ValueError):
    """An unsupported, unsafe or excessive external research representation."""


@dataclass(frozen=True)
class ResearchProjection:
    text: str
    title: str
    truncated: bool
    links: tuple[str, ...] = ()
    body_executed: bool = False
    reference_trusted: bool = False


def check_text(raw: str, *, max_chars: int, max_links: int = 0) -> None:
    if (not isinstance(raw, str) or len(raw) > 2_500_000
            or type(max_chars) is not int or not 1 <= max_chars <= 2_097_152
            or type(max_links) is not int or not 0 <= max_links <= 512):
        raise ResearchFormatError("unbounded external research artifact")
    if any(ord(c) < 32 and c not in "\r\n\t" for c in raw):
        raise ResearchFormatError("binary or control-bearing research artifact")
    if raw.count("\ufffd") > max(4, len(raw) // 100):
        raise ResearchFormatError("excessive undecodable research text")


def project_lines(
    lines: list[str], *, title: str, max_chars: int,
) -> ResearchProjection:
    if not isinstance(lines, list) or len(lines) > 4096:
        raise ResearchFormatError("external artifact record capacity exceeded")
    if not isinstance(title, str) or len(title) > 4096:
        raise ResearchFormatError("invalid external artifact title")
    total = 0
    for line in lines:
        if not isinstance(line, str) or len(line) > 16_384:
            raise ResearchFormatError("external artifact field length exceeded")
        total += len(line) + 1
        if total > 2_500_000 or total > max_chars * 8:
            raise ResearchFormatError("artifact projection expansion exceeded")
    result = "\n".join(lines).strip()
    if not result:
        raise ResearchFormatError("artifact contains no retainable source evidence")
    return ResearchProjection(
        text=result[:max_chars], title=title[:512],
        truncated=len(result) > max_chars,
    )
