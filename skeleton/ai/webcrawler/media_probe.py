"""Strict download media sniffing for already-admitted document responses.

Only a canonical URL's exact file extension AND a matching bounded binary
signature can refine an ambiguous octet-stream MIME type. This is not a
bypass for denied hosts or a general-purpose content-type guessing engine.
Unknown/bad signatures remain unsupported binary rather than inert evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


_ARCHIVES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".epub": "application/epub+zip",
}
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


def inspect_download_media(
    url: str, declared_type: str, body: bytes,
) -> MediaDecision:
    if (
        not isinstance(url, str) or len(url) > 4096
        or type(declared_type) is not str or len(declared_type) > 256
        or type(body) is not bytes or len(body) > 2_097_152
    ):
        raise ValueError("invalid bounded media identity contract")
    declared = declared_type.split(";", 1)[0].strip().lower()
    if declared not in _SOURCE_TYPES:
        return MediaDecision(declared, False, "declared_media_kept")
    path = urlsplit(url).path.lower()
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
