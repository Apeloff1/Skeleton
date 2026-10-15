"""Human-supervised shadow calibration of lawful game-asset quality observations.

Actual bounded deterministic gradient updates to a small local numeric model.
Does NOT fine-tune Jeeves/Dragon/production LLM, infer quality from game bytes,
copy game artwork, or independently validate subjective reviewer labels.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .game_decompilation_quality import QUALITY_SCHEMA

SHADOW_SCHEMA = "skeleton.game.asset_quality_shadow_model.v1"
CANDIDATE_SCHEMA = "skeleton.game.asset_quality_human_label.v1"
FEATURES = (
    "chr_tile_count", "bank_local_unique_tile_count",
    "bank_local_duplicate_count", "graphic_edge_density",
    "reachable_static_instruction_count", "static_control_flow_edge_count",
    "packaged_resource_count", "decoded_image_pixels",
    "nonopaque_pixel_fraction", "audio_sample_rate",
    "audio_duration_seconds",
)
MAX_RECORDS = 128
MAX_EPOCHS = 64


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value,sort_keys=True,separators=(",",":"),
                   ensure_ascii=True,allow_nan=False).encode()
    ).hexdigest()


def _valid_sha(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def make_human_labeled_candidate(
    brief: Mapping[str, Any], *, score: int, reviewer_ref: str,
    label_evidence_digest: str, training_rights_digest: str,
    authorize: Callable[[], bool],
) -> dict[str, Any]:
    """Scope-checked explicit review label. Training admission is separate."""
    if not callable(authorize) or authorize() is not True:
        raise PermissionError("Independent shadow-train authorization required")
    if (not isinstance(brief, dict) or brief.get("schema_version") != QUALITY_SCHEMA
        or type(score) is not int or not 0 <= score <= 100
        or type(reviewer_ref) is not str or not 1 <= len(reviewer_ref) <= 96
        or not reviewer_ref.replace("_","").replace("-","").isalnum()
        or not _valid_sha(label_evidence_digest)
        or not _valid_sha(training_rights_digest)
        or brief.get("raw_game_assets_included") is not False
        or brief.get("reconstructed_source_code_included") is not False
        or brief.get("human_review_required") is not True):
        raise ValueError("Human quality labels require exact source lineage and independent reviewer")
    unsigned = {k:v for k,v in brief.items() if k != "brief_digest"}
    if brief.get("brief_digest") != _digest(unsigned):
        raise ValueError("Measured source evidence/quality brief hash differs")
    numeric = brief.get("measured_numeric_features")
    if not isinstance(numeric, dict) or any(
        k not in FEATURES or type(v) not in (int,float)
        or not math.isfinite(v) or not 0 <= v <= 10_000_000
        for k,v in numeric.items()
    ):
        raise ValueError("Shadow learner refuses unbounded or unknown asset features")
    if not numeric:
        raise ValueError("No measured numeric features; quality cannot be learned from guesses")
    candidate = {
        "schema_version": CANDIDATE_SCHEMA,
        "source_sha256": brief["source_sha256"],
        "quality_brief_sha256": brief["brief_digest"],
        "measured_features": dict(sorted(numeric.items())),
        "human_quality_score_0_to_100": score,
        "reviewer_ref": reviewer_ref,
        "label_evidence_digest": label_evidence_digest,
        "training_rights_digest": training_rights_digest,
        "source_assets_embedded": False,
        "human_label_not_ground_truth_for_all_players": True,
        "production_model_or_language_model_updated": False,
    }
    if not _valid_sha(candidate["source_sha256"]):
        raise ValueError("Human label cannot train without a source SHA-256")
    candidate["candidate_sha256"] = _digest(candidate)
    return candidate


def _load_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict) or row.get("schema_version") != CANDIDATE_SCHEMA:
        raise ValueError("Training candidate schema invalid")
    unsigned = {k:v for k,v in row.items() if k != "candidate_sha256"}
    if _digest(unsigned) != row.get("candidate_sha256"):
        raise ValueError("Human-labeled asset candidate changed after admission")
    if (row.get("source_assets_embedded") is not False
        or row.get("production_model_or_language_model_updated") is not False
        or row.get("human_label_not_ground_truth_for_all_players") is not True
        or not all(_valid_sha(row.get(k)) for k in
                   ("source_sha256","quality_brief_sha256",
                    "label_evidence_digest","training_rights_digest"))
        or type(row.get("human_quality_score_0_to_100")) is not int
        or not 0 <= row["human_quality_score_0_to_100"] <= 100):
        raise ValueError("Human-source lineage or declared bounded score invalid")
    feats = row.get("measured_features")
    if not isinstance(feats, dict) or not feats or any(
        key not in FEATURES or type(value) not in (float,int)
        or not math.isfinite(value) or not 0 <= value <= 10_000_000
        for key,value in feats.items()
    ):
        raise ValueError("Human label contains unknown/invalid numeric feature")
    return dict(row)


def _features(row: Mapping[str, Any]) -> list[float]:
    measured = row["measured_features"]
    # Fixed normalizers prevent held-out statistics leaking into training.
    caps = (8192, 8192, 8192, 1, 4096, 8192, 128,
            1024 * 1024, 1, 96000, 10)
    output=[]
    for name,cap in zip(FEATURES,caps,strict=True):
        val = float(measured.get(name,0))
        output.append(min(1.0, math.log1p(val)/math.log1p(cap)))
    return output


def _infer(weights: Sequence[float], bias: float, xs: Sequence[float]) -> float:
    return min(1, max(0, bias + sum(a*b for a,b in zip(weights,xs,strict=True))))


def train_shadow_asset_quality_model(
    candidates: Sequence[Mapping[str, Any]], *,
    authorize: Callable[[], bool],
    epochs: int = 48,
    learning_rate: float = 0.08,
) -> dict[str, Any]:
    """Train locally and evaluate held-out sources; fail closed if not better."""
    if not callable(authorize) or authorize() is not True:
        raise PermissionError("A newly checked shadow-model training authorization is required")
    if (not isinstance(candidates,(tuple,list)) or not 8 <= len(candidates) <= MAX_RECORDS
        or type(epochs) is not int or not 1 <= epochs <= MAX_EPOCHS
        or type(learning_rate) not in (int,float) or not math.isfinite(learning_rate)
        or not 0.0001 <= learning_rate <= 0.2):
        raise ValueError("Shadow training requires 8–128 distinct bounded human-labeled cases")
    loaded = [_load_candidate(row) for row in candidates]
    if len({r["source_sha256"] for r in loaded}) != len(loaded):
        raise ValueError("Same source may not appear twice across train or holdout")
    if len({r["candidate_sha256"] for r in loaded}) != len(loaded):
        raise ValueError("Duplicate human review record")
    # Stable source-dependent holdout assignment. Prevent training on test
    # copies of the same game and no random seed dependencies.
    ordered = sorted(loaded, key=lambda row: row["source_sha256"])
    valid_count = max(2,len(loaded)//4)
    train, valid = ordered[:-valid_count], ordered[-valid_count:]
    if len(train) < 6:
        raise ValueError("At least six distinct reviewed sources needed to fit")
    train_vectors = [(_features(r),r["human_quality_score_0_to_100"]/100) for r in train]
    valid_vectors = [(_features(r),r["human_quality_score_0_to_100"]/100) for r in valid]
    baseline = sum(y for _,y in train_vectors)/len(train_vectors)

    def loss(weights: Sequence[float], bias: float, items: Sequence[tuple]) -> float:
        return sum((_infer(weights,bias,x)-y)**2 for x,y in items)/len(items)

    baseline_loss = loss([0.0]*len(FEATURES),baseline,valid_vectors)
    weights=[0.0]*len(FEATURES)
    bias=baseline
    for _ in range(epochs):
        # Pure batch-gradient MSE, deterministic order, small L2 shrinkage.
        predictions=[_infer(weights,bias,x)-y for x,y in train_vectors]
        gradients=[
            2*sum(error*x[i] for (x,_),error in zip(train_vectors,predictions,strict=True))
            /len(train_vectors)+0.01*weights[i]
            for i in range(len(FEATURES))
        ]
        bias_gradient=2*sum(predictions)/len(predictions)
        weights=[max(-2.0,min(2.0,w-learning_rate*g)) for w,g in zip(weights,gradients,strict=True)]
        bias=max(-1.0,min(2.0,bias-learning_rate*bias_gradient))
    actual_loss=loss(weights,bias,valid_vectors)
    accepted=actual_loss + 0.0001 < baseline_loss
    model = {
        "schema_version": SHADOW_SCHEMA,
        "algorithm": "deterministic_bounded_batch_gradient_mse_l2",
        "feature_order": list(FEATURES), "weights": [round(x,9) for x in weights],
        "bias": round(bias,9), "epochs": epochs,
        "learning_rate": learning_rate,
        "train_cases": len(train), "held_out_cases": len(valid),
        "train_source_commitment": _digest([r["source_sha256"] for r in train]),
        "validation_source_commitment": _digest([r["source_sha256"] for r in valid]),
        "candidate_set_sha256": _digest(sorted(r["candidate_sha256"] for r in loaded)),
        "human_review_not_absolute_game_quality": True,
        "source_code_or_asset_bytes_in_model": False,
        "baseline_holdout_mse": round(baseline_loss,8),
        "trained_holdout_mse": round(actual_loss,8),
        "heldout_improvement": round(baseline_loss-actual_loss,8),
        "passed_holdout_guard": accepted,
        "promotion_admissible": False,
        "production_model_weights_updated": False,
        "shadow_numeric_parameters_actually_fit": True,
        "model_type": "local_tabular_asset_quality_shadow_regressor",
    }
    model["checkpoint_sha256"]=_digest(model)
    return model


def infer_shadow_asset_quality(
    model: Mapping[str, Any], features: Mapping[str, float],
) -> dict[str, Any]:
    if not isinstance(model, dict) or model.get("schema_version")!=SHADOW_SCHEMA:
        raise ValueError("Bounded shadow model snapshot required")
    digest=model.get("checkpoint_sha256")
    if digest!=_digest({k:v for k,v in model.items() if k!="checkpoint_sha256"}):
        raise ValueError("Shadow model checkpoint changed")
    if (model.get("feature_order")!=list(FEATURES)
        or not isinstance(model.get("weights"),list)
        or len(model["weights"])!=len(FEATURES)
        or any(type(w) not in (float,int) or not math.isfinite(w) or abs(w)>2
               for w in model["weights"])
        or type(model.get("bias")) not in (float,int)
        or not math.isfinite(model["bias"])
        or model.get("production_model_weights_updated") is not False):
        raise ValueError("Shadow model coefficient or deployment state invalid")
    if not isinstance(features,dict) or not features or any(
        k not in FEATURES or type(v) not in (float,int)
        or not math.isfinite(v) or not 0<=v<=10_000_000
        for k,v in features.items()
    ):
        raise ValueError("Unknown, unbounded or nonnumeric asset features")
    prediction=_infer(model["weights"],model["bias"],_features({"measured_features":features}))
    return {
        "schema_version": "skeleton.game.asset_quality_shadow_inference.v1",
        "shadow_model_sha256":digest,
        "relative_human_label_estimate": round(100*prediction,4),
        "score_semantics": "human_label_fit_not_objective_game_quality",
        "training_or_production_weight_mutation":False,
    }
