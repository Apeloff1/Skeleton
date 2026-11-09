"""Respect source-published noindex/nofollow/noarchive capture constraints.

Site directives only narrow what the already-authorized crawler may retain
or discover. They are not authentication, trust, source-rights or a grant to
bypass robots, host restrictions, consent or the canonical request budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Mapping


@dataclass(frozen=True)
class CaptureRights:
    retain: bool
    follow: bool
    directives: tuple[str, ...]
    source: tuple[str, ...]
    site_cannot_grant_authority: bool = True


class _RobotsMetaParser(HTMLParser):
    def __init__(self, *, max_tags: int):
        super().__init__(convert_charrefs=True)
        self.records: list[tuple[str, str]] = []
        self.tags = 0
        self.max_tags = max_tags

    def handle_starttag(self, tag, attrs):
        self.tags += 1
        if self.tags > self.max_tags:
            raise ValueError("HTML robots metadata tag budget exceeded")
        if tag.casefold() != "meta":
            return
        values = dict((k.casefold(), v) for k, v in attrs if k and isinstance(v, str))
        key = values.get("name", "").strip().casefold()
        if key not in ("robots", "skeletonai-crawler", "skeletonai-crawler/1.0"):
            return
        content = values.get("content", "")
        if isinstance(content, str) and len(content) <= 2048:
            self.records.append((key, content))
        if len(self.records) > 32:
            raise ValueError("too many conflicting HTML robots records")


def _tokens(value: str, agent: str, *, targeted: bool) -> list[str]:
    if not isinstance(value, str) or len(value) > 4096:
        return []
    result: list[str] = []
    for cell in value.split(","):
        entry = cell.strip().lower()
        if not entry:
            continue
        # X-Robots-Tag may contain "user-agent: noindex".
        if ":" in entry:
            target, directive = entry.split(":", 1)
            if not targeted and target.strip() not in (
                agent, "skeletonai-crawler", "skeletonai-crawler/1.0",
            ):
                continue
            entry = directive.strip()
        for token in entry.split():
            if token in ("noindex", "nofollow", "noarchive", "none"):
                result.append(token)
    return result


def source_capture_rights(
    headers: Mapping[str, str], body: bytes, *,
    media_type: str, user_agent: str = "SkeletonAI-Crawler/1.0",
    max_meta_tags: int = 4096,
) -> CaptureRights:
    if (
        not isinstance(headers, Mapping) or type(body) is not bytes
        or not isinstance(media_type, str) or not isinstance(user_agent, str)
        or len(user_agent) > 128 or type(max_meta_tags) is not int
        or not 1 <= max_meta_tags <= 8192
    ):
        raise ValueError("invalid source robots authority boundary")
    agent = user_agent.split("/", 1)[0].casefold()
    directives: list[str] = []
    sources: list[str] = []
    for name, value in headers.items():
        if isinstance(name, str) and name.casefold() == "x-robots-tag":
            headers_tokens = _tokens(value, agent, targeted=False)
            if headers_tokens:
                directives.extend(headers_tokens)
                sources.append("x-robots-tag")
    if media_type in ("text/html", "application/xhtml+xml"):
        # A malformed/oversized HTML metadata parse can never *relax* an
        # observed header prohibition. On excess complexity deny both.
        try:
            parser = _RobotsMetaParser(max_tags=max_meta_tags)
            parser.feed(body[:262144].decode("utf-8", errors="replace"))
            parser.close()
        except (ValueError, RecursionError):
            return CaptureRights(
                False, False, tuple(sorted(set(directives + ["meta_overflow"]))),
                tuple(sorted(set(sources + ["html_meta_budget"]))),
            )
        for target, content in parser.records:
            if target == "robots" or target in (
                agent, "skeletonai-crawler", "skeletonai-crawler/1.0",
            ):
                meta_tokens = _tokens(content, agent, targeted=True)
                if meta_tokens:
                    directives.extend(meta_tokens)
                    sources.append("html_meta")
    tokens = tuple(sorted(set(directives)))
    denied = "none" in tokens
    return CaptureRights(
        retain=not denied and "noindex" not in tokens and "noarchive" not in tokens,
        follow=not denied and "nofollow" not in tokens,
        directives=tokens,
        source=tuple(sorted(set(sources))),
    )
