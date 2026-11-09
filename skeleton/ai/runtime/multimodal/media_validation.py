"""Bounded actual image and integer PCM WAVE verification.

These receipts prove local decoding and measured media parameters. They confer
no instruction authority and make no claims about OCR, transcription or content.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import struct
import wave
import zlib
from dataclasses import asdict, dataclass


class MediaValidationError(ValueError):
    """Media cannot be decoded within the declared resource limits."""


_CEILINGS = {
    "max_image_bytes": 32 * 1024 * 1024,
    "max_audio_bytes": 128 * 1024 * 1024,
    "max_pixels": 16_000_000,
    "max_dimension": 16_384,
    "max_decoded_bytes": 64 * 1024 * 1024,
    "max_audio_seconds": 3600,
    "max_sample_rate_hz": 192_000,
    "max_audio_channels": 8,
    "max_container_chunks": 1024,
    "max_metadata_bytes": 64 * 1024,
}


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise MediaValidationError(f"{name} must be lowercase sha256")
    return value


def _positive(value: object, name: str, ceiling: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= ceiling:
        raise MediaValidationError(f"{name} must be an integer in [1, {ceiling}]")
    return value


@dataclass(frozen=True, slots=True)
class MediaValidationLimits:
    max_image_bytes: int = _CEILINGS["max_image_bytes"]
    max_audio_bytes: int = _CEILINGS["max_audio_bytes"]
    max_pixels: int = _CEILINGS["max_pixels"]
    max_dimension: int = _CEILINGS["max_dimension"]
    max_decoded_bytes: int = _CEILINGS["max_decoded_bytes"]
    max_audio_seconds: int = _CEILINGS["max_audio_seconds"]
    max_sample_rate_hz: int = _CEILINGS["max_sample_rate_hz"]
    max_audio_channels: int = _CEILINGS["max_audio_channels"]
    max_container_chunks: int = _CEILINGS["max_container_chunks"]
    max_metadata_bytes: int = _CEILINGS["max_metadata_bytes"]

    def __post_init__(self) -> None:
        for name, ceiling in _CEILINGS.items():
            _positive(getattr(self, name), name, ceiling)

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MediaValidationReceipt:
    source_digest: str
    source_bytes: int
    media_type: str
    format: str
    decoder_ref: str
    decoded_digest: str
    decoded_bytes: int
    width: int | None
    height: int | None
    channels: int
    sample_rate_hz: int | None
    sample_count: int | None
    sample_width_bytes: int | None
    duration_seconds: float | None
    limits: MediaValidationLimits

    def __post_init__(self) -> None:
        _sha(self.source_digest, "source_digest")
        _sha(self.decoded_digest, "decoded_digest")
        if not isinstance(self.limits, MediaValidationLimits):
            raise MediaValidationError("receipt requires MediaValidationLimits")
        # Reconstruct bounds because frozen instances can still be corrupted by
        # privileged Python callers or malformed deserialization adapters.
        limits = MediaValidationLimits(**self.limits.as_dict())
        if not isinstance(self.decoder_ref, str) or not self.decoder_ref or len(self.decoder_ref) > 128:
            raise MediaValidationError("decoder_ref must be bounded nonempty text")
        _positive(self.decoded_bytes, "decoded_bytes", limits.max_decoded_bytes)
        if self.format in {"PNG", "JPEG", "WEBP"}:
            expected_mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[self.format]
            if self.media_type != expected_mime or self.channels != 4:
                raise MediaValidationError("image receipt format/channel mismatch")
            _positive(self.source_bytes, "source_bytes", limits.max_image_bytes)
            _positive(self.width, "width", limits.max_dimension)
            _positive(self.height, "height", limits.max_dimension)
            if (
                self.width * self.height > limits.max_pixels
                or self.decoded_bytes != self.width * self.height * 4
            ):
                raise MediaValidationError("image receipt dimensions exceed decoded bounds")
            if any(
                value is not None
                for value in (
                    self.sample_rate_hz,
                    self.sample_count,
                    self.sample_width_bytes,
                    self.duration_seconds,
                )
            ):
                raise MediaValidationError("image receipt contains audio parameters")
        elif self.format == "PCM_WAVE":
            if self.media_type != "audio/wav" or self.width is not None or self.height is not None:
                raise MediaValidationError("audio receipt format/geometry mismatch")
            _positive(self.source_bytes, "source_bytes", limits.max_audio_bytes)
            _positive(self.channels, "channels", limits.max_audio_channels)
            _positive(self.sample_rate_hz, "sample_rate_hz", limits.max_sample_rate_hz)
            _positive(self.sample_width_bytes, "sample_width_bytes", 4)
            _positive(self.sample_count, "sample_count", limits.max_decoded_bytes)
            if self.decoded_bytes != self.sample_count * self.channels * self.sample_width_bytes:
                raise MediaValidationError("audio receipt decoded byte count mismatch")
            duration = self.sample_count / self.sample_rate_hz
            if (
                isinstance(self.duration_seconds, bool)
                or not isinstance(self.duration_seconds, (float, int))
                or not math.isfinite(self.duration_seconds)
                or self.duration_seconds != duration
                or duration > limits.max_audio_seconds
            ):
                raise MediaValidationError("audio receipt duration mismatch or budget exceeded")
        else:
            raise MediaValidationError("unsupported verified media format")

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["schema_version"] = "skeleton.ai.multimodal_media_validation.v1"
        return payload

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.as_dict()).encode("utf-8")).hexdigest()

    @property
    def measured_metadata(self) -> dict[str, object]:
        if self.width is not None:
            return {"width": self.width, "height": self.height, "format": self.format}
        return {
            "sample_rate": self.sample_rate_hz,
            "duration_ms": self.duration_seconds * 1000,
            "channels": self.channels,
            "sample_width_bits": self.sample_width_bytes * 8,
            "frame_count": self.sample_count,
        }


def _geometry(width: int, height: int, limits: MediaValidationLimits) -> None:
    _positive(width, "width", limits.max_dimension)
    _positive(height, "height", limits.max_dimension)
    if width * height > limits.max_pixels or width * height * 4 > limits.max_decoded_bytes:
        raise MediaValidationError("image pixel/decoded byte budget exceeded")


def _png(payload: bytes, limits: MediaValidationLimits) -> tuple[int, int]:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise MediaValidationError("PNG signature mismatch")
    cursor = 8
    chunks = 0
    dimensions = None
    compressed = []
    data_ended = False
    palette_seen = False
    ended = False
    while cursor < len(payload):
        chunks += 1
        if chunks > limits.max_container_chunks or cursor + 12 > len(payload):
            raise MediaValidationError("PNG chunk budget exceeded or truncated chunk")
        (length,) = struct.unpack_from(">I", payload, cursor)
        kind = payload[cursor + 4 : cursor + 8]
        end = cursor + 12 + length
        if end > len(payload):
            raise MediaValidationError("truncated PNG chunk")
        data = memoryview(payload)[cursor + 8 : cursor + 8 + length]
        (expected_crc,) = struct.unpack_from(">I", payload, cursor + 8 + length)
        if zlib.crc32(data, zlib.crc32(kind)) & 0xFFFFFFFF != expected_crc:
            raise MediaValidationError("PNG chunk CRC mismatch")
        if dimensions is None and kind != b"IHDR":
            raise MediaValidationError("PNG must start with IHDR")
        if kind == b"IHDR":
            if dimensions is not None or length != 13:
                raise MediaValidationError("invalid or duplicate PNG IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", data)
            _geometry(width, height, limits)
            depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if depth not in depths.get(color, set()) or compression != 0 or filtering != 0 or interlace != 0:
                raise MediaValidationError("unsupported PNG coding or interlace")
            dimensions = width, height, depth, color
        elif kind == b"PLTE":
            if palette_seen or compressed or not 3 <= length <= 768 or length % 3:
                raise MediaValidationError("invalid PNG palette")
            palette_seen = True
        elif kind == b"IDAT":
            if data_ended or (dimensions[3] == 3 and not palette_seen):
                raise MediaValidationError("invalid PNG data ordering")
            compressed.append(data)
        elif kind == b"IEND":
            if length or not compressed or end != len(payload):
                raise MediaValidationError("invalid PNG end or trailing bytes")
            ended = True
            break
        else:
            if kind == b"acTL" or not all(65 <= byte <= 90 or 97 <= byte <= 122 for byte in kind):
                raise MediaValidationError("animated PNG or invalid chunk type")
            if kind[0] & 32 == 0:
                raise MediaValidationError("unsupported critical PNG chunk")
            if compressed:
                data_ended = True
        cursor = end
    if not ended or dimensions is None:
        raise MediaValidationError("PNG is incomplete")
    width, height, depth, color = dimensions
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    stride = (width * depth * channels + 7) // 8
    expected = height * (stride + 1)
    if expected > limits.max_decoded_bytes:
        raise MediaValidationError("PNG scanline decoded byte budget exceeded")
    decoder = zlib.decompressobj()
    try:
        decoded = decoder.decompress(b"".join(compressed), expected + 1)
    except zlib.error as exc:
        raise MediaValidationError("invalid PNG compressed data") from exc
    if len(decoded) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise MediaValidationError("PNG compressed data length mismatch or decompression bomb")
    if any(decoded[row * (stride + 1)] > 4 for row in range(height)):
        raise MediaValidationError("invalid PNG scanline filter")
    return width, height


def _jpeg(payload: bytes, limits: MediaValidationLimits) -> tuple[int, int]:
    if not payload.startswith(b"\xff\xd8"):
        raise MediaValidationError("JPEG signature mismatch")
    cursor = 2
    dimensions = None
    scans = 0
    markers = 0
    while cursor < len(payload):
        markers += 1
        if markers > limits.max_container_chunks or payload[cursor] != 0xFF:
            raise MediaValidationError("JPEG marker budget exceeded or corrupt marker")
        cursor += 1
        while cursor < len(payload) and payload[cursor] == 0xFF:
            cursor += 1
        if cursor >= len(payload):
            raise MediaValidationError("truncated JPEG marker")
        marker = payload[cursor]
        cursor += 1
        if marker == 0xD9:
            if dimensions is None or scans == 0 or cursor != len(payload):
                raise MediaValidationError("invalid JPEG end or trailing bytes")
            return dimensions
        if marker in {0x00, 0x01, 0xD8} or 0xD0 <= marker <= 0xD7 or cursor + 2 > len(payload):
            raise MediaValidationError("invalid JPEG marker ordering")
        length = int.from_bytes(payload[cursor : cursor + 2], "big")
        end = cursor + length
        if length < 2 or end > len(payload):
            raise MediaValidationError("truncated JPEG segment")
        if marker in {0xC0, 0xC1, 0xC2}:
            if dimensions is not None or length < 8 or payload[cursor + 2] != 8:
                raise MediaValidationError("unsupported JPEG sample coding")
            height = int.from_bytes(payload[cursor + 3 : cursor + 5], "big")
            width = int.from_bytes(payload[cursor + 5 : cursor + 7], "big")
            _geometry(width, height, limits)
            dimensions = width, height
        cursor = end
        if marker == 0xDA:
            if dimensions is None or length < 6:
                raise MediaValidationError("invalid JPEG scan header")
            scans += 1
            while True:
                start = payload.find(b"\xff", cursor)
                if start < 0:
                    raise MediaValidationError("truncated JPEG scan")
                cursor = start + 1
                while cursor < len(payload) and payload[cursor] == 0xFF:
                    cursor += 1
                if cursor >= len(payload):
                    raise MediaValidationError("truncated JPEG scan marker")
                code = payload[cursor]
                if code == 0 or 0xD0 <= code <= 0xD7:
                    if code != 0:
                        markers += 1
                        if markers > limits.max_container_chunks:
                            raise MediaValidationError("JPEG marker budget exceeded")
                    cursor += 1
                    continue
                cursor = start
                break
    raise MediaValidationError("JPEG is incomplete")


def _webp(payload: bytes, limits: MediaValidationLimits) -> None:
    if (
        len(payload) < 12
        or payload[:4] != b"RIFF"
        or payload[8:12] != b"WEBP"
        or int.from_bytes(payload[4:8], "little") != len(payload) - 8
    ):
        raise MediaValidationError("WebP container length/signature mismatch")
    cursor = 12
    chunks = 0
    pixel_chunks = 0
    while cursor < len(payload):
        chunks += 1
        if chunks > limits.max_container_chunks or cursor + 8 > len(payload):
            raise MediaValidationError("WebP chunk budget exceeded or truncated chunk")
        kind = payload[cursor : cursor + 4]
        length = int.from_bytes(payload[cursor + 4 : cursor + 8], "little")
        end = cursor + 8 + length
        padded_end = end + (length % 2)
        if padded_end > len(payload) or (length % 2 and payload[end] != 0):
            raise MediaValidationError("truncated WebP chunk or invalid padding")
        if kind in {b"ANIM", b"ANMF"}:
            raise MediaValidationError("animated WebP is outside verified intake")
        if kind in {b"VP8 ", b"VP8L"}:
            pixel_chunks += 1
        cursor = padded_end
    if pixel_chunks != 1:
        raise MediaValidationError("WebP requires exactly one coded image")


def _image(payload: bytes, mime: str, limits: MediaValidationLimits) -> MediaValidationReceipt:
    formats = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
    if mime not in formats:
        raise MediaValidationError("unsupported verified image MIME")
    dimensions = None
    if mime == "image/png":
        dimensions = _png(payload, limits)
    elif mime == "image/jpeg":
        dimensions = _jpeg(payload, limits)
    else:
        _webp(payload, limits)
    try:
        from PIL import Image, ImageFile
        from PIL import __version__ as pillow_version
    except ImportError as exc:
        raise MediaValidationError("verified images require the local Pillow decoder") from exc
    if ImageFile.LOAD_TRUNCATED_IMAGES:
        raise MediaValidationError("permissive truncated-image decoder configuration is forbidden")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            if image.format != formats[mime] or getattr(image, "n_frames", 1) != 1:
                raise MediaValidationError("image MIME/actual format mismatch or animation")
            width, height = image.size
            _geometry(width, height, limits)
            if dimensions is not None and dimensions != image.size:
                raise MediaValidationError("image decoder/header dimension mismatch")
            image.verify()
        with Image.open(io.BytesIO(payload)) as image:
            _geometry(*image.size, limits)
            image.load()
            with image.convert("RGBA") as rgba:
                decoded = rgba.tobytes()
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise MediaValidationError("image decoding failed") from exc
    if ImageFile.LOAD_TRUNCATED_IMAGES or len(decoded) != width * height * 4:
        raise MediaValidationError("image decoder configuration/output changed")
    return MediaValidationReceipt(
        hashlib.sha256(payload).hexdigest(),
        len(payload),
        mime,
        formats[mime],
        f"Pillow@{pillow_version}:RGBA:v1",
        hashlib.sha256(decoded).hexdigest(),
        len(decoded),
        width,
        height,
        4,
        None,
        None,
        None,
        None,
        limits,
    )


def _wave(payload: bytes, limits: MediaValidationLimits) -> MediaValidationReceipt:
    if (
        len(payload) < 12
        or payload[:4] != b"RIFF"
        or payload[8:12] != b"WAVE"
        or int.from_bytes(payload[4:8], "little") != len(payload) - 8
    ):
        raise MediaValidationError("WAVE RIFF signature/length mismatch")
    cursor = 12
    chunks = 0
    parameters = None
    samples = None
    while cursor < len(payload):
        chunks += 1
        if chunks > limits.max_container_chunks or cursor + 8 > len(payload):
            raise MediaValidationError("WAVE chunk budget exceeded or truncated chunk")
        kind = payload[cursor : cursor + 4]
        length = int.from_bytes(payload[cursor + 4 : cursor + 8], "little")
        end = cursor + 8 + length
        padded_end = end + (length % 2)
        if padded_end > len(payload) or (length % 2 and payload[end] != 0):
            raise MediaValidationError("truncated WAVE chunk or invalid padding")
        data = memoryview(payload)[cursor + 8 : end]
        if kind == b"fmt ":
            if parameters is not None or samples is not None or length not in {16, 18}:
                raise MediaValidationError("invalid or duplicate WAVE format")
            encoding, channels, rate, byte_rate, alignment, bits = struct.unpack_from("<HHIIHH", data)
            _positive(channels, "channels", limits.max_audio_channels)
            _positive(rate, "sample_rate_hz", limits.max_sample_rate_hz)
            if (
                encoding != 1
                or bits not in {8, 16, 24, 32}
                or alignment != channels * (bits // 8)
                or byte_rate != rate * alignment
                or (length == 18 and bytes(data[16:]) != b"\0\0")
            ):
                raise MediaValidationError("WAVE requires consistent integer PCM parameters")
            parameters = channels, rate, bits // 8, alignment
        elif kind == b"data":
            if samples is not None or parameters is None or length == 0 or length % parameters[3]:
                raise MediaValidationError("invalid WAVE sample data ordering/alignment")
            if length > limits.max_decoded_bytes:
                raise MediaValidationError("WAVE decoded byte budget exceeded")
            frames = length // parameters[3]
            if frames / parameters[1] > limits.max_audio_seconds:
                raise MediaValidationError("WAVE duration budget exceeded")
            samples = data
        cursor = padded_end
    if parameters is None or samples is None:
        raise MediaValidationError("WAVE requires PCM format and sample data")
    channels, rate, sample_width, _ = parameters
    frames = len(samples) // (channels * sample_width)
    try:
        with wave.open(io.BytesIO(payload), "rb") as audio:
            if (audio.getnchannels(), audio.getframerate(), audio.getsampwidth(), audio.getnframes()) != (
                channels,
                rate,
                sample_width,
                frames,
            ) or audio.getcomptype() != "NONE":
                raise MediaValidationError("WAVE decoder/header parameter mismatch")
            decoded = audio.readframes(frames + 1)
    except (wave.Error, EOFError, OSError) as exc:
        raise MediaValidationError("PCM WAVE decoding failed") from exc
    if decoded != samples:
        raise MediaValidationError("WAVE decoder sample mismatch or truncated frames")
    return MediaValidationReceipt(
        hashlib.sha256(payload).hexdigest(),
        len(payload),
        "audio/wav",
        "PCM_WAVE",
        "python.wave:integer-PCM:v1",
        hashlib.sha256(decoded).hexdigest(),
        len(decoded),
        None,
        None,
        channels,
        rate,
        frames,
        sample_width,
        frames / rate,
        limits,
    )


def validate_media(
    payload: bytes, *, modality: str, mime_type: str, limits: MediaValidationLimits | None = None
) -> MediaValidationReceipt:
    if not isinstance(payload, bytes):
        raise MediaValidationError("media payload must be immutable bytes")
    if limits is None:
        limits = MediaValidationLimits()
    if not isinstance(limits, MediaValidationLimits):
        raise MediaValidationError("limits must be MediaValidationLimits")
    limits = MediaValidationLimits(**limits.as_dict())
    if modality not in {"image", "audio"} or not isinstance(mime_type, str):
        raise MediaValidationError("verified intake supports only image and PCM WAVE audio")
    maximum = limits.max_image_bytes if modality == "image" else limits.max_audio_bytes
    if not payload or len(payload) > maximum:
        raise MediaValidationError("media source byte budget exceeded or empty payload")
    mime = mime_type.strip().casefold()
    if modality == "image":
        return _image(payload, mime, limits)
    if mime != "audio/wav":
        raise MediaValidationError("verified audio supports only PCM audio/wav")
    return _wave(payload, limits)
