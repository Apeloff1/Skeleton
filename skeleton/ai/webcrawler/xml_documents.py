"""Finite, no-execution general XML, GPX and KML evidence extraction.

Sitemaps and syndication feeds are *discovery*, handled separately. Unrelated
XML is captured as untrusted textual evidence without treating URLs, XML
attributes, instructions, entity references or embedded markup as commands.
No network, filesystem access, package imports or external entities are used.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import xml.etree.ElementTree as ET


GENERIC_XML_TYPES = frozenset({
    "application/xml", "text/xml", "application/x-xml",
    "application/gpx+xml", "application/vnd.google-earth.kml+xml",
    "application/rdf+xml",
})
_FORBID = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.I)
_DECL = re.compile(rb"^<\?xml[^?]*\bencoding\s*=\s*['\"]([^'\"]+)['\"]", re.I)
_NAME_SAFE = re.compile(r"[^a-z0-9_-]+", re.I)
_REDACT = frozenset({
    "password", "passwd", "apikey", "api_key", "authorization",
    "token", "access_token", "refresh_token", "secret",
    "client_secret", "private_key", "credential", "credentials",
})


class XMLDocumentError(ValueError):
    """Untrusted XML cannot be safely represented as finite source evidence."""


@dataclass(frozen=True)
class ExtractedXML:
    text: str
    title: str
    links: tuple[str, ...] = ()
    truncated: bool = False
    body_executed: bool = False
    reference_trusted: bool = False


def _local(tag: str) -> str:
    if not isinstance(tag, str):
        raise XMLDocumentError("XML tag is not a string")
    return tag.rsplit("}", 1)[-1] if tag.startswith("{") else tag


def _safe_name(tag: str) -> str:
    return _NAME_SAFE.sub("_", _local(tag)[:96]).strip("_") or "field"


def _sensitive(tag: str) -> bool:
    name = _safe_name(tag).casefold().replace("-", "_")
    return name in _REDACT or any(
        name.endswith("_" + key) for key in _REDACT
    )


def extract_xml_evidence(
    body: bytes, *, max_chars: int = 524288,
    max_nodes: int = 8192, max_depth: int = 32,
) -> ExtractedXML:
    """Extract bounded leaf text with structural labels and secret-key redaction."""
    if (
        type(body) is not bytes or not body or len(body) > 2_097_152
        or type(max_chars) is not int or not 1 <= max_chars <= 2_097_152
        or type(max_nodes) is not int or not 1 <= max_nodes <= 20_000
        or type(max_depth) is not int or not 1 <= max_depth <= 48
    ):
        raise XMLDocumentError("XML evidence exceeds parse capacity")
    if (
        b"\x00" in body or _FORBID.search(body)
        or body.startswith((b"\xff\xfe", b"\xfe\xff"))
    ):
        raise XMLDocumentError("binary XML or XML external entity declaration")
    match = _DECL.match(body.lstrip(b"\xef\xbb\xbf \r\n\t")[:256])
    if match and match.group(1).lower().replace(b"-", b"") != b"utf8":
        raise XMLDocumentError("only UTF-8 XML may enter the evidence store")
    try:
        content = body.decode("utf-8-sig", errors="strict")
        root = ET.fromstring(content)
    except (UnicodeError, ET.ParseError, RecursionError) as exc:
        raise XMLDocumentError("malformed source XML") from exc
    # Explicit iterative depth-first traversal; no recursion or entity fetch.
    stack: list[tuple[ET.Element, str, int, bool]] = [
        (root, _safe_name(root.tag), 1, _sensitive(root.tag))
    ]
    lines: list[str] = []
    total = nodes = 0
    title = ""
    clipped = False
    while stack:
        element, path, depth, secret = stack.pop()
        nodes += 1
        if nodes > max_nodes or depth > max_depth:
            raise XMLDocumentError("XML tree exceeds node/depth budget")
        if len(element.attrib) > 128:
            raise XMLDocumentError("XML attribute count exceeds budget")
        # No attributes are persisted: in XML APIs they often contain secrets,
        # remote links, tokens or user identifiers. Elements are inert text.
        children = list(element)
        if len(children) > 2048:
            raise XMLDocumentError("XML branch exceeds child budget")
        label = _safe_name(element.tag)
        value = " ".join((element.text or "").split())
        if secret:
            value = "[redacted sensitive XML element]"
        if value:
            if len(value) > 8192:
                value = value[:8192]
                clipped = True
            if label.casefold() in ("title", "name", "headline") and not title and not secret:
                title = value[:512]
            row = f"{path}: {value}"
            total += len(row) + 1
            # The retained budget is a truncation target, not a parse error.
            # Keep the inspection finite even when the caller requests a tiny
            # preview of a moderately sized, valid XML source.
            if total > min(2_097_152, max_chars * 8 + 16384):
                raise XMLDocumentError("XML text projection exceeds parse budget")
            lines.append(row)
        for child in reversed(children):
            child_name = _safe_name(child.tag)
            stack.append((
                child, path + "." + child_name, depth + 1,
                secret or _sensitive(child.tag),
            ))
    text = "\n".join(lines).strip()
    if not text:
        raise XMLDocumentError("XML contains no meaningful textual evidence")
    return ExtractedXML(text[:max_chars], title, truncated=clipped or len(text) > max_chars)
