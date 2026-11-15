"""Inert structural text recovery; adaptive to page layout without selectors.

The input is already downloaded HTML. This module never evaluates scripts,
loads resources, generates selectors for a live browser, or changes links.
A high-confidence structural projection is a narrower research view, not
proof of factual accuracy. Ambiguous layouts preserve ordinary extraction.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import math
import re
import unicodedata

MAX_TAGS = 32768
MAX_DEPTH = 128
MAX_BLOCKS = 2048
MAX_BLOCK_CHARS = 8192
MAX_TOTAL_CHARS = 2_097_152
_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
                   "meta", "param", "source", "track", "wbr"})
_SKIP = frozenset({"script", "style", "noscript", "template", "svg", "canvas", "iframe",
                   "object", "button", "select", "textarea", "head"})
_BLOCK = frozenset({"p", "div", "section", "article", "main", "aside", "header", "footer",
                    "nav", "li", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5",
                    "h6", "tr", "td", "th", "figcaption", "dt", "dd", "summary", "address"})
_CHROME = frozenset({"nav", "aside", "header", "footer", "form"})
_CHROME_ROLES = frozenset({"navigation", "banner", "complementary", "contentinfo",
                           "search", "menu", "menubar", "toolbar"})
_MAIN_TAGS = frozenset({"main", "article"})
_MAIN_ROLES = frozenset({"main", "article", "document"})
_PROSE = frozenset({"p", "blockquote", "pre", "figcaption", "dt", "dd", "td", "th"})
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_PUNCT = re.compile(r"[.!?;:。！？；：]")
_HIDDEN_STYLE = re.compile(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\s*(?:!important\s*)?(?:;|$)", re.I)


class StructuralExtractionError(ValueError):
    pass


@dataclass(frozen=True)
class Block:
    ordinal: int
    text: str
    main: bool
    chrome: bool
    prose: bool
    anchor_chars: int
    heading: bool

    @property
    def link_density(self) -> float:
        return min(1., self.anchor_chars / max(1, len(self.text)))

    @property
    def quality(self) -> float:
        words = len(_WORD.findall(self.text))
        punctuation = len(_PUNCT.findall(self.text))
        return (
            .32 * min(1., len(self.text) / 220)
            + .16 * min(1., words / 36)
            + .10 * min(1., punctuation / 3)
            + .15 * self.prose + .20 * self.main + .07 * self.heading
            - .50 * self.link_density - .35 * self.chrome
        )


@dataclass(frozen=True)
class StructuralProjection:
    text: str
    strategy: str
    total_blocks: int
    selected_blocks: int
    visible_chars: int
    selected_chars: int
    confidence: float
    fallback: bool
    truncated: bool

    def receipt(self) -> dict:
        return {"strategy": self.strategy, "total_blocks": self.total_blocks,
                "selected_blocks": self.selected_blocks, "visible_chars": self.visible_chars,
                "selected_chars": self.selected_chars, "confidence": self.confidence,
                "fallback": self.fallback, "truncated": self.truncated,
                "source_trusted": False, "network_used": False}


@dataclass(frozen=True)
class _Frame:
    tag: str
    hidden: bool
    main: bool
    chrome: bool
    prose: bool
    anchor: bool
    heading: bool


class _Reader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[_Frame] = []
        self.blocks: list[Block] = []
        self.fragments: list[str] = []
        self.used = 0
        self.anchor_chars = 0
        self.context: _Frame | None = None
        self.tags = 0
        self.visible = 0
        self.truncated = False

    def _flush(self):
        if not self.fragments:
            self.context = None
            return
        text = " ".join(" ".join(self.fragments).split())
        if text and self.context is not None:
            if len(self.blocks) >= MAX_BLOCKS:
                raise StructuralExtractionError("structural block capacity exhausted")
            self.blocks.append(Block(len(self.blocks), text, self.context.main,
                                     self.context.chrome, self.context.prose,
                                     self.anchor_chars, self.context.heading))
            self.visible += len(text)
            if self.visible > MAX_TOTAL_CHARS:
                raise StructuralExtractionError("visible text exceeds capacity")
        self.fragments = []
        self.used = self.anchor_chars = 0
        self.context = None

    @staticmethod
    def _same_context(a: _Frame | None, b: _Frame) -> bool:
        return a is not None and (a.main, a.chrome, a.prose, a.heading) == (
            b.main, b.chrome, b.prose, b.heading)

    def handle_starttag(self, tag, attrs):
        self.tags += 1
        if self.tags > MAX_TAGS or len(self.stack) > MAX_DEPTH:
            raise StructuralExtractionError("HTML structure budget exceeded")
        tag = tag.casefold()
        if tag in _BLOCK or tag in {"br", "hr"}:
            self._flush()
        parent = self.stack[-1] if self.stack else _Frame("", False, False, False, False, False, False)
        attr = dict(attrs)
        role = (attr.get("role") or "").casefold().split()[:4]
        hidden = (parent.hidden or tag in _SKIP or "hidden" in attr or "inert" in attr
                  or (attr.get("aria-hidden") or "").casefold() == "true"
                  or bool(_HIDDEN_STYLE.search((attr.get("style") or "")[:2048])))
        main = parent.main or tag in _MAIN_TAGS or bool(set(role) & _MAIN_ROLES)
        chrome = parent.chrome or tag in _CHROME or bool(set(role) & _CHROME_ROLES)
        if tag not in _VOID:
            # Common malformed HTML implicitly closes p/li. Avoid allowing
            # an unclosed decorative block to misclassify subsequent text.
            if tag in {"p", "li", "dt", "dd", "td", "th"} and self.stack and self.stack[-1].tag == tag:
                self.stack.pop()
            self.stack.append(_Frame(tag, hidden, main, chrome, parent.prose or tag in _PROSE,
                                     parent.anchor or tag == "a",
                                     parent.heading or tag in {"h1", "h2", "h3", "h4", "h5", "h6"}))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.casefold()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == tag:
                if tag in _BLOCK:
                    self._flush()
                del self.stack[index:]
                break

    def handle_data(self, data):
        context = self.stack[-1] if self.stack else _Frame("", False, False, False, False, False, False)
        if context.hidden:
            return
        text = " ".join(data.split())
        if not text:
            return
        if not self._same_context(self.context, context):
            self._flush()
            self.context = context
        # Fragment the evidence at word boundaries rather than grow an
        # unbounded buffer or silently discard a long source paragraph.
        while text:
            if self.used >= MAX_BLOCK_CHARS:
                self._flush()
                self.context = context
            count = min(len(text), MAX_BLOCK_CHARS - self.used)
            if count < len(text):
                split = text.rfind(" ", max(0, count - 256), count)
                if split > 0:
                    count = split + 1
            piece = text[:count]
            self.fragments.append(piece)
            self.used += len(piece)
            if context.anchor:
                self.anchor_chars += len(piece)
            text = text[count:]

    def finish(self) -> list[Block]:
        self._flush()
        return self.blocks


def extract_structural_text(raw: str, *, max_chars: int) -> StructuralProjection:
    if (not isinstance(raw, str) or len(raw) > 2_500_000
            or type(max_chars) is not int or not 128 <= max_chars <= MAX_TOTAL_CHARS):
        raise StructuralExtractionError("structural input exceeds bounds")
    reader = _Reader()
    try:
        reader.feed(raw)
        reader.close()
        blocks = reader.finish()
    except (ValueError, RecursionError, OverflowError) as exc:
        raise StructuralExtractionError("bounded structural parser rejected HTML") from exc
    visible = sum(len(row.text) for row in blocks)
    selected = [row for row in blocks if row.main and not row.chrome and row.link_density <= .55]
    main_chars = sum(len(row.text) for row in selected)
    main_prose = sum(row.prose and len(row.text) >= 48 for row in selected)
    main_quality = sum(max(0., row.quality) * len(row.text) for row in selected) / max(1, main_chars)
    chrome_chars = sum(len(row.text) for row in blocks if row.chrome or row.link_density > .70)
    # Explicit landmarks plus sufficient prose and observed surrounding
    # chrome make the projection reliable enough to prefer. Ambiguity is
    # not a reason to erase a page's ordinary evidence.
    confidence = min(1., .35 * min(1., main_chars / 400)
                     + .25 * min(1., main_prose / 3)
                     + .25 * min(1., main_quality / .65)
                     + .15 * min(1., chrome_chars / 100))
    strategy = "landmark_density_v1"
    fallback = not (len(selected) >= 2 and main_chars >= 160 and main_chars >= visible * .25
                    and main_prose >= 2 and chrome_chars >= 48 and confidence >= .70)
    if fallback:
        selected = blocks
        strategy = "ambiguous_full_projection"
    # Keep selected source order and exact wording; do not summarize or
    # reorder claims. Captured normalized text still receives its own hash.
    joined = " ".join(row.text for row in selected)
    limited = len(joined) > max_chars
    return StructuralProjection(joined[:max_chars], strategy, len(blocks), len(selected),
                                visible, min(max_chars, len(joined)), round(confidence, 8),
                                fallback, limited)


def validate_structural_receipt(value: object) -> bool:
    keys = {"strategy", "total_blocks", "selected_blocks", "visible_chars",
            "selected_chars", "confidence", "fallback", "truncated",
            "source_trusted", "network_used"}
    if not isinstance(value, dict) or set(value) != keys:
        return False
    if (value["strategy"] not in {"landmark_density_v1", "ambiguous_full_projection"}
            or type(value["fallback"]) is not bool or type(value["truncated"]) is not bool
            or value["source_trusted"] is not False or value["network_used"] is not False
            or value["fallback"] != (value["strategy"] == "ambiguous_full_projection")):
        return False
    for key, cap in (("total_blocks", MAX_BLOCKS), ("selected_blocks", MAX_BLOCKS),
                     ("visible_chars", MAX_TOTAL_CHARS), ("selected_chars", MAX_TOTAL_CHARS)):
        if type(value[key]) is not int or not 0 <= value[key] <= cap:
            return False
    score = value["confidence"]
    return (isinstance(score, (int, float)) and not isinstance(score, bool)
            and math.isfinite(score) and 0 <= score <= 1
            and value["selected_blocks"] <= value["total_blocks"]
            and (value["fallback"] or (value["confidence"] >= .70 and value["selected_blocks"] >= 2)))
