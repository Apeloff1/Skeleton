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
    assert batch.position_ids == ((0, 1, 2), (0, 0, 0))
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
        second.model_batches(prepared, pad_token_id=native_model.unk)


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
    left = pipeline.causal_training_batches(prepared, pad_token_id=native_model.unk)
    right = pipeline.causal_training_batches(prepared, pad_token_id=native_model.unk)
    assert tuple(batch.digest for batch in left) == tuple(batch.digest for batch in right)


def test_training_receipt_binds_replayable_training_payload(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig, TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    pipeline = TextTokenPipeline(NativeTokenizer(native_model), TextPipelineConfig(context_size=4))
    prepared = pipeline.prepare("alpha beta gamma delta epsilon")
    receipt = pipeline.training_receipt(prepared, pad_token_id=native_model.unk)

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
    receipt = pipeline.training_receipt(prepared, pad_token_id=native_model.unk)
    tampered = replace(receipt, supervised_token_count=receipt.supervised_token_count + 1)

    with pytest.raises(TokenizerContractError, match="receipt mismatch"):
        pipeline.verify_training_receipt(prepared, tampered)


def test_training_receipt_fails_closed_without_trainable_examples(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig, TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError

    pipeline = TextTokenPipeline(NativeTokenizer(native_model), TextPipelineConfig(context_size=1))
    prepared = pipeline.prepare("alpha")
    with pytest.raises(TokenizerContractError, match="no trainable"):
        pipeline.training_receipt(prepared, pad_token_id=native_model.unk)


def test_governed_training_input_binds_dataset_lineage(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig, TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision, DatasetRights

    pipeline = TextTokenPipeline(NativeTokenizer(native_model), TextPipelineConfig(context_size=4))
    prepared = pipeline.prepare("alpha beta gamma delta epsilon")
    rights = DatasetRights("dataset", "source", "allowed", "license", ("training",), "9" * 64)
    rights_digest = rights.digest
    revision = DatasetRevision("dataset", 0, prepared.raw_text_digest, rights_digest, pipeline.digest)
    governed = pipeline.governed_training_input(prepared, revision, rights, pad_token_id=native_model.unk)

    assert governed.dataset_revision_digest == revision.digest
    assert governed.transform_digest == pipeline.digest
    assert governed.rights_digest == rights_digest
    assert governed.authorized_scope == "training"
    assert governed.receipt_digest == pipeline.training_receipt(prepared, pad_token_id=native_model.unk).digest
    assert len(governed.digest) == 64


def test_governed_training_input_rejects_wrong_content(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision, DatasetRights

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta")
    rights = DatasetRights("dataset", "source", "allowed", "license", ("training",), "9" * 64)
    revision = DatasetRevision("dataset", 0, "0" * 64, rights.digest, pipeline.digest)
    with pytest.raises(TokenizerContractError, match="content"):
        pipeline.governed_training_input(prepared, revision, rights, pad_token_id=native_model.unk)


def test_governed_training_input_rejects_wrong_transform(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision, DatasetRights

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta")
    rights = DatasetRights("dataset", "source", "allowed", "license", ("training",), "9" * 64)
    revision = DatasetRevision("dataset", 0, prepared.raw_text_digest, rights.digest, "2" * 64)
    with pytest.raises(TokenizerContractError, match="transform"):
        pipeline.governed_training_input(prepared, revision, rights, pad_token_id=native_model.unk)


def test_training_manifest_binds_pipeline_and_dataset(native_model):
    from skeleton.ai.model_runtime.flgb_model_runtime import digest_json
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision, DatasetRights

    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta gamma")
    rights = DatasetRights("dataset", "source", "allowed", "license", ("training",), "9" * 64)
    revision = DatasetRevision("dataset", 0, prepared.raw_text_digest, rights.digest, pipeline.digest)
    governed = pipeline.governed_training_input(prepared, revision, rights, pad_token_id=native_model.unk)
    manifest = pipeline.training_manifest(
        prepared, revision, rights, run_id="run-1", base_model_digest="2" * 64,
        code_digest="3" * 64, seed_manifest_digest="4" * 64, max_steps=10, pad_token_id=native_model.unk,
    )

    assert manifest.dataset_revision_digests == (revision.digest,)
    assert manifest.config_digest == digest_json({"pipeline_digest": pipeline.digest, "training_input_digest": governed.digest})
    assert manifest.output_kind == "candidate-only"


def _training_lineage_fixture(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision, DatasetRights
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta gamma delta")
    rights = DatasetRights("dataset", "source", "allowed", "license", ("training",), "9" * 64)
    revision = DatasetRevision("dataset", 0, prepared.raw_text_digest, rights.digest, pipeline.digest)
    manifest = pipeline.training_manifest(
        prepared, revision, rights, run_id="run-1", base_model_digest="2" * 64,
        code_digest="3" * 64, seed_manifest_digest="4" * 64, max_steps=10, pad_token_id=native_model.unk,
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


def test_causal_pipeline_skips_untrainable_windows_without_exception_matching(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig, TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer

    pipeline = TextTokenPipeline(
        NativeTokenizer(native_model),
        TextPipelineConfig(context_size=1, max_batch_size=8),
    )
    prepared = pipeline.prepare("alpha beta gamma")
    assert pipeline.causal_training_batches(prepared, pad_token_id=native_model.unk) == ()


def test_governed_training_rejects_rights_without_training_scope(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision, DatasetRights
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta gamma")
    rights = DatasetRights("dataset", "source", "allowed", "license", ("evaluation",), "9" * 64)
    revision = DatasetRevision("dataset", 0, prepared.raw_text_digest, rights.digest, pipeline.digest)
    with pytest.raises(TokenizerContractError, match="rights do not permit"):
        pipeline.governed_training_input(prepared, revision, rights, pad_token_id=native_model.unk)


def test_governed_training_rejects_mismatched_rights_identity(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision, DatasetRights
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta gamma")
    rights = DatasetRights("other", "source", "allowed", "license", ("training",), "9" * 64)
    revision = DatasetRevision("dataset", 0, prepared.raw_text_digest, rights.digest, pipeline.digest)
    with pytest.raises(TokenizerContractError, match="rights identity mismatch"):
        pipeline.governed_training_input(prepared, revision, rights, pad_token_id=native_model.unk)


def test_governed_training_scope_changes_durable_identity(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    from skeleton.ai.training.flgb_training_runtime import DatasetRevision, DatasetRights
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta gamma")
    rights = DatasetRights("dataset", "source", "allowed", "license", ("training", "continued-training"), "9" * 64)
    revision = DatasetRevision("dataset", 0, prepared.raw_text_digest, rights.digest, pipeline.digest)
    training = pipeline.governed_training_input(prepared, revision, rights, scope="training", pad_token_id=native_model.unk)
    continued = pipeline.governed_training_input(prepared, revision, rights, scope="continued-training", pad_token_id=native_model.unk)
    assert training.authorized_scope == "training"
    assert continued.authorized_scope == "continued-training"
    assert training.digest != continued.digest


def test_model_batch_rejects_position_ids_in_padding():
    from dataclasses import replace
    from skeleton.ai.model_runtime.text_pipeline import materialize_model_batch
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError, TokenWindow
    batch = materialize_model_batch((
        TokenWindow(0, 2, (1, 2), "a" * 64),
        TokenWindow(2, 3, (3,), "a" * 64),
    ), pad_token_id=0)
    with pytest.raises(TokenizerContractError, match="position ids"):
        replace(batch, position_ids=((0, 1), (0, 1)))


def test_model_batches_require_declared_or_explicit_padding(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    prepared = pipeline.prepare("alpha beta gamma")
    with pytest.raises(TokenizerContractError, match="does not declare pad token"):
        pipeline.model_batches(prepared)
    batches = pipeline.model_batches(prepared, pad_token_id=native_model.unk)
    assert batches


def test_model_input_batch_canonical_serialization_round_trip():
    from skeleton.ai.model_runtime.text_pipeline import deserialize_model_input_batch, materialize_model_batch, serialize_model_input_batch
    from skeleton.ai.model_runtime.tokenization import TokenWindow
    batch = materialize_model_batch((
        TokenWindow(0, 3, (1, 2, 3), "a" * 64),
        TokenWindow(3, 4, (4,), "a" * 64),
    ), pad_token_id=0)
    payload = serialize_model_input_batch(batch)
    restored = deserialize_model_input_batch(payload)
    assert restored == batch
    assert serialize_model_input_batch(restored) == payload


def test_model_input_batch_serialization_rejects_tampering():
    import json
    from skeleton.ai.model_runtime.text_pipeline import deserialize_model_input_batch, materialize_model_batch, serialize_model_input_batch
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError, TokenWindow
    batch = materialize_model_batch((TokenWindow(0, 2, (1, 2), "a" * 64),), pad_token_id=0)
    value = json.loads(serialize_model_input_batch(batch))
    value["input_ids"][0][0] = 9
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(TokenizerContractError, match="digest mismatch"):
        deserialize_model_input_batch(payload)


def test_causal_training_batch_canonical_serialization_round_trip():
    from skeleton.ai.model_runtime.text_pipeline import deserialize_causal_training_batch, materialize_causal_training_batch, materialize_model_batch, serialize_causal_training_batch
    from skeleton.ai.model_runtime.tokenization import TokenWindow
    model = materialize_model_batch((TokenWindow(0, 3, (1, 2, 3), "b" * 64),), pad_token_id=0)
    batch = materialize_causal_training_batch(model)
    payload = serialize_causal_training_batch(batch)
    restored = deserialize_causal_training_batch(payload)
    assert restored == batch
    assert serialize_causal_training_batch(restored) == payload


def test_native_tokenizer_rejects_non_integer_native_ids(native_model, monkeypatch):
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    tokenizer = NativeTokenizer(native_model)
    monkeypatch.setattr(native_model, "_ids", lambda text: [True])
    with pytest.raises(TokenizerContractError, match="non-integer"):
        tokenizer.encode_ids("alpha")


def test_native_tokenizer_wraps_native_encode_failure(native_model, monkeypatch):
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    tokenizer = NativeTokenizer(native_model)
    def fail(text):
        raise RuntimeError("backend exploded")
    monkeypatch.setattr(native_model, "_ids", fail)
    with pytest.raises(TokenizerContractError, match="encode failed"):
        tokenizer.encode_ids("alpha")


def test_corpus_training_receipt_binds_ordered_document_boundaries(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    corpus = pipeline.prepare_corpus((
        ("doc-a", "alpha beta gamma"),
        ("doc-b", "delta epsilon zeta"),
    ))
    receipt = pipeline.corpus_training_receipt(corpus, pad_token_id=native_model.unk)
    per_document = pipeline.corpus_training_receipts(corpus, pad_token_id=native_model.unk)
    assert receipt.document_ids == ("doc-a", "doc-b")
    assert receipt.document_receipt_digests == tuple(item.digest for item in per_document)
    assert receipt.example_count == sum(item.example_count for item in per_document)
    assert receipt.supervised_token_count == sum(item.supervised_token_count for item in per_document)
    assert pipeline.verify_corpus_training_receipt(corpus, receipt, pad_token_id=native_model.unk)


def test_corpus_training_receipt_is_order_sensitive(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    left = pipeline.prepare_corpus((("a", "alpha beta"), ("b", "gamma delta")))
    right = pipeline.prepare_corpus((("b", "gamma delta"), ("a", "alpha beta")))
    left_receipt = pipeline.corpus_training_receipt(left, pad_token_id=native_model.unk)
    right_receipt = pipeline.corpus_training_receipt(right, pad_token_id=native_model.unk)
    assert left_receipt.digest != right_receipt.digest


def test_corpus_training_receipt_rejects_foreign_corpus(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextPipelineConfig, TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    tokenizer = NativeTokenizer(native_model)
    first = TextTokenPipeline(tokenizer, TextPipelineConfig(context_size=2))
    second = TextTokenPipeline(tokenizer, TextPipelineConfig(context_size=3))
    corpus = first.prepare_corpus((("a", "alpha beta gamma"),))
    receipt = first.corpus_training_receipt(corpus, pad_token_id=native_model.unk)
    with pytest.raises(TokenizerContractError):
        second.verify_corpus_training_receipt(corpus, receipt, pad_token_id=native_model.unk)


def test_prompt_prefix_mask_keeps_context_but_removes_prompt_loss():
    from skeleton.ai.model_runtime.text_pipeline import mask_causal_prefix, materialize_causal_training_batch, materialize_model_batch
    from skeleton.ai.model_runtime.tokenization import TokenWindow
    model = materialize_model_batch((TokenWindow(0, 5, (10, 11, 12, 13, 14), "c" * 64),), pad_token_id=0)
    causal = materialize_causal_training_batch(model)
    masked = mask_causal_prefix(causal, (3,))
    assert masked.input_ids == causal.input_ids
    assert masked.loss_mask == ((0, 0, 1, 1),)
    assert masked.labels == ((-100, -100, 13, 14),)
    assert masked.digest != causal.digest


def test_prompt_prefix_mask_rejects_all_loss_removed():
    from skeleton.ai.model_runtime.text_pipeline import mask_causal_prefix, materialize_causal_training_batch, materialize_model_batch
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError, TokenWindow
    model = materialize_model_batch((TokenWindow(0, 3, (10, 11, 12), "d" * 64),), pad_token_id=0)
    causal = materialize_causal_training_batch(model)
    with pytest.raises(TokenizerContractError, match="removed all supervised"):
        mask_causal_prefix(causal, (3,))


@pytest.mark.parametrize("prefix_lengths", [(), (1, 2), (-1,), (True,)])
def test_prompt_prefix_mask_rejects_invalid_policy(prefix_lengths):
    from skeleton.ai.model_runtime.text_pipeline import mask_causal_prefix, materialize_causal_training_batch, materialize_model_batch
    from skeleton.ai.model_runtime.tokenization import TokenizerContractError, TokenWindow
    model = materialize_model_batch((TokenWindow(0, 3, (10, 11, 12), "e" * 64),), pad_token_id=0)
    causal = materialize_causal_training_batch(model)
    with pytest.raises(TokenizerContractError):
        mask_causal_prefix(causal, prefix_lengths)


def test_supervised_example_binds_prompt_response_boundary(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    example = pipeline.prepare_supervised_example("example-1", "alpha beta ", "gamma delta")
    assert example.prompt_token_count > 0
    assert example.prompt_token_count < len(example.prepared.sequence.token_ids)
    batches = pipeline.supervised_training_batches(example, pad_token_id=native_model.unk)
    assert batches
    assert sum(sum(row) for batch in batches for row in batch.loss_mask) > 0
    assert example.digest == pipeline.prepare_supervised_example("example-1", "alpha beta ", "gamma delta").digest


def test_supervised_example_identity_changes_with_response(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    left = pipeline.prepare_supervised_example("example-1", "alpha beta ", "gamma")
    right = pipeline.prepare_supervised_example("example-1", "alpha beta ", "delta")
    assert left.digest != right.digest
    assert left.response_digest != right.response_digest


def test_supervised_example_requires_response_tokens(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    with pytest.raises(TokenizerContractError):
        pipeline.prepare_supervised_example("example-1", "alpha", "")


def test_temporal_training_signal_derives_year_age_buckets(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    assert pipeline.temporal_signal(source_year=2026, observed_year=2026, knowledge_cutoff_year=2026).age_bucket == "current"
    assert pipeline.temporal_signal(source_year=2024, observed_year=2025, knowledge_cutoff_year=2026).age_bucket == "recent"
    assert pipeline.temporal_signal(source_year=2021, observed_year=2025, knowledge_cutoff_year=2026).age_bucket == "medium"
    assert pipeline.temporal_signal(source_year=2018, observed_year=2024, knowledge_cutoff_year=2026).age_bucket == "historical"
    assert pipeline.temporal_signal(source_year=2000, observed_year=2020, knowledge_cutoff_year=2026).age_bucket == "archive"


@pytest.mark.parametrize("kwargs", [
    {"source_year": 2027, "observed_year": 2026, "knowledge_cutoff_year": 2026},
    {"source_year": 2025, "observed_year": 2027, "knowledge_cutoff_year": 2026},
    {"source_year": 2025, "observed_year": 2025, "knowledge_cutoff_year": 2026, "valid_from_year": 2027},
    {"source_year": 2020, "observed_year": 2025, "knowledge_cutoff_year": 2026, "valid_from_year": 2024, "valid_to_year": 2023},
])
def test_temporal_training_signal_rejects_chronology_leakage(native_model, kwargs):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    with pytest.raises(TokenizerContractError):
        pipeline.temporal_signal(**kwargs)


def test_supervised_example_identity_binds_temporal_signal(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    old = pipeline.temporal_signal(source_year=2020, observed_year=2020, knowledge_cutoff_year=2026)
    new = pipeline.temporal_signal(source_year=2026, observed_year=2026, knowledge_cutoff_year=2026)
    left = pipeline.prepare_supervised_example("temporal-1", "alpha beta ", "gamma delta", temporal_signal=old)
    right = pipeline.prepare_supervised_example("temporal-1", "alpha beta ", "gamma delta", temporal_signal=new)
    assert left.prepared.sequence.digest == right.prepared.sequence.digest
    assert left.temporal_signal_digest == old.digest
    assert right.temporal_signal_digest == new.digest
    assert left.digest != right.digest


def test_temporal_weight_ppm_uses_deterministic_year_bands(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline, temporal_weight_ppm
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    cases = ((2026, 1_000_000), (2025, 850_000), (2022, 650_000), (2018, 400_000), (2000, 200_000))
    for source_year, expected in cases:
        signal = pipeline.temporal_signal(source_year=source_year, observed_year=source_year, knowledge_cutoff_year=2026)
        assert temporal_weight_ppm(signal) == expected


def test_temporal_supersession_binds_order_and_cutoff(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    old = pipeline.temporal_signal(source_year=2020, observed_year=2020, knowledge_cutoff_year=2026)
    new = pipeline.temporal_signal(source_year=2026, observed_year=2026, knowledge_cutoff_year=2026)
    relation = pipeline.temporal_supersession(old, new, supersedes=True)
    assert relation.relation == "supersedes"
    assert relation.year_distance == 6
    assert relation.older_signal_digest == old.digest
    assert relation.newer_signal_digest == new.digest


def test_temporal_supersession_rejects_reverse_chronology(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    old = pipeline.temporal_signal(source_year=2020, observed_year=2020, knowledge_cutoff_year=2026)
    new = pipeline.temporal_signal(source_year=2026, observed_year=2026, knowledge_cutoff_year=2026)
    with pytest.raises(TokenizerContractError, match="runs backward"):
        pipeline.temporal_supersession(new, old, supersedes=True)


def test_temporal_supersession_rejects_mixed_cutoffs(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    old = pipeline.temporal_signal(source_year=2020, observed_year=2020, knowledge_cutoff_year=2025)
    new = pipeline.temporal_signal(source_year=2025, observed_year=2025, knowledge_cutoff_year=2026)
    with pytest.raises(TokenizerContractError, match="different knowledge cutoffs"):
        pipeline.temporal_supersession(old, new, supersedes=True)


def test_decade_signal_preserves_exact_year_anchor(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    year = pipeline.temporal_signal(source_year=1987, observed_year=1994, knowledge_cutoff_year=2026)
    decade = pipeline.decade_signal(year)
    assert decade.source_decade == 1980
    assert decade.observed_decade == 1990
    assert decade.cutoff_decade == 2020
    assert decade.source_year == 1987
    assert decade.cutoff_year == 2026
    assert decade.distance_decades == 4
    assert decade.cohort == "long-history"


def test_decade_weight_ppm_uses_deterministic_cohorts(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline, decade_weight_ppm
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    cases = ((2026, 1_000_000), (2019, 800_000), (2001, 600_000), (1980, 350_000), (1900, 150_000))
    for source_year, expected in cases:
        year = pipeline.temporal_signal(source_year=source_year, observed_year=source_year, knowledge_cutoff_year=2026)
        assert decade_weight_ppm(pipeline.decade_signal(year)) == expected


def test_decade_signal_digest_distinguishes_exact_years_within_same_decade(native_model):
    from skeleton.ai.model_runtime.text_pipeline import TextTokenPipeline
    from skeleton.ai.model_runtime.tokenization import NativeTokenizer
    pipeline = TextTokenPipeline(NativeTokenizer(native_model))
    early = pipeline.decade_signal(pipeline.temporal_signal(source_year=1981, observed_year=1981, knowledge_cutoff_year=2026))
    late = pipeline.decade_signal(pipeline.temporal_signal(source_year=1989, observed_year=1989, knowledge_cutoff_year=2026))
    assert early.source_decade == late.source_decade == 1980
    assert early.digest != late.digest
