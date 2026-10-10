"""Layered analysis chains for the Dragon companion.

A typed, deterministic analysis plan preserves explicit evidence custody from
raw observations through hypotheses, adversarial tests and knowledge promotion.
No stage is treated as having run until its evidence receipt is supplied.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json


class AnalysisLayer(str, Enum):
    SOURCE_INTEGRITY = "source_integrity"
    TEMPORAL_SEGMENTATION = "temporal_segmentation"
    OBJECT_TRACKING = "object_tracking"
    STATE_INFERENCE = "state_inference"
    MECHANIC_HYPOTHESES = "mechanic_hypotheses"
    CAUSAL_FALSIFICATION = "causal_falsification"
    CROSS_SOURCE_CORROBORATION = "cross_source_corroboration"
    UNCERTAINTY_CALIBRATION = "uncertainty_calibration"
    KNOWLEDGE_NORMALIZATION = "knowledge_normalization"
    ADVERSARIAL_REVIEW = "adversarial_review"
    HUMAN_APPROVAL = "human_approval"
    MEMORY_PROMOTION = "memory_promotion"


@dataclass(frozen=True)
class LayerSpec:
    layer: AnalysisLayer
    dependencies: tuple[AnalysisLayer, ...]
    requires_human: bool = False
    min_independent_sources: int = 1


@dataclass(frozen=True)
class LayerReceipt:
    layer: AnalysisLayer
    input_fingerprints: tuple[str, ...]
    output_fingerprint: str
    independent_sources: int
    passed: bool
    human_approved: bool = False


@dataclass(frozen=True)
class ChainVerdict:
    complete: bool
    accepted_layers: tuple[AnalysisLayer, ...]
    pending_layers: tuple[AnalysisLayer, ...]
    rejected_layers: tuple[AnalysisLayer, ...]
    fingerprint: str


DEFAULT_CHAIN = (
    LayerSpec(AnalysisLayer.SOURCE_INTEGRITY, ()),
    LayerSpec(AnalysisLayer.TEMPORAL_SEGMENTATION, (AnalysisLayer.SOURCE_INTEGRITY,)),
    LayerSpec(AnalysisLayer.OBJECT_TRACKING, (AnalysisLayer.TEMPORAL_SEGMENTATION,)),
    LayerSpec(AnalysisLayer.STATE_INFERENCE, (AnalysisLayer.OBJECT_TRACKING,)),
    LayerSpec(AnalysisLayer.MECHANIC_HYPOTHESES, (AnalysisLayer.STATE_INFERENCE,)),
    LayerSpec(AnalysisLayer.CAUSAL_FALSIFICATION, (AnalysisLayer.MECHANIC_HYPOTHESES,)),
    LayerSpec(AnalysisLayer.CROSS_SOURCE_CORROBORATION, (AnalysisLayer.CAUSAL_FALSIFICATION,),
              min_independent_sources=2),
    LayerSpec(AnalysisLayer.UNCERTAINTY_CALIBRATION, (AnalysisLayer.CROSS_SOURCE_CORROBORATION,)),
    LayerSpec(AnalysisLayer.KNOWLEDGE_NORMALIZATION, (AnalysisLayer.UNCERTAINTY_CALIBRATION,)),
    LayerSpec(AnalysisLayer.ADVERSARIAL_REVIEW, (AnalysisLayer.KNOWLEDGE_NORMALIZATION,)),
    LayerSpec(AnalysisLayer.HUMAN_APPROVAL, (AnalysisLayer.ADVERSARIAL_REVIEW,),
              requires_human=True),
    LayerSpec(AnalysisLayer.MEMORY_PROMOTION, (AnalysisLayer.HUMAN_APPROVAL,)),
)


def _digest(payload: object) -> str:
    return sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode()).hexdigest()


def validate_chain(
    receipts: tuple[LayerReceipt, ...], *,
    authorized: bool, chain: tuple[LayerSpec, ...] = DEFAULT_CHAIN,
) -> ChainVerdict:
    if not authorized:
        raise PermissionError("analysis chain requires authorization")
    specs = {item.layer: item for item in chain}
    if len(specs) != len(chain):
        raise ValueError("duplicate analysis layer")
    visited = set()
    topological = []
    def check(layer: AnalysisLayer, active: set[AnalysisLayer]) -> None:
        if layer in active:
            raise ValueError("cyclic analysis chain")
        if layer in visited:
            return
        if layer not in specs:
            raise ValueError("unknown analysis dependency")
        active.add(layer)
        for dep in specs[layer].dependencies:
            check(dep, active)
        active.remove(layer)
        visited.add(layer)
        topological.append(layer)
    for layer in specs:
        check(layer, set())
    by_layer = {}
    for receipt in receipts:
        if receipt.layer not in specs or receipt.layer in by_layer:
            raise ValueError("unknown or duplicate layer receipt")
        if not isinstance(receipt.passed, bool) or not isinstance(receipt.human_approved, bool):
            raise ValueError("invalid receipt flags")
        if not isinstance(receipt.independent_sources, int) or receipt.independent_sources < 0:
            raise ValueError("invalid independent source count")
        for digest in (*receipt.input_fingerprints, receipt.output_fingerprint):
            if not isinstance(digest, str) or len(digest) != 64 or any(
                ch not in "0123456789abcdef" for ch in digest
            ):
                raise ValueError("invalid evidence fingerprint")
        by_layer[receipt.layer] = receipt
    accepted, rejected = set(), set()
    for layer in topological:
        spec = specs[layer]
        receipt = by_layer.get(layer)
        if receipt is None:
            continue
        if any(dep not in accepted for dep in spec.dependencies):
            rejected.add(layer)
            continue
        expected_inputs = tuple(by_layer[dep].output_fingerprint for dep in spec.dependencies)
        if receipt.input_fingerprints != expected_inputs:
            rejected.add(layer)
        elif not receipt.passed or receipt.independent_sources < spec.min_independent_sources:
            rejected.add(layer)
        elif spec.requires_human and not receipt.human_approved:
            rejected.add(layer)
        else:
            accepted.add(layer)
    ordered = tuple(spec.layer for spec in chain)
    accepted_order = tuple(layer for layer in ordered if layer in accepted)
    rejected_order = tuple(layer for layer in ordered if layer in rejected)
    pending = tuple(layer for layer in ordered if layer not in by_layer)
    return ChainVerdict(
        len(accepted) == len(chain), accepted_order, pending, rejected_order,
        _digest([(r.layer.value, r.input_fingerprints, r.output_fingerprint,
                  r.independent_sources, r.passed, r.human_approved)
                 for r in sorted(receipts, key=lambda x: x.layer.value)]),
    )
