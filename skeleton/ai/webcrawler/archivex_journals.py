"""Policy-gated Europe PMC open-access article ingestion into ArchiveX.

The transport is injected; this module never makes network requests itself.
Only an explicitly authorized, license-reviewed PMC article is accepted.
XML entities and DTDs are rejected before parsing. Sections are distilled
to bounded text snippets with source-level provenance retained.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Callable
from urllib.parse import quote
import re
import xml.etree.ElementTree as ET

from .archivex import ArchiveX, ArchiveXSnapshot


_PMCID = re.compile(r"^PMC[0-9]{1,12}$")
_ALLOWED_LICENSE = frozenset({"CC0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-3.0"})


@dataclass(frozen=True)
class JournalIngestionPolicy:
    max_xml_bytes: int = 1_000_000
    max_sections: int = 64
    max_section_chars: int = 4000
    max_references: int = 256


@dataclass(frozen=True)
class JournalSection:
    section_id: str
    heading: str
    text: str
    text_digest: str


@dataclass(frozen=True)
class JournalIngestionReceipt:
    pmcid: str
    snapshot: ArchiveXSnapshot
    title: str
    sections: tuple[JournalSection, ...]
    reference_ids: tuple[str, ...]
    truncated: bool
    fingerprint: str


def _text(node: ET.Element, max_chars: int) -> str:
    value = " ".join(" ".join(node.itertext()).split())
    return value[:max_chars]


def _parse_article(body: bytes, policy: JournalIngestionPolicy):
    if not 1 <= policy.max_xml_bytes <= 10_000_000:
        raise ValueError("invalid XML budget")
    if not 1 <= policy.max_sections <= 1000:
        raise ValueError("invalid section budget")
    if not 1 <= policy.max_section_chars <= 20000:
        raise ValueError("invalid section text budget")
    if not 1 <= policy.max_references <= 10000:
        raise ValueError("invalid reference budget")
    if not isinstance(body, bytes) or not 0 < len(body) <= policy.max_xml_bytes:
        raise ValueError("invalid XML payload size")
    # ElementTree does not fetch external entities, but rejecting declarations
    # also prevents entity expansion and inconsistent parser behavior.
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)\b", body, re.I):
        raise ValueError("XML entity declarations are forbidden")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError("invalid article XML") from exc
    if root.tag != "article":
        raise ValueError("expected JATS article root")
    title_node = root.find("./front/article-meta/title-group/article-title")
    title = _text(title_node, 500) if title_node is not None else ""
    if not title:
        raise ValueError("article title missing")
    nodes = root.findall("./body/sec")
    sections = []
    for index, node in enumerate(nodes[:policy.max_sections], 1):
        heading_node = node.find("./title")
        heading = _text(heading_node, 200) if heading_node is not None else f"Section {index}"
        body_text = " ".join(
            " ".join(child.itertext()) for child in node
            if child.tag != "title"
        )
        body_text = " ".join(body_text.split())[:policy.max_section_chars]
        if body_text:
            sections.append(JournalSection(
                f"section-{index}", heading, body_text,
                sha256(body_text.encode("utf-8")).hexdigest(),
            ))
    refs = []
    for ref in root.findall("./back/ref-list/ref")[:policy.max_references]:
        identifier = ref.get("id")
        if identifier and len(identifier) <= 128:
            refs.append(identifier)
    truncated = (len(nodes) > policy.max_sections or
                 len(root.findall("./back/ref-list/ref")) > policy.max_references)
    return title, tuple(sections), tuple(refs), truncated


def ingest_open_access_journal(
    archive: ArchiveX, *, owner: str, pmcid: str,
    fetch_xml: Callable[[str], bytes], observed_at: float, now: float,
    license_id: str, authorized: bool,
    policy: JournalIngestionPolicy = JournalIngestionPolicy(),
) -> JournalIngestionReceipt:
    if not authorized:
        raise PermissionError("journal ingestion requires explicit authorization")
    if not isinstance(pmcid, str) or not _PMCID.fullmatch(pmcid):
        raise ValueError("invalid PMC identifier")
    if license_id not in _ALLOWED_LICENSE:
        raise PermissionError("license not approved for archival ingestion")
    endpoint = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/"
        + quote(pmcid, safe="") + "/fullTextXML"
    )
    body = fetch_xml(endpoint)
    title, sections, references, truncated = _parse_article(body, policy)
    snapshot = archive.capture(
        owner, source_url=endpoint, body=body, observed_at=observed_at,
        now=now, media_type="application/xml", license_note=license_id,
        authorized=True,
    )
    fingerprint = sha256(
        (snapshot.snapshot_id + ":" +
         ":".join(section.text_digest for section in sections)).encode("utf-8")
    ).hexdigest()
    return JournalIngestionReceipt(
        pmcid, snapshot, title, sections, references, truncated, fingerprint,
    )
