"""Bounded local-only, raw-byte attestation for human-reviewed media advisories.

This is NOT OCR, STT, video analysis, media decoding, fact verification or
another model. Raw bytes exist only during this authenticated loopback request
and are never saved to the model's SQLite source library or execution record.
"""
from __future__ import annotations

import base64
import binascii
from hashlib import sha256
import hmac
import re
from typing import Any

MAX_MEDIA_BYTES = 4 * 1024 * 1024
MAX_MEDIA_REQUEST_BYTES = 6 * 1024 * 1024
_TYPES = {
    "image/png": "image-caption",
    "image/jpeg": "image-caption",
    "image/webp": "image-caption",
    "audio/wav": "audio-transcript",
    "audio/flac": "audio-transcript",
    "video/mp4": "video-frames",
}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_BASE64 = re.compile(r"[A-Za-z0-9+/]*={0,2}\Z")


class MediaAdvisoryRejected(ValueError):
    """User media is not an approved bounded advisory source."""


def _signature_matches(media_type: str, data: bytes) -> bool:
    """Admit only familiar container headers; no parsing/decoding is claimed."""
    size = len(data)
    if media_type == "image/png":
        return (size >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n"
                and data[12:16] == b"IHDR"
                and 0 < int.from_bytes(data[16:20], "big") <= 32768
                and 0 < int.from_bytes(data[20:24], "big") <= 32768)
    if media_type == "image/jpeg":
        return size >= 8 and data[:3] == b"\xff\xd8\xff" and data[-2:] == b"\xff\xd9"
    if media_type == "image/webp":
        return (size >= 16 and data[:4] == b"RIFF"
                and data[8:12] == b"WEBP"
                and int.from_bytes(data[4:8], "little") + 8 == size)
    if media_type == "audio/wav":
        return (size >= 44 and data[:4] == b"RIFF"
                and data[8:12] == b"WAVE"
                and int.from_bytes(data[4:8], "little") + 8 == size)
    if media_type == "audio/flac":
        return size >= 8 and data[:4] == b"fLaC"
    if media_type == "video/mp4":
        return (size >= 24 and data[4:8] == b"ftyp"
                and 16 <= int.from_bytes(data[:4], "big") <= size
                and bool(re.fullmatch(rb"[A-Za-z0-9 ]{4}", data[8:12])))
    return False


def verify_transient_media(body: dict[str, Any]) -> dict[str, Any] | None:
    """Independently verify actual raw bytes, without retaining the artifact.

    Presence of either media field requires the complete raw-media contract.
    The human-reviewed text and source bytes are different authorities.
    """
    contains = "media_base64" in body or "media_type" in body
    if not contains:
        return None
    if not {"media_type", "media_base64"}.issubset(body):
        raise MediaAdvisoryRejected("local media requires both MIME and exact bytes")
    media_type = body["media_type"]
    text = body["media_base64"]
    if (type(media_type) is not str or media_type not in _TYPES
            or body.get("modality") != _TYPES[media_type]):
        raise MediaAdvisoryRejected("local media type does not match advisory modality")
    if (type(text) is not str or not text
            or len(text) > ((MAX_MEDIA_BYTES + 2) // 3) * 4
            or not text.isascii() or _BASE64.fullmatch(text) is None):
        raise MediaAdvisoryRejected("local media exceeds encoded byte budget or has invalid encoding")
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise MediaAdvisoryRejected("local media is not valid canonical base64") from None
    if not 1 <= len(raw) <= MAX_MEDIA_BYTES:
        raise MediaAdvisoryRejected("local media exceeds decoded byte budget")
    if base64.b64encode(raw).decode("ascii") != text:
        raise MediaAdvisoryRejected("local media base64 is not canonical")
    if not _signature_matches(media_type, raw):
        raise MediaAdvisoryRejected("local media header does not match the declared type")
    source = body.get("source_sha256")
    if type(source) is not str or _SHA.fullmatch(source) is None:
        raise MediaAdvisoryRejected("local media requires exact source SHA-256")
    digest = sha256(raw).hexdigest()
    if not hmac.compare_digest(digest, source):
        raise MediaAdvisoryRejected("local media source SHA-256 differs from exact bytes")
    # Drop raw immediately after the hash/header check; only bounded scalar
    # metadata enters the canonical advisory text or SQLite transaction.
    return {
        "media_type": media_type,
        "media_size_bytes": len(raw),
        "source_sha256": digest,
        "media_digest_authority": "server-verified-transient-source-bytes",
        "media_header_authority": "container-header-only-not-decoded",
        "media_bytes_persisted": False,
    }


__all__ = [
    "MAX_MEDIA_BYTES", "MAX_MEDIA_REQUEST_BYTES",
    "MediaAdvisoryRejected", "verify_transient_media",
]
