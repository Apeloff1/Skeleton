"""Verified image/PCM bytes, temporal provenance and actual fusion scoring."""

from __future__ import annotations

import io
import wave
from dataclasses import replace

import pytest
from PIL import Image

from skeleton.ai.runtime.learning_foundation.multimodal import (
    LearningModality,
    MultimodalCorpus,
    MultimodalFoundationError,
)
from skeleton.ai.runtime.learning_foundation.temporal import (
    TimedMediaFragment,
    VideoEvidenceIndex,
)


def png(color):
    output = io.BytesIO()
    Image.new("RGB", (2, 2), color).save(output, format="PNG")
    return output.getvalue()


def wav(value):
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8000)
        writer.writeframes(value.to_bytes(2, "little") * 2000)
    return output.getvalue()


def parent(corpus, name="video", *, simulated=False, rights=("rights:clip",)):
    return corpus.ingest(
        record_id=name,
        modality=LearningModality.VIDEO,
        media_type="video/mp4",
        payload=f"declared-container:{name}".encode(),
        source_refs=("source:clip",),
        rights_refs=rights,
        metadata={"duration_ms": 2000},
        simulated=simulated,
    )


def fragment(
    corpus,
    root,
    *,
    name="image",
    modality=LearningModality.IMAGE,
    text="red bus",
    color="red",
    value=1,
    verified=True,
    rights=None,
    sources=None,
    lineage=None,
    simulated=None,
):
    return corpus.ingest(
        record_id=name,
        modality=modality,
        media_type="image/png" if modality is LearningModality.IMAGE else "audio/wav",
        payload=png(color) if modality is LearningModality.IMAGE else wav(value),
        source_refs=root.source_refs if sources is None else sources,
        rights_refs=root.rights_refs if rights is None else rights,
        lineage_refs=(root.digest,) if lineage is None else lineage,
        extracted_text=text,
        extractor_ref="operator:semantic-declaration",
        verified=verified,
        simulated=root.simulated if simulated is None else simulated,
    )


def fixture():
    corpus = MultimodalCorpus()
    root = parent(corpus)
    image = fragment(corpus, root)
    audio = fragment(corpus, root, name="audio", modality=LearningModality.AUDIO, text="bus stop", value=2)
    index = VideoEvidenceIndex(corpus)
    spans = (TimedMediaFragment(image.record_id, 0.1, 0.1, 3), TimedMediaFragment(audio.record_id, 0.1, 0.35))
    receipt = index.bind(timeline_id="clip", parent_record_id=root.record_id, fragments=spans)
    return corpus, root, image, audio, index, receipt


def search(index, query="red bus", **kwargs):
    return index.search(query, timeline_ids=("clip",), allowed_rights_refs=("rights:clip",), **kwargs)


def test_actual_cross_modal_scores_are_bounded_deterministic_and_content_bound():
    corpus, root, image, audio, index, receipt = fixture()
    hit = search(index)[0]
    assert hit.score == pytest.approx((2 * 1 + 1 / 3) / 3)
    assert hit.modality_scores == ((LearningModality.IMAGE, 1.0), (LearningModality.AUDIO, 1 / 3))
    assert hit == search(index)[0]
    assert hit.parent_record_digest == root.digest
    assert hit.parent_asset_digest == root.asset_digest
    assert hit.timeline_digest == receipt.digest
    assert tuple(item.record_digest for item in hit.fragments) == (image.digest, audio.digest)
    assert tuple(item.projection_digest for item in hit.fragments) == (
        image.text_projection.digest,
        audio.text_projection.digest,
    )
    assert corpus.store.get(image.asset_digest) == png("red")
    assert corpus.store.get(audio.asset_digest) == wav(2)
    assert hit.instruction_trusted is False
    assert hit.source_refs == root.source_refs and hit.rights_refs == root.rights_refs
    assert 0 < hit.score <= 1


