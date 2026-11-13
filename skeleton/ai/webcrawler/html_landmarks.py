"""Bounded semantic HTML landmarks enriching inert external source evidence.

This walks only already downloaded source HTML. It never creates URL hints,
opens a browser or fetches resources, interprets ARIA as trusted instructions,
executes script, loads iframes, or promotes extracted content to knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser


_ALLOWED = frozenset({
    "h1", "h2", "h3", "h4", "h5", "h6",
    "figcaption", "blockquote", "caption", "summary", "dt", "dd",
})
_IGNORE = frozenset({
    "script", "style", "noscript", "svg", "template", "iframe", "canvas",
})
_LABEL = {
    "figcaption":"Figure", "blockquote":"Quotation",
    "caption":"Caption", "summary":"Summary", "dt":"Term", "dd":"Definition",
}


class HTMLLandmarkError(ValueError):
    """HTML landmark projection limit or syntax violated."""


@dataclass(frozen=True)
class HTMLLandmarks:
    text: str
    count: int
    meta_descriptions: int
    truncated: bool
    links: tuple[str, ...] = ()
    body_executed: bool = False
    reference_trusted: bool = False


class _LandmarkReader(HTMLParser):
    def __init__(self, *, max_chars: int):
        super().__init__(convert_charrefs=True)
        self.max_chars = max_chars
        self.tags = 0
        self.hidden_depth = 0
        self.stack: list[tuple[str,list[str]]] = []
        self.lines: list[str] = []
        self.chars = 0
        self.count = 0
        self.meta_count = 0
        self.truncated = False

    def _line(self, value: str):
        if not value or self.count >= 128:
            self.truncated = True
            return
        if self.chars + len(value) + 1 > self.max_chars:
            self.truncated = True
            return
        self.lines.append(value)
        self.chars += len(value) + 1
        self.count += 1

    def handle_starttag(self, tag, attrs):
        self.tags += 1
        if self.tags > 16384:
            raise HTMLLandmarkError("HTML source tag count exceeded")
        tag = tag.lower()
        if tag in _IGNORE:
            self.hidden_depth += 1
        if self.hidden_depth:
            return
        attr = dict(attrs)
        if tag == "meta" and (attr.get("name") or "").lower() == "description":
            value = attr.get("content") or ""
            if not isinstance(value, str) or len(value) > 1024:
                raise HTMLLandmarkError("invalid source meta description")
            if value.strip() and self.meta_count == 0:
                self.meta_count = 1
                self._line("Document description: " + value.strip())
        if tag in _ALLOWED:
            if len(self.stack) > 16:
                raise HTMLLandmarkError("HTML landmark nesting exceeded")
            label = attr.get("aria-label") or ""
            if not isinstance(label, str) or len(label) > 1024:
                raise HTMLLandmarkError("invalid HTML landmark ARIA label")
            self.stack.append((tag, [label.strip()] if label.strip() else []))

    def handle_data(self, data):
        if self.hidden_depth or not self.stack:
            return
        if len(data) > 32768:
            raise HTMLLandmarkError("single HTML landmark chunk exceeded")
        for _, fragments in self.stack:
            if sum(map(len, fragments)) + len(data) > 4096:
                raise HTMLLandmarkError("HTML landmark text budget exceeded")
            fragments.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _IGNORE:
            if self.hidden_depth:
                self.hidden_depth -= 1
            return
        if self.hidden_depth or tag not in _ALLOWED or not self.stack:
            return
        # Broken nesting must not create fictitious source headings.
        if self.stack[-1][0] != tag:
            return
        label, fragments = self.stack.pop()
        body = " ".join("".join(fragments).split()).strip()
        if body:
            title = f"Heading {label[1]}" if label.startswith("h") else _LABEL[label]
            self._line(f"{title}: {body[:2048]}")


def extract_html_landmarks(
    raw: str, *, max_chars: int = 8192,
) -> HTMLLandmarks:
    if (not isinstance(raw, str) or len(raw) > 2_500_000
            or type(max_chars) is not int or not 128 <= max_chars <= 2_097_152):
        raise HTMLLandmarkError("unbounded HTML landmark input")
    parser = _LandmarkReader(max_chars=max_chars)
    try:
        parser.feed(raw)
        parser.close()
    except (ValueError, RecursionError) as exc:
        raise HTMLLandmarkError("invalid HTML landmark structure") from exc
    return HTMLLandmarks(
        text="\n".join(parser.lines), count=parser.count,
        meta_descriptions=parser.meta_count, truncated=parser.truncated,
    )
