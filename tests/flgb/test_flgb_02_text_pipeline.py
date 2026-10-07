from __future__ import annotations

import pytest

from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig
from skeleton.ai.model_runtime.tokenization import TokenizerContractError


def test_pipeline_config_digest_is_deterministic():
    left = TextPipelineConfig(context_size=128, stride=64, max_batch_size=4, max_tokens_per_batch=512)
    right = TextPipelineConfig(context_size=128, stride=64, max_batch_size=4, max_tokens_per_batch=512)
    assert left.digest == right.digest
    assert len(left.digest) == 64


@pytest.mark.parametrize("kwargs", [
    {"normalization": "BOGUS"},
    {"context_size": 0},
    {"context_size": True},
    {"context_size": 8, "stride": 9},
    {"context_size": 8, "stride": 0},
    {"max_batch_size": 0},
    {"max_tokens_per_batch": 0},
])
def test_pipeline_config_fails_closed(kwargs):
    with pytest.raises(TokenizerContractError):
        TextPipelineConfig(**kwargs)


def test_normalization_is_provenance_visible_in_sequence_digest(native_model):
    """Byte-distinct source text must not silently collapse provenance."""
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    raw = "Cafe\u0301"
    prepared = pipeline.prepare(raw)

    raw_digest = __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()
    normalized_digest = __import__("hashlib").sha256(prepared.normalized_text.encode("utf-8")).hexdigest()
    assert prepared.normalized_text == "Caf\u00e9"
    assert prepared.raw_text_digest == raw_digest
    assert prepared.normalized_text_digest == normalized_digest
    assert prepared.raw_text_digest != prepared.normalized_text_digest
    assert prepared.sequence.source_text_digest == prepared.normalized_text_digest


