from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from skeleton.ai.runtime.learning_foundation.data import (
    ContentAddressedStore,
    DataPlaneError,
)
from skeleton.ai.runtime.learning_foundation.multimodal import (
    LearningModality,
    MultimodalCorpus,
    MultimodalFoundationError,
    SpeechChunkReceipt,
)


def _ingest(corpus: MultimodalCorpus, **overrides):
    arguments = {
        "record_id": "document",
        "modality": LearningModality.DOCUMENT,
        "media_type": "text/plain",
        "payload": b"quarterly revenue",
        "source_refs": ("source:report",),
        "rights_refs": ("rights:internal",),
        "metadata": {"filename": "report.txt"},
        "extracted_text": "quarterly revenue",
        "extractor_ref": "extractor:text-v1",
        "language": "en",
    }
    arguments.update(overrides)
    return corpus.ingest(**arguments)


def _state(corpus: MultimodalCorpus):
    return (
        dict(corpus._records),
        dict(corpus._record_digests),
        dict(corpus._text),
        dict(corpus.intake._assets),
        dict(corpus.store._objects),
        dict(corpus.store._types),
        dict(corpus._speech_tail),
        dict(corpus._speech_tail_sequences),
        dict(corpus._speech_chunks),
        dict(corpus._speech_chain_digests),
        dict(corpus._speech_record_keys),
    )


@pytest.mark.parametrize(
    "override",
    (
        {"extracted_text": "poisoned projection"},
        {"source_refs": ("source:attacker",)},
        {"rights_refs": ()},
        {"extractor_ref": None},
        {"language": ""},
        {"simulated": "false"},
    ),
)
def test_rejected_reingest_preserves_all_committed_evidence(override) -> None:
    corpus = MultimodalCorpus()
    original = _ingest(corpus)
    independent = _ingest(
        corpus,
        record_id="independent",
        payload=b"independent source",
        extracted_text="independent evidence",
    )
    before = _state(corpus)

    with pytest.raises(MultimodalFoundationError):
        _ingest(corpus, **override)

    assert _state(corpus) == before
    assert corpus.get("document") is original
    assert corpus.search("poisoned") == ()
    assert corpus.search("quarterly")[0].record_digest == original.digest
    assert corpus.search("independent")[0].record_digest == independent.digest


@pytest.mark.parametrize(
    "override",
    (
        {"rights_refs": ()},
        {"source_refs": ()},
        {"lineage_refs": ("duplicate", "duplicate")},
        {"extracted_text": "invalid extraction", "extractor_ref": None},
        {"extracted_text": None, "extractor_ref": "orphan-extractor"},
        {"language": ""},
        {"metadata": {"filename": {"nested": "mutable"}}},
        {"metadata": {"page_count": float("nan")}},
    ),
)
def test_failed_new_ingest_publishes_neither_asset_blob_nor_projection(override) -> None:
    corpus = MultimodalCorpus()
    before = _state(corpus)
    with pytest.raises(MultimodalFoundationError):
        _ingest(corpus, **override)
    assert _state(corpus) == before
    assert corpus.search("quarterly") == ()


def test_storage_failure_after_staged_put_preserves_all_authorities() -> None:
    class FailingStore(ContentAddressedStore):
        def put(self, payload, *, media_type="application/octet-stream"):
            super().put(payload, media_type=media_type)
            raise DataPlaneError("injected failure after allocation")

    corpus = MultimodalCorpus(store=FailingStore())
    before = _state(corpus)
    with pytest.raises(MultimodalFoundationError, match="storage failed"):
        _ingest(corpus)
    assert _state(corpus) == before


def test_duplicate_ingest_returns_issued_record_without_republishing() -> None:
    corpus = MultimodalCorpus()
    original = _ingest(corpus)
    before = _state(corpus)
    assert _ingest(corpus) is original
    assert _state(corpus) == before


def test_record_metadata_cannot_drift_from_input_or_returned_reference() -> None:
    corpus = MultimodalCorpus()
    metadata = {"filename": "report.txt"}
    record = _ingest(corpus, metadata=metadata)
    identity = record.digest
    metadata["filename"] = "replacement.txt"
    with pytest.raises(TypeError):
        record.metadata["filename"] = "replacement.txt"
    assert corpus.get("document").digest == identity