def test_missing_modality_contributes_zero_and_explicit_weights_change_actual_rank():
    _, root, image, _, index, _ = fixture()
    index.bind(
        timeline_id="vision",
        parent_record_id=root.record_id,
        fragments=(TimedMediaFragment(image.record_id, 0.1, 0.1, 3),),
    )
    hits = index.search("red bus", timeline_ids=("vision", "clip"), allowed_rights_refs=("rights:clip",))
    assert [item.timeline_id for item in hits] == ["clip", "vision"]
    assert hits[1].score == 2 / 3
    assert hits[1].modality_scores[1] == (LearningModality.AUDIO, 0.0)
    audio_only = search(index, weights={LearningModality.AUDIO: 1})[0]
    assert audio_only.score == 1 / 3
    assert len(audio_only.fragments) == 1 and audio_only.fragments[0].modality is LearningModality.AUDIO


def test_time_window_filters_before_fusion_and_point_end_is_excluded():
    _, _, _, _, index, _ = fixture()
    hit = search(index, window_seconds=(0.2, 0.3))[0]
    assert hit.score == 1 / 9
    assert hit.modality_scores[0][1] == 0
    assert len(hit.fragments) == 1
    assert search(index, window_seconds=(0, 0.1)) == ()
    assert search(index, window_seconds=(0.35, 1)) == ()


def test_rights_simulation_filters_precede_source_reads_and_ranking():
    corpus, root, image, _, index, _ = fixture()
    restricted = parent(corpus, "restricted", rights=("rights:private",))
    private_image = fragment(corpus, restricted, name="private-image", color="blue")
    index.bind(
        timeline_id="private",
        parent_record_id=restricted.record_id,
        fragments=(TimedMediaFragment(private_image.record_id, 0.1, 0.1, 1),),
    )
    simulated = parent(corpus, "simulated", simulated=True)
    sim_image = fragment(corpus, simulated, name="sim-image", color="green")
    index.bind(
        timeline_id="simulation",
        parent_record_id=simulated.record_id,
        fragments=(TimedMediaFragment(sim_image.record_id, 0.1, 0.1, 1),),
    )
    # Corruption outside rights/simulation scope cannot pollute eligible evidence.
    corpus.store._objects[private_image.asset_digest] = b"corrupt private"
    corpus.store._objects[sim_image.asset_digest] = b"corrupt simulated"
    hits = index.search(
        "red bus", timeline_ids=("private", "simulation", "clip"), allowed_rights_refs=("rights:clip",)
    )
    assert [item.timeline_id for item in hits] == ["clip"]
    assert hits[0].fragments[0].asset_digest == image.asset_digest
    with pytest.raises(MultimodalFoundationError):
        index.search(
            "red bus",
            timeline_ids=("simulation",),
            allowed_rights_refs=("rights:clip",),
            include_simulated=True,
        )
    with pytest.raises(MultimodalFoundationError):
        index.search("red bus", timeline_ids=("private",), allowed_rights_refs=("rights:private",))
    assert root.digest == hits[0].parent_record_digest


@pytest.mark.parametrize(
    "arguments",
    [
        {"verified": False},
        {"rights": ("unrelated",)},
        {"sources": ("unrelated",)},
        {"lineage": ()},
        {"simulated": True},
    ],
)
def test_fragment_without_verified_parent_provenance_cannot_bind(arguments):
    corpus = MultimodalCorpus()
    root = parent(corpus)
    record = fragment(corpus, root, **arguments)
    index = VideoEvidenceIndex(corpus)
    with pytest.raises(MultimodalFoundationError):
        index.bind(
            timeline_id="bad",
            parent_record_id=root.record_id,
            fragments=(TimedMediaFragment(record.record_id, 0.1, 0.1, 0),),
        )
    assert index._timelines == {} and index._digests == {}


