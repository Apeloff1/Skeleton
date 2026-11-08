"""Finite HTTP entity decoding for the canonical DNS-pinned Dragon transport.

Only identity, gzip and RFC 9110 zlib-wrapped deflate are accepted. Both the
on-wire and decoded bodies have independent hard byte ceilings. Incomplete
frames, concatenated streams, trailing data and decompression bombs fail before
a source can enter the existing evidence store. This module performs no I/O.
"""
from __future__ import annotations

import hashlib
import zlib


SUPPORTED_CODINGS = frozenset({"identity", "gzip", "deflate"})


class ContentCodingError(ValueError):
    """A response cannot be decoded under its reserved acquisition budget."""


class BoundedHTTPBody:
    """Incrementally decode an HTTP body without unbounded buffers or output."""

    def __init__(self, coding: str, *, max_bytes: int):
        if (type(coding) is not str or coding not in SUPPORTED_CODINGS
                or type(max_bytes) is not int or not 1 <= max_bytes <= 4_000_000):
            raise ContentCodingError("unsupported or unbounded HTTP entity coding")
        self.coding = coding
        self.max_bytes = max_bytes
        self.wire_bytes = 0
        self.decoded_bytes = 0
        self._wire_digest = hashlib.sha256()
        self._chunks: list[bytes] = []
        self._finished = False
        self._decoder = (
            zlib.decompressobj(16 + zlib.MAX_WBITS)
            if coding == "gzip" else
            zlib.decompressobj(zlib.MAX_WBITS)
            if coding == "deflate" else None
        )

    @property
    def remaining_wire(self) -> int:
        return self.max_bytes - self.wire_bytes

    @property
    def wire_hash(self) -> str:
        return self._wire_digest.hexdigest()

    def _append(self, decoded: bytes) -> None:
        self.decoded_bytes += len(decoded)
        if self.decoded_bytes > self.max_bytes:
            raise ContentCodingError("decoded HTTP body exceeds reserved byte cap")
        if decoded:
            self._chunks.append(decoded)

    def feed(self, data: bytes) -> None:
        if self._finished or type(data) is not bytes:
            raise ContentCodingError("invalid or late HTTP body fragment")
        if not data:
            return
        self.wire_bytes += len(data)
        if self.wire_bytes > self.max_bytes:
            raise ContentCodingError("wire HTTP body exceeds reserved byte cap")
        self._wire_digest.update(data)
        if self._decoder is None:
            self._append(data)
            return
        if self._decoder.eof:
            raise ContentCodingError("unexpected data after compressed HTTP frame")
        try:
            decoded = self._decoder.decompress(
                data, self.max_bytes - self.decoded_bytes + 1,
            )
        except zlib.error as exc:
            raise ContentCodingError("malformed compressed HTTP body") from exc
        self._append(decoded)
        if self._decoder.unconsumed_tail:
            raise ContentCodingError("compressed body exceeds decoded cap")
        if self._decoder.unused_data:
            raise ContentCodingError("trailing data or concatenated compression members")

    def finish(self) -> bytes:
        if self._finished:
            raise ContentCodingError("HTTP body already finalized")
        self._finished = True
        if self._decoder is not None:
            if not self._decoder.eof:
                raise ContentCodingError("truncated compressed HTTP body")
            try:
                suffix = self._decoder.flush(self.max_bytes - self.decoded_bytes + 1)
            except zlib.error as exc:
                raise ContentCodingError("invalid compressed body trailer") from exc
            self._append(suffix)
            if self._decoder.unused_data or self._decoder.unconsumed_tail:
                raise ContentCodingError("compressed body trailing data")
        return b"".join(self._chunks)


def normalize_content_coding(value: str | None) -> str:
    """Reject stacked, ambiguous or unknown Content-Encoding values."""
    if value is None:
        return "identity"
    if not isinstance(value, str) or len(value) > 64:
        raise ContentCodingError("invalid Content-Encoding header")
    token = value.strip().lower()
    if token not in SUPPORTED_CODINGS:
        raise ContentCodingError("unsupported Content-Encoding")
    return token