@pytest.mark.parametrize("reader", ("get", "search"))
@pytest.mark.parametrize("corruption", ("text", "missing_text", "source", "metadata", "orphan_text"))
def test_retrieval_rejects_corrupt_source_and_derived_projection(reader, corruption) -> None:
    corpus = MultimodalCorpus()
    record = _ingest(corpus)
    if corruption == "text":
        corpus._text[record.record_id] = "forged revenue"
    elif corruption == "missing_text":
        del corpus._text[record.record_id]
    elif corruption == "source":
        corpus.store._objects[record.asset_digest] = b"replacement source"
    elif corruption == "metadata":
        corpus.intake._assets[record.record_id].sanitized_metadata["filename"] = "forged.txt"
    else:
        corpus._text[record.record_id] = "quarterly revenue"
        corpus._records[record.record_id] = replace(record, text_projection=None)
    with pytest.raises(MultimodalFoundationError):
        if reader == "get":
            corpus.get(record.record_id)
        else:
            corpus.search("revenue")


def test_self_consistent_forged_projection_is_not_issued_evidence() -> None:
    corpus = MultimodalCorpus()
    record = _ingest(corpus)
    assert record.text_projection is not None
    forged_text = "forged quarterly revenue"
    forged_projection = replace(
        record.text_projection,
        text_digest=hashlib.sha256(forged_text.encode()).hexdigest(),
    )
    corpus._records[record.record_id] = replace(record, text_projection=forged_projection)
    corpus._text[record.record_id] = forged_text
    with pytest.raises(MultimodalFoundationError, match="record identity drift"):
        corpus.search("forged")


def test_projection_cannot_be_rebound_to_another_source_record() -> None:
    corpus = MultimodalCorpus()
    first = _ingest(corpus)
    second = _ingest(corpus, record_id="second", payload=b"another source")
    corpus._records[first.record_id] = replace(first, asset_digest=second.asset_digest)
    with pytest.raises(MultimodalFoundationError, match="record identity drift"):
        corpus.get(first.record_id)


def test_projection_instruction_authority_mutation_is_detected() -> None:
    corpus = MultimodalCorpus()
    record = _ingest(corpus)
    assert record.text_projection is not None
    object.__setattr__(record.text_projection, "instruction_trusted", True)
    with pytest.raises(MultimodalFoundationError, match="record identity drift"):
        corpus.search("quarterly")


def test_orphan_projection_fails_with_typed_error() -> None:
    corpus = MultimodalCorpus()
    corpus._text["missing"] = "orphan evidence"
    with pytest.raises(MultimodalFoundationError, match="orphan"):
        corpus.search("orphan")


def _speech(corpus: MultimodalCorpus, sequence=0, **overrides):
    arguments = {
        "stream_id": "speech",
        "sequence": sequence,
        "payload": f"chunk-{sequence}".encode(),
        "media_type": "audio/wav",
        "source_refs": ("source:microphone",),
        "rights_refs": ("rights:consent",),
        "transcript": f"transcript chunk {sequence}",
        "extractor_ref": "asr:local-v1",
    }
    arguments.update(overrides)
    return corpus.ingest_speech_chunk(**arguments)


@pytest.mark.parametrize("sequence", (False, 0.0, -1, "0"))
def test_invalid_speech_sequence_cannot_leave_a_record(sequence) -> None:
    corpus = MultimodalCorpus()
    before = _state(corpus)
    with pytest.raises(MultimodalFoundationError, match="sequence"):
        _speech(corpus, sequence)
    assert _state(corpus) == before


def test_speech_duplicate_retry_preserves_receipt_and_does_not_rewind_tail() -> None:
    corpus = MultimodalCorpus()
    first, receipt0 = _speech(corpus)
    _, receipt1 = _speech(corpus, 1)
    before = _state(corpus)
    duplicate, receipt = _speech(corpus)
    assert duplicate is first
    assert receipt is receipt0
    assert _state(corpus) == before
    third, receipt2 = _speech(corpus, 2)
    assert third.lineage_refs == (receipt1.record_digest,)
    assert receipt2.previous_chunk_digest == receipt1.chain_digest