@pytest.mark.parametrize(
    "case", ["audio_duration", "image_span", "image_index", "outside", "audio_index", "duplicate"]
)
def test_bad_temporal_fragments_cannot_publish_timeline(case):
    _, root, image, audio, index, _ = fixture()
    mapping = {
        "audio_duration": (TimedMediaFragment(audio.record_id, 0, 0.3),),
        "image_span": (TimedMediaFragment(image.record_id, 0, 0.1, 0),),
        "image_index": (TimedMediaFragment(image.record_id, 0.1, 0.1),),
        "outside": (TimedMediaFragment(image.record_id, 2, 2, 0),),
        "audio_index": (TimedMediaFragment(audio.record_id, 0, 0.25, 1),),
        "duplicate": (
            TimedMediaFragment(image.record_id, 0.1, 0.1, 0),
            TimedMediaFragment(image.record_id, 0.2, 0.2, 1),
        ),
    }
    before = dict(index._timelines)
    with pytest.raises(MultimodalFoundationError):
        index.bind(timeline_id="bad", parent_record_id=root.record_id, fragments=mapping[case])
    assert index._timelines == before and "bad" not in index._digests


@pytest.mark.parametrize("case", ["frame_regression", "index_regression", "audio_overlap"])
def test_order_fences_real_additional_media(case):
    corpus, root, image, audio, index, _ = fixture()
    if case == "audio_overlap":
        extra = fragment(corpus, root, name="extra-audio", modality=LearningModality.AUDIO, value=3)
        spans = (TimedMediaFragment(audio.record_id, 0, 0.25), TimedMediaFragment(extra.record_id, 0.2, 0.45))
    else:
        extra = fragment(corpus, root, name="extra-image", color="blue")
        spans = (
            TimedMediaFragment(image.record_id, 0.2, 0.2, 4),
            TimedMediaFragment(
                extra.record_id,
                0.1 if case == "frame_regression" else 0.3,
                0.1 if case == "frame_regression" else 0.3,
                5 if case == "frame_regression" else 3,
            ),
        )
    with pytest.raises(MultimodalFoundationError):
        index.bind(timeline_id="unordered", parent_record_id=root.record_id, fragments=spans)
    assert "unordered" not in index._timelines


def test_best_per_modality_score_prevents_frame_oversampling_inflation():
    corpus, root, image, audio, index, receipt = fixture()
    extra = fragment(corpus, root, name="extra", color="blue")
    index.bind(
        timeline_id="many",
        parent_record_id=root.record_id,
        fragments=(
            receipt.fragments[0].fragment,
            TimedMediaFragment(extra.record_id, 0.2, 0.2, 4),
            receipt.fragments[1].fragment,
        ),
    )
    hits = index.search("red bus", timeline_ids=("clip", "many"), allowed_rights_refs=("rights:clip",))
    assert hits[0].score == hits[1].score
    assert [hit.timeline_id for hit in hits] == ["clip", "many"]
    assert hits[0].fragments[0].record_digest == image.digest
    assert hits[0].fragments[1].record_digest == audio.digest


def test_binding_exact_retry_conflicting_reuse_and_frozen_receipt_mutation():
    _, root, _, _, index, receipt = fixture()
    assert (
        index.bind(
            timeline_id="clip",
            parent_record_id=root.record_id,
            fragments=tuple(item.fragment for item in receipt.fragments),
        )
        is receipt
    )
    with pytest.raises(MultimodalFoundationError, match="conflict"):
        index.bind(
            timeline_id="clip",
            parent_record_id=root.record_id,
            fragments=(replace(receipt.fragments[0].fragment, start_seconds=0.2, end_seconds=0.2),),
        )
    object.__setattr__(receipt, "duration_seconds", 7)
    with pytest.raises(MultimodalFoundationError, match="drift"):
        search(index)


@pytest.mark.parametrize("corruption", ["source", "projection", "decoder"])
def test_issued_content_and_projection_corruption_cannot_supply_scores(corruption):
    corpus, _, image, _, index, _ = fixture()
    if corruption == "source":
        corpus.store._objects[image.asset_digest] = b"fake frame"
    elif corruption == "projection":
        corpus._text[image.record_id] = "red bus plus fabricated text"
    else:
        object.__setattr__(corpus.intake._assets[image.record_id].validation, "decoded_digest", "0" * 64)
    with pytest.raises(MultimodalFoundationError):
        search(index)


