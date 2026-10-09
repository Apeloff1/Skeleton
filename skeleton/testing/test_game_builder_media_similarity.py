"""Media originality triage; synthetic samples only, no real game assets."""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from math import pi, sin
import struct
import wave

import pytest

from skeleton.ai.game_builder.media_similarity import (
    MediaScreenError, compare_media, fingerprint_image, fingerprint_wav,
)
from skeleton.ai.game_builder.plagiarism_guard import (
    AssetDeclaration, AssetDisposition, AttributionStatus, UseBasis,
    OriginalityDisposition, audit_game_originality,
)


def synthetic_png(*, invert=False):
    from PIL import Image
    im = Image.new("RGB", (72, 64))
    pixels = im.load()
    for y in range(64):
        for x in range(72):
            v = x * 3
            pixels[x, y] = ((255-v if invert else v), 30+y*2, (x+y)*2)
    out = BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


def synthetic_wav(*, invert_envelope=False):
    rate = 8000
    samples = []
    for i in range(rate):
        proportion = i / rate
        amplitude = (0.05 + 0.80 * (1.0-proportion if invert_envelope else proportion))
        samples.append(round(15000 * amplitude * sin(2*pi*220*i/rate)))
    out = BytesIO()
    with wave.open(out, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(struct.pack("<" + "h"*len(samples), *samples))
    return out.getvalue()


def assets_for_media():
    categories = (
        "artwork", "characters", "interface_appearance", "level_maps",
        "marketing_brand", "music_audio", "source_code", "story_dialogue",
    )
    return tuple(
        AssetDeclaration(
            category,
            AssetDisposition.INCLUDED if category in {"artwork", "music_audio"} else AssetDisposition.NOT_USED,
            basis=UseBasis.OWN_CREATION if category in {"artwork", "music_audio"} else None,
            provenance_sha256="b"*64 if category in {"artwork", "music_audio"} else None,
            author_identity="art and sound author" if category in {"artwork", "music_audio"} else None,
            attribution=AttributionStatus.NOT_REQUIRED,
            comparable_media_screened=True if category in {"artwork", "music_audio"} else False,
            reviewer_evidence_sha256="c"*64 if category in {"artwork", "music_audio"} else None,
        ) for category in categories
    )


def test_image_exact_and_perceptual_matches_are_review_signals_not_legal_findings():
    first = fingerprint_image("submitted", synthetic_png())
    identical = fingerprint_image("reference", synthetic_png())
    assert first.content_sha256 == identical.content_sha256
    finding = compare_media(first, identical)
    assert finding is not None
    assert finding.signal == "EXACT_MEDIA_BYTES"
    assert finding.matched_bytes
    assert finding.legal_infringement_determined is False
    reverse = fingerprint_image("reverse", synthetic_png(invert=True))
    assert compare_media(first, reverse) is None


def test_wav_exact_and_modified_audio_generate_bounded_fingerprints():
    a = fingerprint_wav("my-audio", synthetic_wav())
    b = fingerprint_wav("reference-audio", synthetic_wav())
    match = compare_media(a, b)
    assert match is not None and match.signal == "EXACT_MEDIA_BYTES"
    changed = bytearray(synthetic_wav())
    changed[-14] ^= 1
    near = compare_media(a, fingerprint_wav("modified", bytes(changed)))
    assert near is not None
    assert near.signal == "WAV_ENERGY_ENVELOPE_REVIEW"
    assert near.media_similarity_score is not None
    assert near.legal_infringement_determined is False


def test_image_and_audio_findings_are_separate_and_cannot_auto_clear():
    image = fingerprint_image("original-illustration", synthetic_png())
    image_match = compare_media(image, fingerprint_image("third-party", synthetic_png()))
    assert image_match is not None
    report = audit_game_originality(
        "new-homebrew", assets=assets_for_media(),
        candidate_samples=(), references=(),
        media_findings=(image_match,), artifact_sha256="a"*64,
    )
    assert report.disposition is OriginalityDisposition.HUMAN_REVIEW_REQUIRED
    assert len(report.media_overlap_findings) == 1
    assert report.public_receipt()["potential_media_matches"][0]["reference_id"] == "third-party"
    assert report.public_receipt()["legal_originality_certified"] is False
    assert report.release_permitted is False


def test_media_can_be_compared_without_storing_third_party_bytes_in_report():
    s = fingerprint_wav("own-music", synthetic_wav())
    r = fingerprint_wav("other-music", synthetic_wav(invert_envelope=True))
    finding = compare_media(s, r)
    # A negative triage finding is not a clean legal bill.
    if finding is not None:
        assert finding.legal_infringement_determined is False
    assert not s.release_safe


def test_cross_media_type_does_not_trigger_false_equivalence():
    image = fingerprint_image("screenshot", synthetic_png())
    audio = fingerprint_wav("music", synthetic_wav())
    assert compare_media(image, audio) is None


@pytest.mark.parametrize("data", [b"", b"not a png", b"x"*(12*1024*1024 + 1)])
def test_invalid_image_is_rejected_not_pretended_screened(data):
    with pytest.raises(MediaScreenError):
        fingerprint_image("bad", data)


@pytest.mark.parametrize("data", [b"", b"not a wav"])
def test_invalid_wav_is_rejected_not_pretended_screened(data):
    with pytest.raises(MediaScreenError):
        fingerprint_wav("bad", data)


def test_arbitrary_media_fingerprint_fields_fail_closed():
    with pytest.raises(MediaScreenError):
        compare_media("image", "audio")