def test_conflicting_speech_retry_does_not_poison_text_or_receipts() -> None:
    corpus = MultimodalCorpus()
    _speech(corpus)
    before = _state(corpus)
    with pytest.raises(MultimodalFoundationError, match="identity conflict"):
        _speech(corpus, transcript="poisoned speech")
    assert _state(corpus) == before
    assert corpus.search("poisoned") == ()
    assert len(corpus.search("transcript")) == 1


def test_speech_receipt_mutation_blocks_next_chunk_without_publication() -> None:
    corpus = MultimodalCorpus()
    _, receipt = _speech(corpus)
    object.__setattr__(receipt, "record_digest", "0" * 64)
    before = _state(corpus)
    with pytest.raises(MultimodalFoundationError, match="receipt identity drift"):
        _speech(corpus, 1)
    assert _state(corpus) == before


@pytest.mark.parametrize("operation", ("append", "search", "get"))
def test_earlier_speech_receipt_corruption_cannot_hide_behind_valid_tail(operation) -> None:
    corpus = MultimodalCorpus()
    _, receipt0 = _speech(corpus)
    _speech(corpus, 1)
    object.__setattr__(receipt0, "record_digest", "0" * 64)
    before = _state(corpus)
    with pytest.raises(MultimodalFoundationError, match="receipt identity drift"):
        if operation == "append":
            _speech(corpus, 2)
        elif operation == "search":
            corpus.search("transcript")
        else:
            corpus.get("speech:1")
    assert _state(corpus) == before


def test_self_consistent_forged_speech_tail_is_not_issued_evidence() -> None:
    corpus = MultimodalCorpus()
    _, receipt = _speech(corpus)
    forged_digest = "0" * 64
    payload = {
        "stream_id": receipt.stream_id,
        "sequence": receipt.sequence,
        "record_digest": forged_digest,
        "previous_chunk_digest": receipt.previous_chunk_digest,
    }
    chain = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    corpus._speech_tail["speech"] = replace(receipt, record_digest=forged_digest, chain_digest=chain)
    before = _state(corpus)
    with pytest.raises(MultimodalFoundationError, match="tail identity drift"):
        _speech(corpus, 1)
    assert _state(corpus) == before


def test_speech_receipt_constructor_rejects_unbound_chain_identity() -> None:
    with pytest.raises(MultimodalFoundationError, match="chain identity drift"):
        SpeechChunkReceipt("speech", 0, "0" * 64, None, "1" * 64)


def test_speech_sequence_type_mutation_is_detected_on_read() -> None:
    corpus = MultimodalCorpus()
    _, receipt = _speech(corpus)
    object.__setattr__(receipt, "sequence", False)
    with pytest.raises(MultimodalFoundationError, match="receipt identity drift"):
        corpus.get("speech:0")


def test_speech_chain_with_missing_source_fails_with_typed_error() -> None:
    corpus = MultimodalCorpus()
    _speech(corpus)
    _speech(corpus, 1)
    del corpus._records["speech:0"]
    with pytest.raises(MultimodalFoundationError, match="source record is missing"):
        corpus.get("speech:1")


def test_missing_speech_receipt_index_cannot_bypass_read_verification() -> None:
    corpus = MultimodalCorpus()
    _speech(corpus)
    del corpus._speech_record_keys["speech:0"]
    with pytest.raises(MultimodalFoundationError, match="receipt provenance drift"):
        corpus.get("speech:0")


def test_concurrent_identity_conflict_commits_one_consistent_projection() -> None:
    corpus = MultimodalCorpus()

    def ingest(text):
        try:
            return _ingest(corpus, extracted_text=text)
        except MultimodalFoundationError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(ingest, ("alpha evidence", "beta evidence")))
    committed = [outcome for outcome in outcomes if outcome is not None]
    assert len(committed) == 1
    assert corpus.get("document") is committed[0]
    assert len(corpus.search("alpha")) + len(corpus.search("beta")) == 1
