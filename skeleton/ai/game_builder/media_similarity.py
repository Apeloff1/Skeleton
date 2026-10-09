"""Local audio/image overlap triage; outputs fingerprints, never media copies.

Exact hashes are strong evidence that bytes match. Perceptual similarity is
ONLY a human-review trigger, not a legal infringement score. Audio comparison
supports safe bounded PCM WAV; visual comparison requires optional Pillow.
Other formats must be reviewed separately, not silently labelled plagiarism
free. Callers must lawfully possess reference content.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from math import sqrt
import struct
import wave

_MAX_IMAGE_PIXELS = 16_000_000
_MAX_MEDIA_BYTES = 12 * 1024 * 1024
_MAX_WAV_FRAMES = 3_000_000
_WINDOWS = 128


class MediaScreenError(ValueError):
    """Unsupported, malformed or unbounded media evidence."""


@dataclass(frozen=True, slots=True)
class MediaFingerprint:
    media_id: str
    category: str
    content_sha256: str
    feature: tuple[float, ...] | int
    length_or_pixels: int
    raw_bytes_evaluated: bool = True
    release_safe: bool = False


@dataclass(frozen=True, slots=True)
class MediaMatchEvidence:
    submitted_id: str
    reference_id: str
    category: str
    submitted_sha256: str
    reference_sha256: str
    signal: str
    matched_bytes: bool
    media_similarity_score: float | None
    legal_infringement_determined: bool = False


def fingerprint_image(media_id: str, data: bytes) -> MediaFingerprint:
    """dHash triage for images; no OCR or reproducing reference images."""
    _check_input(media_id, data)
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:
        raise MediaScreenError("Pillow visual reviewer is unavailable; do not mark artwork screened") from exc
    try:
        with Image.open(BytesIO(data)) as original:
            w, h = original.size
            if w <= 0 or h <= 0 or w * h > _MAX_IMAGE_PIXELS:
                raise MediaScreenError("pixel budget exceeded")
            if original.format not in ("PNG", "JPEG", "WEBP", "GIF"):
                raise MediaScreenError("unsupported image media type")
            im = ImageOps.exif_transpose(original)
            im.load()
            gray = im.convert("L").resize((9, 8), resample=Image.Resampling.LANCZOS)
            pixels = list(gray.getdata())
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise MediaScreenError("unreadable or oversized visual evidence") from exc
    bitfield = 0
    for y in range(8):
        for x in range(8):
            bitfield = (bitfield << 1) | int(pixels[y*9 + x] > pixels[y*9 + x + 1])
    return MediaFingerprint(media_id, "artwork", sha256(data).hexdigest(), bitfield, w*h)


def fingerprint_wav(media_id: str, data: bytes) -> MediaFingerprint:
    """Sample-window energy envelope; detects some close PCM duplicates."""
    _check_input(media_id, data)
    try:
        with wave.open(BytesIO(data), "rb") as audio:
            nframes = audio.getnframes()
            rate = audio.getframerate()
            channels = audio.getnchannels()
            width = audio.getsampwidth()
            if (audio.getcomptype() != "NONE" or channels not in (1, 2)
                or width not in (1, 2) or nframes < _WINDOWS
                or nframes > _MAX_WAV_FRAMES or rate <= 0):
                raise MediaScreenError("unsupported PCM WAV characteristics")
            raw = audio.readframes(nframes)
    except (EOFError, OSError, ValueError, wave.Error) as exc:
        raise MediaScreenError("unreadable PCM WAV reference") from exc
    expected = nframes * channels * width
    if len(raw) != expected:
        raise MediaScreenError("truncated PCM WAV data")
    energy = [0.0] * _WINDOWS
    count = [0] * _WINDOWS
    if width == 2:
        samples = (item[0] / 32768.0 for item in struct.iter_unpack("<h", raw))
    else:
        samples = ((value - 128) / 128.0 for value in raw)
    channel_sums = 0.0
    for index, sample in enumerate(samples):
        channel_sums += sample
        if index % channels != channels - 1:
            continue
        frame = index // channels
        block = min(_WINDOWS - 1, frame * _WINDOWS // nframes)
        energy[block] += abs(channel_sums / channels)
        count[block] += 1
        channel_sums = 0.0
    env = [energy[i] / max(1, count[i]) for i in range(_WINDOWS)]
    maximum = max(env)
    if maximum <= 1e-9:
        normalized = tuple(0.0 for _ in env)
    else:
        normalized = tuple(round(x / maximum, 6) for x in env)
    return MediaFingerprint(media_id, "music_audio", sha256(data).hexdigest(), normalized, nframes)


def compare_media(
    submitted: MediaFingerprint, reference: MediaFingerprint,
) -> MediaMatchEvidence | None:
    """Flag exact bytes and close *candidate* media; no legal threshold."""
    if not isinstance(submitted, MediaFingerprint) or not isinstance(reference, MediaFingerprint):
        raise MediaScreenError("typed media fingerprints required")
    if submitted.category != reference.category:
        return None
    same_bytes = submitted.content_sha256 == reference.content_sha256
    score = None
    signal = None
    if same_bytes:
        signal, score = "EXACT_MEDIA_BYTES", 1.0
    elif submitted.category == "artwork":
        if type(submitted.feature) is not int or type(reference.feature) is not int:
            raise MediaScreenError("incompatible image hashes")
        # dHash has many collisions on blank/low-information imagery. Even
        # a near match may be a false positive, not legal copying.
        bit_diff = (submitted.feature ^ reference.feature).bit_count()
        if bit_diff <= 7:
            signal, score = "VISUAL_PERCEPTUAL_REVIEW", round(1 - bit_diff/64, 6)
    elif submitted.category == "music_audio":
        if not isinstance(submitted.feature, tuple) or not isinstance(reference.feature, tuple):
            raise MediaScreenError("incompatible audio feature vectors")
        if len(submitted.feature) != _WINDOWS or len(reference.feature) != _WINDOWS:
            raise MediaScreenError("unsupported audio window count")
        ratio = submitted.length_or_pixels / max(1, reference.length_or_pixels)
        if 0.92 <= ratio <= 1.08:
            left, right = submitted.feature, reference.feature
            delta = sum(abs(a - b) for a, b in zip(left, right)) / _WINDOWS
            if delta <= 0.055 and max(left) > 0.03 and max(right) > 0.03:
                signal, score = "WAV_ENERGY_ENVELOPE_REVIEW", round(1 - delta, 6)
    if signal is None:
        return None
    return MediaMatchEvidence(
        submitted.media_id, reference.media_id, submitted.category,
        submitted.content_sha256, reference.content_sha256, signal,
        same_bytes, score,
    )


def _check_input(media_id: str, data: bytes) -> None:
    if not isinstance(media_id, str) or not media_id or len(media_id) > 128:
        raise MediaScreenError("invalid media identifier")
    if type(data) is not bytes or not 1 <= len(data) <= _MAX_MEDIA_BYTES:
        raise MediaScreenError("unsupported/bounded media bytes required")
