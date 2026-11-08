"""Strict download media sniffing for already-admitted document responses.

Only a canonical URL's exact file extension AND a matching bounded binary
signature can refine an ambiguous octet-stream MIME type. This is not a
bypass for denied hosts or a general-purpose content-type guessing engine.
Unknown/bad signatures remain unsupported binary rather than inert evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlsplit


_ARCHIVES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".epub": "application/epub+zip",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
}
_PDF = {".pdf": "application/pdf"}
_XML = {
    ".xml": "application/xml",
    ".gpx": "application/gpx+xml",
    ".kml": "application/vnd.google-earth.kml+xml",
}
_SOURCE_TYPES = frozenset({"application/octet-stream", "binary/octet-stream", "application/zip"})


@dataclass(frozen=True)
class MediaDecision:
    effective_type: str
    inferred: bool
    reason: str
    executable_content_admitted: bool = False
    external_network_authority: bool = False


def valid_media_receipt(
    effective_type: object,
    declared_type: object,
    inferred: object,
    reason: object,
) -> bool:
    """Validate optional stored MIME provenance without trusting source text.

    Legacy snapshots omit all three extension fields and are admitted by the
    calling snapshot validator. A present receipt is indivisible, and only
    media_probe's finite, explicitly recognized decisions are accepted.
    This checks stored metadata consistency, not an unavailable raw body.
    """
    if (
        type(effective_type) is not str
        or type(declared_type) is not str
        or not 0 < len(declared_type) <= 256
        or type(inferred) is not bool
        or type(reason) is not str
    ):
        return False
    if inferred:
        if declared_type not in _SOURCE_TYPES or declared_type == effective_type:
            return False
        expected = {
            "pdf_magic_and_extension": set(_PDF.values()),
            "finite_archive_magic_and_extension": set(_ARCHIVES.values()),
            "finite_xml_prefix_and_extension": set(_XML.values()),
        }
        return effective_type in expected.get(reason, ())
    if declared_type != effective_type:
        return False
    if declared_type in _SOURCE_TYPES:
        return reason in {
            "pdf_magic_missing", "archive_magic_missing",
            "xml_magic_missing", "unsupported_binary_media",
        }
    return reason == "declared_media_kept"


def inspect_download_media(
    url: str, declared_type: str, body: bytes,
    content_disposition: str | None = None,
) -> MediaDecision:
    if (
        not isinstance(url, str) or len(url) > 4096
        or (content_disposition is not None and (
            not isinstance(content_disposition, str)
            or len(content_disposition) > 1024
        ))
        or type(declared_type) is not str or len(declared_type) > 256
        or type(body) is not bytes or len(body) > 2_097_152
    ):
        raise ValueError("invalid bounded media identity contract")
    declared = declared_type.split(";", 1)[0].strip().lower()
    if declared not in _SOURCE_TYPES:
        return MediaDecision(declared, False, "declared_media_kept")
    path = urlsplit(url).path.lower()
    # RFC 6266 filename is an untrusted format hint, never a host/rights grant.
    # Only a simple basename plus a matching magic signature is sufficient.
    if content_disposition:
        match = re.fullmatch(
            r'(?is)attachment\s*;\s*filename\s*=\s*(?:"([a-z0-9_. -]{1,128})"|([a-z0-9_.-]{1,128}))\s*',
            content_disposition.strip(),
        )
        if match:
            hint = (match.group(1) or match.group(2)).lower()
            if hint not in (".", "..") and not hint.startswith("."):
                path = hint
    if path.endswith(".pdf"):
        if body.startswith(b"%PDF-"):
            return MediaDecision("application/pdf", True, "pdf_magic_and_extension")
        return MediaDecision(declared, False, "pdf_magic_missing")
    for extension, result in _ARCHIVES.items():
        if path.endswith(extension):
            if body[:4] == b"PK\x03\x04":
                return MediaDecision(result, True, "finite_archive_magic_and_extension")
            return MediaDecision(declared, False, "archive_magic_missing")
    for extension, result in _XML.items():
        if path.endswith(extension):
            prefix = body[:512].lstrip(b"\xef\xbb\xbf \r\n\t")
            if prefix.startswith((b"<?xml ", b"<?xml?", b"<")) and b"\x00" not in prefix:
                return MediaDecision(result, True, "finite_xml_prefix_and_extension")
            return MediaDecision(declared, False, "xml_magic_missing")
    return MediaDecision(declared, False, "unsupported_binary_media")
