"""Non-decoding PNG/JPEG/GIF/WAV metadata from already-admitted external bytes.

This is intentionally *not* image, audio or authenticity verification. It
cannot decode pixels, infer audio content, run codecs, load file paths,
interpret EXIF, issue media requests, or license source material for training.
"""
from __future__ import annotations

import struct
import zlib

from .research_projection import ResearchFormatError, ResearchProjection, project_lines

IMAGE_METADATA_TYPES = frozenset({"image/png", "image/jpeg", "image/gif"})
AUDIO_METADATA_TYPES = frozenset({"audio/wav", "audio/x-wav", "audio/vnd.wave"})
BINARY_MEDIA_TYPES = IMAGE_METADATA_TYPES | AUDIO_METADATA_TYPES
_MAX_BODY = 2_097_152
_MAX_DIMENSION = 16384


def _dimensions(width: int, height: int) -> None:
    if (type(width) is not int or type(height) is not int
            or not 1 <= width <= _MAX_DIMENSION
            or not 1 <= height <= _MAX_DIMENSION
            or width * height > 67_108_864):
        raise ResearchFormatError("oversized or invalid image dimensions")


def _png(body: bytes) -> list[str]:
    signature = b"\x89PNG\r\n\x1a\n"
    if len(body) < 33 or body[:8] != signature:
        raise ResearchFormatError("invalid PNG signature or header size")
    if body[8:12] != b"\x00\x00\x00\r" or body[12:16] != b"IHDR":
        raise ResearchFormatError("PNG IHDR must be the first 13-byte chunk")
    data = body[16:29]
    expected_crc = struct.unpack(">I", body[29:33])[0]
    if (zlib.crc32(b"IHDR" + data) & 0xffffffff) != expected_crc:
        raise ResearchFormatError("PNG IHDR CRC mismatch")
    width, height, depth, color, compression, filt, interlace = struct.unpack(
        ">IIBBBBB", data,
    )
    _dimensions(width, height)
    if (depth not in (1, 2, 4, 8, 16)
            or color not in (0, 2, 3, 4, 6)
            or compression != 0 or filt != 0 or interlace not in (0, 1)):
        raise ResearchFormatError("unsupported PNG image header")
    return [
        "Image kind: PNG",
        f"Dimensions: {width} x {height}",
        f"Bit depth: {depth}; color type: {color}; interlaced: {bool(interlace)}",
        "Pixels and EXIF: not decoded or inspected",
    ]


def _jpeg(body: bytes) -> list[str]:
    if len(body) < 8 or not body.startswith(b"\xff\xd8"):
        raise ResearchFormatError("missing JPEG start marker")
    index, segments = 2, 0
    while index < len(body) and segments < 256:
        if body[index] != 0xff:
            raise ResearchFormatError("malformed JPEG marker framing")
        while index < len(body) and body[index] == 0xff:
            index += 1
        if index >= len(body):
            break
        marker = body[index]
        index += 1
        if marker in (0xd9, 0xda):
            break
        if marker in range(0xd0, 0xd8) or marker == 0x01:
            raise ResearchFormatError("unexpected JPEG standalone segment")
        if index + 2 > len(body):
            break
        length = struct.unpack(">H", body[index:index+2])[0]
        if length < 2 or index + length > len(body):
            raise ResearchFormatError("invalid JPEG segment length")
        segment = body[index+2:index+length]
        index += length
        segments += 1
        if marker in (0xc0, 0xc1, 0xc2, 0xc3):
            if len(segment) < 6:
                raise ResearchFormatError("incomplete JPEG SOF marker")
            depth = segment[0]
            height = struct.unpack(">H", segment[1:3])[0]
            width = struct.unpack(">H", segment[3:5])[0]
            components = segment[5]
            _dimensions(width, height)
            if depth not in (8, 12) or components not in (1, 3, 4):
                raise ResearchFormatError("unsupported JPEG sample format")
            return [
                "Image kind: JPEG",
                f"Dimensions: {width} x {height}",
                f"Sample depth: {depth}; components: {components}",
                "Pixels, embedded thumbnails and EXIF: not decoded or inspected",
            ]
    raise ResearchFormatError("no bounded JPEG dimension marker")