@pytest.mark.parametrize(
    "options",
    [
        {"weights": {LearningModality.IMAGE: True}},
        {"weights": {LearningModality.VIDEO: 1}},
        {"weights": {}},
        {"include_simulated": 1},
        {"limit": True},
        {"window_seconds": (1, 0)},
        {"window_seconds": [0, 1]},
    ],
)
def test_invalid_query_policy_denied(options):
    _, _, _, _, index, _ = fixture()
    with pytest.raises(MultimodalFoundationError):
        search(index, **options)


def test_fragment_extra_rights_cannot_escape_query_scope():
    corpus = MultimodalCorpus()
    root = parent(corpus)
    image = fragment(corpus, root, rights=("rights:clip", "rights:derived"))
    index = VideoEvidenceIndex(corpus)
    index.bind(
        timeline_id="clip",
        parent_record_id=root.record_id,
        fragments=(TimedMediaFragment(image.record_id, 0, 0, 0),),
    )
    assert search(index) == ()
    assert (
        index.search(
            "red bus", timeline_ids=("clip",), allowed_rights_refs=("rights:clip", "rights:derived")
        )[0].score
        == 2 / 3
    )


def test_disallowed_fragment_corruption_is_filtered_before_source_verification():
    corpus, root, image, _, index, _ = fixture()
    private_audio = fragment(
        corpus,
        root,
        name="private-audio",
        modality=LearningModality.AUDIO,
        value=4,
        rights=("rights:clip", "rights:private"),
    )
    index.bind(
        timeline_id="mixed",
        parent_record_id=root.record_id,
        fragments=(
            TimedMediaFragment(image.record_id, 0.1, 0.1, 3),
            TimedMediaFragment(private_audio.record_id, 0.1, 0.35),
        ),
    )
    corpus.store._objects[private_audio.asset_digest] = b"corrupt excluded audio"
    hits = index.search("red bus", timeline_ids=("mixed",), allowed_rights_refs=("rights:clip",))
    assert hits[0].score == 2 / 3
    assert len(hits[0].fragments) == 1
    with pytest.raises(MultimodalFoundationError):
        index.search(
            "red bus", timeline_ids=("mixed",), allowed_rights_refs=("rights:clip", "rights:private")
        )


def test_source_byte_bound_denies_before_hashing_or_decoding(monkeypatch):
    corpus = MultimodalCorpus()
    root = parent(corpus)
    image = fragment(corpus, root)
    index = VideoEvidenceIndex(corpus, max_source_bytes=1)

    def forbidden(*args, **kwargs):
        raise AssertionError("source bytes must be admitted before hash/decode")

    monkeypatch.setattr(corpus, "get", forbidden)
    with pytest.raises(MultimodalFoundationError, match="byte budget"):
        index.bind(
            timeline_id="oversized",
            parent_record_id=root.record_id,
            fragments=(TimedMediaFragment(image.record_id, 0.1, 0.1, 3),),
        )
    assert not index._timelines


def test_query_cumulative_source_byte_limit_precedes_second_source_verification(monkeypatch):
    corpus = MultimodalCorpus()
    first = parent(corpus)
    image = fragment(corpus, first)
    second = parent(corpus, "other-video")
    other_image = fragment(corpus, second, name="other-image", color="blue")
    per_first = len(corpus.store.get(first.asset_digest)) + len(corpus.store.get(image.asset_digest))
    per_second = len(corpus.store.get(second.asset_digest)) + len(corpus.store.get(other_image.asset_digest))
    index = VideoEvidenceIndex(corpus, max_source_bytes=max(per_first, per_second))
    index.bind(
        timeline_id="first",
        parent_record_id=first.record_id,
        fragments=(TimedMediaFragment(image.record_id, 0, 0, 0),),
    )
    index.bind(
        timeline_id="second",
        parent_record_id=second.record_id,
        fragments=(TimedMediaFragment(other_image.record_id, 0, 0, 0),),
    )
    get = corpus.get
    read_ids = []

    def track(record_id):
        read_ids.append(record_id)
        return get(record_id)

    monkeypatch.setattr(corpus, "get", track)
    with pytest.raises(MultimodalFoundationError, match="byte budget"):
        index.search("red bus", timeline_ids=("first", "second"), allowed_rights_refs=("rights:clip",))
    assert read_ids == [first.record_id, image.record_id]
