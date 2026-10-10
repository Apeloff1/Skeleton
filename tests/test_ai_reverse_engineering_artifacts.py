from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering import (
    EvidenceChain,
    QuantizationPair,
    TensorRecord,
    analyze_quantization,
    build_artifact_manifest,
    infer_tensor_topology,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def tensors():
    receipt = d("authorized-artifact")
    return (
        TensorRecord("embed.weight", (100, 16), "float16", receipt),
        TensorRecord("layers.0.attn.q.weight", (16, 16), "float16", receipt),
        TensorRecord("layers.0.attn.k.weight", (16, 16), "float16", receipt),
        TensorRecord("layers.1.attn.q.weight", (16, 16), "float16", receipt),
        TensorRecord("layers.1.attn.k.weight", (16, 16), "float16", receipt),
        TensorRecord("norm.weight", (16,), "float32", receipt),
    )


def test_artifact_manifest_counts_without_storing_tensor_values():
    manifest = build_artifact_manifest(tensors())
    assert manifest.tensor_count == 6
    assert manifest.parameter_count == 100 * 16 + 4 * 16 * 16 + 16
    assert manifest.unknown_dtype_tensors == 0
    assert ("float16", 5) in manifest.dtype_counts


def test_tensor_topology_detects_contiguous_indexed_layers():
    report = infer_tensor_topology(tensors())
    assert report.indexed_layer_count == 2
    assert report.min_layer_index == 0
    assert report.max_layer_index == 1
    assert report.contiguous_layer_indices is True
    assert report.unindexed_tensor_count == 2
    assert ((16, 16), 4) in report.recurrent_shape_groups


def test_quantization_report_measures_authorized_numeric_error():
    receipt = d("receipt")
    report = analyze_quantization(
        (
            QuantizationPair("a", (1.0, 2.0), (1.0, 1.5), receipt),
            QuantizationPair("b", (-1.0, 0.0), (-0.5, 0.0), receipt),
        )
    )
    assert report.pair_count == 2
    assert report.scalar_count == 4
    assert report.mean_absolute_error == 0.25
    assert report.max_absolute_error == 0.5
    assert report.cosine_similarity is not None


def test_evidence_chain_is_append_only_and_verifiable():
    chain = EvidenceChain().append(evidence_digest=d("a"), evidence_kind="probe")
    chain2 = chain.append(evidence_digest=d("b"), evidence_kind="topology")
    assert len(chain.entries) == 1
    assert len(chain2.entries) == 2
    assert chain2.verify() is True
    assert chain2.entries[1].previous_entry_digest == chain2.entries[0].entry_digest


def test_evidence_chain_detects_tampering():
    chain = EvidenceChain().append(evidence_digest=d("a"), evidence_kind="probe")
    bad_entry = replace(chain.entries[0], evidence_digest=d("tampered"))
    assert EvidenceChain((bad_entry,)).verify() is False


def test_manifest_digest_is_order_independent():
    first = build_artifact_manifest(tensors())
    second = build_artifact_manifest(tuple(reversed(tensors())))
    assert first.digest == second.digest