def _gif(body: bytes) -> list[str]:
    if len(body) < 13 or body[:6] not in (b"GIF87a", b"GIF89a"):
        raise ResearchFormatError("invalid GIF logical screen header")
    width, height = struct.unpack("<HH", body[6:10])
    _dimensions(width, height)
    return [
        "Image kind: GIF",
        f"Logical screen: {width} x {height}",
        "Frames, animation and pixel content: not decoded or inspected",
    ]


def _wave(body: bytes) -> list[str]:
    if (len(body) < 44 or body[:4] != b"RIFF"
            or body[8:12] != b"WAVE"):
        raise ResearchFormatError("invalid WAV RIFF signature")
    container_size = struct.unpack("<I", body[4:8])[0]
    if container_size + 8 != len(body):
        raise ResearchFormatError("WAV RIFF length mismatch")
    cursor, fmt, audio_bytes, chunks = 12, None, None, 0
    while cursor + 8 <= len(body):
        chunks += 1
        if chunks > 128:
            raise ResearchFormatError("WAV chunk count exceeded")
        tag = body[cursor:cursor+4]
        length = struct.unpack("<I", body[cursor+4:cursor+8])[0]
        cursor += 8
        if length > len(body) - cursor:
            raise ResearchFormatError("WAV chunk length invalid")
        data = body[cursor:cursor+length]
        cursor += length + (length % 2)
        if cursor > len(body):
            raise ResearchFormatError("WAV padding is incomplete")
        if tag == b"fmt ":
            if fmt is not None or len(data) < 16:
                raise ResearchFormatError("duplicate or incomplete WAV format")
            fmt = struct.unpack("<HHIIHH", data[:16])
        if tag == b"data":
            if audio_bytes is not None:
                raise ResearchFormatError("multiple WAV data chunks unsupported")
            audio_bytes = length
    if cursor != len(body) or fmt is None or audio_bytes is None:
        raise ResearchFormatError("incomplete WAV chunk stream")
    encoding, channels, sample_rate, byte_rate, block_align, bit_depth = fmt
    if (encoding != 1 or not 1 <= channels <= 8
            or not 8000 <= sample_rate <= 192000
            or bit_depth not in (8, 16, 24, 32)
            or block_align != channels * bit_depth // 8
            or byte_rate != sample_rate * block_align
            or audio_bytes % block_align):
        raise ResearchFormatError("unsupported or inconsistent WAV PCM format")
    duration = round(audio_bytes / byte_rate, 3)
    return [
        "Audio kind: WAV PCM",
        f"Channels: {channels}; sampling_hz: {sample_rate}; bits: {bit_depth}",
        f"Audio data bytes: {audio_bytes}; duration_seconds_from_header: {duration}",
        "Audio samples: not decoded, transcribed or executed",
    ]


def extract_binary_media_metadata(
    body: bytes, media_type: str, *, max_chars: int = 524288,
) -> ResearchProjection:
    if (type(body) is not bytes or len(body) > _MAX_BODY
            or type(max_chars) is not int or not 1 <= max_chars <= _MAX_BODY):
        raise ResearchFormatError("binary media exceeds read-only metadata limits")
    if media_type == "image/png":
        rows, title = _png(body), "PNG image metadata"
    elif media_type == "image/jpeg":
        rows, title = _jpeg(body), "JPEG image metadata"
    elif media_type == "image/gif":
        rows, title = _gif(body), "GIF image metadata"
    elif media_type in AUDIO_METADATA_TYPES:
        rows, title = _wave(body), "WAV audio metadata"
    else:
        raise ResearchFormatError("unapproved binary media type")
    return project_lines(rows, title=title, max_chars=max_chars)