def test_pipeline_digest_binds_normalization_policy(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    tokenizer = NativeTokenizer(native_model)
    nfc = TextTokenPipeline(tokenizer, TextPipelineConfig(normalization="NFC"))
    none = TextTokenPipeline(tokenizer, TextPipelineConfig(normalization="NONE"))

    assert nfc.digest != none.digest


def test_prepared_text_rejects_tampered_provenance(native_model):
    from dataclasses import replace
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError

    prepared = TextTokenPipeline(NativeTokenizer(native_model)).prepare("alpha")
    with pytest.raises(TokenizerContractError):
        replace(prepared, raw_text_digest="0" * 63)
    with pytest.raises(TokenizerContractError):
        replace(prepared, normalized_text_digest="0" * 64)


def test_stream_preserves_raw_chunk_boundary_independent_provenance(native_model):
    import hashlib
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    raw = "Cafe\u0301\r\nnext"
    one = pipeline.stream([raw])
    split = pipeline.stream(["Ca", "fe\u0301\r", "\nnext"])

    assert one.raw_text_digest == split.raw_text_digest == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert one.normalized_text_digest == split.normalized_text_digest
    assert one.sequence.digest == split.sequence.digest
    assert one.pipeline_digest == split.pipeline_digest


def test_materialized_batch_is_rectangular_and_masked():
    from skeleton.ai.model_runtime.text_pipeline import materialize_model_batch
    from skeleton.ai.model_runtime.tokenization import TokenWindow

    source = "a" * 64
    first = TokenWindow(0, 3, (1, 2, 3), source)
    second = TokenWindow(3, 4, (4,), source)
    batch = materialize_model_batch((first, second), pad_token_id=0)

    assert batch.input_ids == ((1, 2, 3), (4, 0, 0))
    assert batch.attention_mask == ((1, 1, 1), (1, 0, 0))
    assert batch.source_window_digests == (first.digest, second.digest)
    assert len(batch.digest) == 64


def test_materialized_batch_rejects_invalid_padding():
    from skeleton.ai.model_runtime.text_pipeline import materialize_model_batch
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError, TokenWindow

    with pytest.raises(TokenizerContractError):
        materialize_model_batch((TokenWindow(0, 1, (1,), "a" * 64),), pad_token_id=True)


def test_model_batches_reject_cross_pipeline_prepared_text(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig, TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError

    tokenizer = NativeTokenizer(native_model)
    first = TextTokenPipeline(tokenizer, TextPipelineConfig(context_size=2))
    second = TextTokenPipeline(tokenizer, TextPipelineConfig(context_size=3))
    prepared = first.prepare("alpha beta gamma")
    with pytest.raises(TokenizerContractError):
        second.model_batches(prepared)


def test_causal_training_batch_shifts_targets_and_masks_padding():
    from skeleton.ai.model_runtime.text_pipeline import materialize_causal_training_batch, materialize_model_batch
    from skeleton.ai.model_runtime.tokenization import TokenWindow

    source = "b" * 64
    model_batch = materialize_model_batch((
        TokenWindow(0, 4, (5, 6, 7, 8), source),
        TokenWindow(4, 6, (9, 10), source),
    ), pad_token_id=0)
    causal = materialize_causal_training_batch(model_batch)

    assert causal.input_ids == ((5, 6, 7), (9, 10, 0))
    assert causal.labels == ((6, 7, 8), (10, -100, -100))
    assert causal.loss_mask == ((1, 1, 1), (1, 0, 0))
    assert causal.source_window_digests == model_batch.source_window_digests
    assert len(causal.digest) == 64


def test_causal_training_rejects_single_token_only_batch():
    from skeleton.ai.model_runtime.text_pipeline import materialize_causal_training_batch, materialize_model_batch
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError, TokenWindow

    model_batch = materialize_model_batch((TokenWindow(0, 1, (5,), "c" * 64),), pad_token_id=0)
    with pytest.raises(TokenizerContractError, match="at least two"):
        materialize_causal_training_batch(model_batch)


def test_causal_training_pipeline_is_deterministic(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig, TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    pipeline = TextTokenPipeline(NativeTokenizer(native_model), TextPipelineConfig(context_size=4))
    prepared = pipeline.prepare("alpha beta gamma delta epsilon")
    left = pipeline.causal_training_batches(prepared)
    right = pipeline.causal_training_batches(prepared)
    assert tuple(batch.digest for batch in left) == tuple(batch.digest for batch in right)


def test_training_receipt_binds_replayable_training_payload(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig, TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    pipeline = TextTokenPipeline(NativeTokenizer(native_model), TextPipelineConfig(context_size=4))
    prepared = pipeline.prepare("alpha beta gamma delta epsilon")
    receipt = pipeline.training_receipt(prepared)

    assert receipt.pipeline_digest == pipeline.digest
    assert receipt.tokenizer_digest == pipeline.tokenizer.digest
    assert receipt.sequence_digest == prepared.sequence.digest
    assert receipt.example_count > 0
    assert receipt.supervised_token_count > 0
    assert len(receipt.digest) == 64
    pipeline.verify_training_receipt(prepared, receipt)


def test_training_receipt_rejects_tampered_payload(native_model):
    from dataclasses import replace
    from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig, TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError

    pipeline = TextTokenPipeline(NativeTokenizer(native_model), TextPipelineConfig(context_size=4))
    prepared = pipeline.prepare("alpha beta gamma delta epsilon")
    receipt = pipeline.training_receipt(prepared)
    tampered = replace(receipt, supervised_token_count=receipt.supervised_token_count + 1)

    with pytest.raises(TokenizerContractError, match="receipt mismatch"):
        pipeline.verify_training_receipt(prepared, tampered)


def test_training_receipt_fails_closed_without_trainable_examples(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig, TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError

    pipeline = TextTokenPipeline(NativeTokenizer(native_model), TextPipelineConfig(context_size=1))
    prepared = pipeline.prepare("alpha")
    with pytest.raises(TokenizerContractError, match="no trainable"):
        pipeline.training_receipt(prepared)


def test_governed_training_input_binds_dataset_lineage(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig, TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision

    pipeline = TextTokenPipeline(NativeTokenizer(native_model), TextPipelineConfig(context_size=4))
    prepared = pipeline.prepare("alpha beta gamma delta epsilon")
    rights_digest = "1" * 64
    revision = DatasetRevision("dataset", 0, prepared.raw_text_digest, rights_digest, pipeline.digest)
    governed = pipeline.governed_training_input(prepared, revision)

    assert governed.dataset_revision_digest == revision.digest
    assert governed.transform_digest == pipeline.digest
    assert governed.rights_digest == rights_digest
    assert governed.receipt_digest == pipeline.training_receipt(prepared).digest
    assert len(governed.digest) == 64


def test_governed_training_input_rejects_wrong_content(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta")
    revision = DatasetRevision("dataset", 0, "0" * 64, "1" * 64, pipeline.digest)
    with pytest.raises(TokenizerContractError, match="content"):
        pipeline.governed_training_input(prepared, revision)


def test_governed_training_input_rejects_wrong_transform(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta")
    revision = DatasetRevision("dataset", 0, prepared.raw_text_digest, "1" * 64, "2" * 64)
    with pytest.raises(TokenizerContractError, match="transform"):
        pipeline.governed_training_input(prepared, revision)


def test_training_manifest_binds_pipeline_and_dataset(native_model):
    from skeleton.ai.model_runtime.flgb_model_runtime import digest_json
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta gamma")
    revision = DatasetRevision("dataset", 0, prepared.raw_text_digest, "1" * 64, pipeline.digest)
    governed = pipeline.governed_training_input(prepared, revision)
    manifest = pipeline.training_manifest(
        prepared, revision, run_id="run-1", base_model_digest="2" * 64,
        code_digest="3" * 64, seed_manifest_digest="4" * 64, max_steps=10,
    )

    assert manifest.dataset_revision_digests == (revision.digest,)
    assert manifest.config_digest == digest_json({"pipeline_digest": pipeline.digest, "training_input_digest": governed.digest})
    assert manifest.output_kind == "candidate-only"


def _training_lineage_fixture(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta gamma delta")
    revision = DatasetRevision("dataset", 0, prepared.raw_text_digest, "1" * 64, pipeline.digest)
    manifest = pipeline.training_manifest(
        prepared, revision, run_id="run-1", base_model_digest="2" * 64,
        code_digest="3" * 64, seed_manifest_digest="4" * 64, max_steps=10,
    )
    return pipeline, manifest


def test_training_checkpoint_and_candidate_preserve_lineage(native_model):
    pipeline, manifest = _training_lineage_fixture(native_model)
    checkpoint = pipeline.initial_training_checkpoint(
        manifest, weights_digest="5" * 64, optimizer_digest="6" * 64, rng_digest="7" * 64,
    )
    candidate = pipeline.candidate_from_checkpoint(
        manifest, checkpoint, candidate_id="candidate-1", base_model_digest="2" * 64,
    )

    assert checkpoint.run_manifest_digest == manifest.digest
    assert candidate.weights_digest == checkpoint.weights_digest
    assert candidate.training_lineage_digest == checkpoint.digest
    assert candidate.status == "candidate"
    assert candidate.production_authorized() is False


def test_candidate_rejects_checkpoint_from_other_manifest(native_model):
    from dataclasses import replace
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError

    pipeline, manifest = _training_lineage_fixture(native_model)
    checkpoint = pipeline.initial_training_checkpoint(
        manifest, weights_digest="5" * 64, optimizer_digest="6" * 64, rng_digest="7" * 64,
    )
    foreign = replace(checkpoint, run_manifest_digest="8" * 64)
    with pytest.raises(TokenizerContractError, match="does not belong"):
        pipeline.candidate_from_checkpoint(
            manifest, foreign, candidate_id="candidate-1", base_model_digest="2" * 64,
        )


def test_candidate_rejects_base_model_mismatch(native_model):
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError

    pipeline, manifest = _training_lineage_fixture(native_model)
    checkpoint = pipeline.initial_training_checkpoint(
        manifest, weights_digest="5" * 64, optimizer_digest="6" * 64, rng_digest="7" * 64,
    )
    with pytest.raises(TokenizerContractError, match="base model"):
        pipeline.candidate_from_checkpoint(
            manifest, checkpoint, candidate_id="candidate-1", base_model_digest="9" * 64,
        )


def test_checkpoint_advancement_forms_hash_chain(native_model):
    pipeline, manifest = _training_lineage_fixture(native_model)
    genesis = pipeline.initial_training_checkpoint(
        manifest, weights_digest="5" * 64, optimizer_digest="6" * 64, rng_digest="7" * 64,
    )
    second = pipeline.advance_training_checkpoint(
        manifest, genesis, weights_digest="8" * 64, optimizer_digest="9" * 64, rng_digest="a" * 64,
    )

    assert second.sequence == 1
    assert second.prior_checkpoint_digest == genesis.digest
    assert second.run_manifest_digest == manifest.digest
    assert second.digest != genesis.digest


def _candidate_fixture(native_model):
    pipeline, manifest = _training_lineage_fixture(native_model)
    checkpoint = pipeline.initial_training_checkpoint(
        manifest, weights_digest="5" * 64, optimizer_digest="6" * 64, rng_digest="7" * 64,
    )
    return pipeline, pipeline.candidate_from_checkpoint(
        manifest, checkpoint, candidate_id="candidate-1", base_model_digest="2" * 64,
    )


def test_mirror_evaluation_and_promotion_evidence_are_independently_verified(native_model):
    pipeline, candidate = _candidate_fixture(native_model)
    evaluation = pipeline.mirror_evaluation(
        candidate, evaluation_id="eval-1", champion_digest="8" * 64,
        candidate_score_ppm=700000, champion_score_ppm=600000,
        risk_gate_passed=True, independent_verifier="mirror-verifier",
        evidence_digest="9" * 64,
    )
    evidence = pipeline.promotion_evidence(
        candidate, evaluation, exact_head_commit="a" * 64, rights_digest="b" * 64,
        contamination_scan_digest="c" * 64, rollback_digest="d" * 64,
        independent_verifier="promotion-verifier", rights_passed=True,
        contamination_clear=True, rollback_ready=True,
    )

    assert evaluation.candidate_wins is True
    assert evidence.candidate_digest == candidate.digest
    assert evidence.evaluation_passed is True
    assert evidence.qualified is True
    assert candidate.production_authorized() is False


def test_promotion_evidence_rejects_same_verifier(native_model):
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError
    pipeline, candidate = _candidate_fixture(native_model)
    evaluation = pipeline.mirror_evaluation(
        candidate, evaluation_id="eval-1", champion_digest="8" * 64,
        candidate_score_ppm=700000, champion_score_ppm=600000,
        risk_gate_passed=True, independent_verifier="verifier", evidence_digest="9" * 64,
    )
    with pytest.raises(TokenizerContractError, match="verifier separation"):
        pipeline.promotion_evidence(
            candidate, evaluation, exact_head_commit="a" * 64, rights_digest="b" * 64,
            contamination_scan_digest="c" * 64, rollback_digest="d" * 64,
            independent_verifier="verifier", rights_passed=True,
            contamination_clear=True, rollback_ready=True,
        )


def test_failed_mirror_risk_gate_cannot_qualify_promotion(native_model):
    pipeline, candidate = _candidate_fixture(native_model)
    evaluation = pipeline.mirror_evaluation(
        candidate, evaluation_id="eval-1", champion_digest="8" * 64,
        candidate_score_ppm=900000, champion_score_ppm=100000,
        risk_gate_passed=False, independent_verifier="mirror-verifier", evidence_digest="9" * 64,
    )
    evidence = pipeline.promotion_evidence(
        candidate, evaluation, exact_head_commit="a" * 64, rights_digest="b" * 64,
        contamination_scan_digest="c" * 64, rollback_digest="d" * 64,
        independent_verifier="promotion-verifier", rights_passed=True,
        contamination_clear=True, rollback_ready=True,
    )
    assert evaluation.candidate_wins is False
    assert evidence.evaluation_passed is False
    assert evidence.qualified is False


def _candidate_fixture(native_model):
    pipeline, manifest = _training_lineage_fixture(native_model)
    checkpoint = pipeline.initial_training_checkpoint(
        manifest, weights_digest="5" * 64, optimizer_digest="6" * 64, rng_digest="7" * 64,
    )
    candidate = pipeline.candidate_from_checkpoint(
        manifest, checkpoint, candidate_id="candidate-1", base_model_digest="2" * 64,
    )
    return pipeline, candidate


def test_mirror_evaluation_and_promotion_evidence_preserve_separation(native_model):
    pipeline, candidate = _candidate_fixture(native_model)
    evaluation = pipeline.mirror_evaluation(
        candidate, evaluation_id="eval-1", champion_digest="8" * 64,
        candidate_score_ppm=700000, champion_score_ppm=600000, risk_gate_passed=True,
        independent_verifier="mirror-verifier", evidence_digest="9" * 64,
    )
    evidence = pipeline.promotion_evidence(
        candidate, evaluation, exact_head_commit="a" * 64, rights_digest="b" * 64,
        contamination_scan_digest="c" * 64, rollback_digest="d" * 64,
        independent_verifier="promotion-verifier", rights_passed=True,
        contamination_clear=True, rollback_ready=True,
    )

    assert evaluation.candidate_wins is True
    assert evidence.candidate_digest == candidate.digest
    assert evidence.evaluation_passed is True
    assert evidence.qualified is True
    assert candidate.production_authorized() is False


def test_promotion_evidence_rejects_same_verifier(native_model):
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError

    pipeline, candidate = _candidate_fixture(native_model)
    evaluation = pipeline.mirror_evaluation(
        candidate, evaluation_id="eval-1", champion_digest="8" * 64,
        candidate_score_ppm=700000, champion_score_ppm=600000, risk_gate_passed=True,
        independent_verifier="same-verifier", evidence_digest="9" * 64,
    )
    with pytest.raises(TokenizerContractError, match="verifier separation"):
        pipeline.promotion_evidence(
            candidate, evaluation, exact_head_commit="a" * 64, rights_digest="b" * 64,
            contamination_scan_digest="c" * 64, rollback_digest="d" * 64,
            independent_verifier="same-verifier", rights_passed=True,
            contamination_clear=True, rollback_ready=True,
        )


def test_promotion_evidence_rejects_foreign_candidate(native_model):
    from dataclasses import replace
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError

    pipeline, candidate = _candidate_fixture(native_model)
    evaluation = pipeline.mirror_evaluation(
        candidate, evaluation_id="eval-1", champion_digest="8" * 64,
        candidate_score_ppm=700000, champion_score_ppm=600000, risk_gate_passed=True,
        independent_verifier="mirror-verifier", evidence_digest="9" * 64,
    )
    foreign = replace(candidate, candidate_id="candidate-2")
    with pytest.raises(TokenizerContractError, match="does not belong"):
        pipeline.promotion_evidence(
            foreign, evaluation, exact_head_commit="a" * 64, rights_digest="b" * 64,
            contamination_scan_digest="c" * 64, rollback_digest="d" * 64,
            independent_verifier="promotion-verifier", rights_passed=True,
            contamination_clear=True, rollback_ready=True,
        )


def test_failed_risk_gate_cannot_qualify_promotion(native_model):
    pipeline, candidate = _candidate_fixture(native_model)
    evaluation = pipeline.mirror_evaluation(
        candidate, evaluation_id="eval-1", champion_digest="8" * 64,
        candidate_score_ppm=900000, champion_score_ppm=100000, risk_gate_passed=False,
        independent_verifier="mirror-verifier", evidence_digest="9" * 64,
    )
    evidence = pipeline.promotion_evidence(
        candidate, evaluation, exact_head_commit="a" * 64, rights_digest="b" * 64,
        contamination_scan_digest="c" * 64, rollback_digest="d" * 64,
        independent_verifier="promotion-verifier", rights_passed=True,
        contamination_clear=True, rollback_ready=True,
    )
    assert evaluation.candidate_wins is False
    assert evidence.evaluation_passed is False
    assert evidence.qualified is False


def _qualified_promotion_fixture(native_model):
    pipeline, candidate = _candidate_fixture(native_model)
    evaluation = pipeline.mirror_evaluation(
        candidate, evaluation_id="eval-1", champion_digest="8" * 64,
        candidate_score_ppm=700000, champion_score_ppm=600000,
        risk_gate_passed=True, independent_verifier="mirror-verifier", evidence_digest="9" * 64,
    )
    evidence = pipeline.promotion_evidence(
        candidate, evaluation, exact_head_commit="a" * 64, rights_digest="b" * 64,
        contamination_scan_digest="c" * 64, rollback_digest="d" * 64,
        independent_verifier="promotion-verifier", rights_passed=True,
        contamination_clear=True, rollback_ready=True,
    )
    return pipeline, candidate, evidence


def test_qualified_evidence_creates_non_authorizing_handoff(native_model):
    pipeline, candidate, evidence = _qualified_promotion_fixture(native_model)
    request = pipeline.promotion_authorization_request(candidate, evidence, requester="release-authority")
    assert request.candidate_digest == candidate.digest
    assert request.promotion_evidence_digest == evidence.digest
    assert request.exact_head_commit == evidence.exact_head_commit
    assert len(request.digest) == 64
    assert candidate.production_authorized() is False


def test_unqualified_evidence_cannot_request_authorization(native_model):
    from dataclasses import replace
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError
    pipeline, candidate, evidence = _qualified_promotion_fixture(native_model)
    failed = replace(evidence, rollback_ready=False)
    with pytest.raises(TokenizerContractError, match="unqualified"):
        pipeline.promotion_authorization_request(candidate, failed, requester="release-authority")


def test_foreign_candidate_evidence_cannot_request_authorization(native_model):
    from dataclasses import replace
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError
    pipeline, candidate, evidence = _qualified_promotion_fixture(native_model)
    foreign = replace(evidence, candidate_digest="e" * 64)
    with pytest.raises(TokenizerContractError, match="does not belong"):
        pipeline.promotion_authorization_request(candidate, foreign, requester="release-authority")


def test_prepared_corpus_preserves_document_boundaries(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig, TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    pipeline = TextTokenPipeline(NativeTokenizer(native_model), TextPipelineConfig(context_size=8))
    corpus = pipeline.prepare_corpus((("doc-a", "alpha beta"), ("doc-b", "gamma delta")))
    receipts = pipeline.corpus_training_receipts(corpus)

    assert corpus.document_ids == ("doc-a", "doc-b")
    assert len(corpus.documents) == 2
    assert len(receipts) == 2
    assert receipts[0].sequence_digest == corpus.documents[0].sequence.digest
    assert receipts[1].sequence_digest == corpus.documents[1].sequence.digest
    assert corpus.documents[0].raw_text_digest != corpus.documents[1].raw_text_digest
    assert len(corpus.digest) == 64


def test_prepared_corpus_rejects_duplicate_document_ids(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    with pytest.raises(TokenizerContractError, match="duplicate document id"):
        pipeline.prepare_corpus((("doc", "alpha beta"), ("doc", "gamma delta")))


def test_prepared_corpus_digest_is_order_sensitive(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    left = pipeline.prepare_corpus((("a", "alpha beta"), ("b", "gamma delta")))
    right = pipeline.prepare_corpus((("b", "gamma delta"), ("a", "alpha beta")))
    assert left.digest != right.digest


def test_pipeline_replay_checkpoint_verifies_text_and_corpus(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta gamma")
    corpus = pipeline.prepare_corpus((("a", "alpha beta"), ("b", "gamma delta")))
    text_checkpoint = pipeline.replay_checkpoint(prepared)
    corpus_checkpoint = pipeline.replay_checkpoint(corpus)

    assert text_checkpoint.payload_kind == "prepared-text"
    assert corpus_checkpoint.payload_kind == "prepared-corpus"
    pipeline.verify_replay_checkpoint(prepared, text_checkpoint)
    pipeline.verify_replay_checkpoint(corpus, corpus_checkpoint)


def test_pipeline_replay_checkpoint_rejects_different_payload(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    checkpoint = pipeline.replay_checkpoint(pipeline.prepare("alpha beta"))
    with pytest.raises(TokenizerContractError, match="checkpoint mismatch"):
        pipeline.verify_replay_checkpoint(pipeline.prepare("gamma delta"), checkpoint)
