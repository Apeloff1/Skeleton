"""All 200 authored Jeeves first-order lenses over source-bound native gameplay.

This is the *complete* canonical skeleton.jeeves.agent.lens_system.LensCatalog,
not an arbitrary 200-out-of-N lexical route from MaximalSemanticRegistry.
Every lens gets an inspectable question and a real native evidence reference.
Unsupported lenses stay pending hypotheses. They NEVER become measurements,
independent training samples, model claims or approved production weights.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from .game_learning import _digest

SCHEMA = "skeleton.jeeves.game_triangle_semantic_lens_routes.v1"
CATALOG_OWNER = "skeleton.jeeves.agent.lens_system.LensCatalog"
COMPLETE_LENS_COUNT = 200


class CompleteLensError(ValueError):
    """Canonical lens catalog drift or native observation mismatch."""


@lru_cache(maxsize=1)
def _catalog():
    from skeleton.jeeves.agent.lens_system import LensCatalog
    catalog = LensCatalog()
    lenses = catalog.all()
    if len(lenses) != COMPLETE_LENS_COUNT:
        raise CompleteLensError(
            "Jeeves canonical first-order lens catalog no longer contains exactly 200 definitions"
        )
    if len({lens.lens_id for lens in lenses}) != COMPLETE_LENS_COUNT:
        raise CompleteLensError("Jeeves canonical first-order catalog repeats a lens")
    if any(not lens.preserves_source_truth or not lens.outputs for lens in lenses):
        raise CompleteLensError("one canonical Jeeves lens violates evidence-preservation contract")
    full_identity = _digest([
        {
            "id": lens.lens_id, "family": lens.family.value,
            "authority": lens.authority.value, "description": lens.description,
            "cues": list(lens.cues), "outputs": list(lens.outputs),
            "incompatible_with": list(lens.incompatible_with),
            "preserves_source_truth": lens.preserves_source_truth,
        } for lens in lenses
    ])
    return lenses, catalog.fingerprint, full_identity


def route_complete_lens_catalog(episode: dict[str, Any], *,
                                requested_keys: tuple[str, ...] = ()) -> dict[str, Any]:
    """Allocate all 200 authored lenses, incl. those without matching native cues.

    Operator key manifests, if supplied, must be an exact permutation of the
    canonical 200 keys: they may change order, never omit or invent a lens.
    """
    from .game_emulator_triangle_semantics import _source_observations
    if type(episode) is not dict or not isinstance(episode.get("grounded_lens_evidence"), dict):
        raise CompleteLensError("complete lens routing requires verified native episode measurements")
    definitions, upstream_fingerprint, identity = _catalog()
    by_id = {lens.lens_id: lens for lens in definitions}
    if requested_keys:
        if (type(requested_keys) not in (list, tuple)
                or len(requested_keys) != COMPLETE_LENS_COUNT
                or len(set(requested_keys)) != COMPLETE_LENS_COUNT
                or set(requested_keys) != set(by_id)):
            raise CompleteLensError(
                "the 200-lens operator manifest must include ALL canonical Jeeves first-order lens IDs"
            )
        chosen = [by_id[key] for key in requested_keys]
    else:
        chosen = list(definitions)
    observations = _source_observations(episode)
    trace = episode["source_trace_sha256"]
    receipt = episode["source_receipt_sha256"]
    records: list[dict[str, Any]] = []
    for lens in chosen:
        # A catalog definition is not an executed statistical computation.
        # Conservatively index positive cues in *actual* observations only.
        provenance: list[dict[str, Any]] = []
        for observation in observations:
            observed = (observation.content + " " + " ".join(observation.tags)).casefold()
            matches = sorted(cue for cue in lens.cues if cue in observed)
            if matches:
                provenance.append({
                    "native_observation_id": observation.observation_id,
                    "native_observation_fingerprint": observation.fingerprint,
                    "matched_positive_cues": matches,
                })
        matched_cues = sorted({cue for row in provenance for cue in row["matched_positive_cues"]})
        grade = lens.authority.value
        policy = {
            "lens_id": lens.lens_id,
            "family": lens.family.value,
            "authority": grade,
            "outputs": list(lens.outputs),
            "preserves_source_truth": lens.preserves_source_truth,
            "native_factual_claims_allowed": False,
            "native_causal_claims_allowed": False,
            "model_review_required": True,
        }
        records.append({
            "lens_key": lens.lens_id,
            "lens_family": lens.family.value,
            "lens_role": "canonical_" + grade + "_operator",
            "governance_grade": grade,
            "governance_fingerprint": _digest(policy),
            "matched_native_observation_cues": matched_cues,
            "native_observation_cue_provenance": provenance,
            "native_observation_cue_provenance_sha256": _digest(provenance),
            "cue_support_present": bool(matched_cues),
            "native_evidence_support_class": (
                "measured_native_cue_present" if matched_cues
                else "hypothesis_only_without_matching_native_cue"
            ),
            "semantic_media_interpretation_verified": False,
            "operator_requested_not_evidence": bool(requested_keys),
            "factual_claims_allowed": False,
            "causal_claims_allowed": False,
            "activation_score": round(len(matched_cues) / max(1, len(lens.cues)), 6),
            "question": (
                "Inspect the " + lens.name.lower() + " operator: "
                + lens.description[:240]
            ),
            "prediction_to_test": (
                "Seek independent native measurements for outputs "
                + ", ".join(lens.outputs[:6])
                + "; abstain when unmeasured."
            ),
            "failure_mode": (
                "Misreading a catalog-level interpretive question as native "
                "evidence or independently observed game behavior."
            ),
            "rare": False,
            "observation_count_required": 1,
            "state": "routed_interpretive_question_unanswered",
            "new_independent_evidence": 0,
            "training_ground_truth_label_available": False,
        })
    if len(records) != COMPLETE_LENS_COUNT or len({
            row["lens_key"] for row in records}) != COMPLETE_LENS_COUNT:
        raise CompleteLensError("an authored Jeeves lens was not scheduled")
    report = {
        "schema_version": SCHEMA,
        "source_native_trace_sha256": trace,
        "source_native_receipt_sha256": receipt,
        "canonical_registry": CATALOG_OWNER,
        "canonical_catalog_sha256": identity,
        "canonical_catalog_lens_count": COMPLETE_LENS_COUNT,
        "canonical_lens_catalog_fingerprint": upstream_fingerprint,
        "requested_max_lenses": COMPLETE_LENS_COUNT,
        "actually_routed_lenses": len(records),
        "operator_requested_lens_keys": list(requested_keys),
        "selection_mode": (
            "operator_exact_200_complete_catalog" if requested_keys
            else "complete_canonical_200_catalog"
        ),
        "governance_fingerprint": _digest([
            row["governance_fingerprint"] for row in records
        ]),
        "semantic_lenses_remain_hypotheses_not_source_evidence": True,
        "selection_is_dynamic_not_a_claim_of_exactly_43_catalog_lenses": False,
        "source_evidence_observation_count": len(observations),
        "native_rgb24_frames_measured": episode["companion_viewing"][
            "native_rgb24_frames_optically_inspected"
        ],
        "native_counterfactual_probes_measured": episode["ai_playing"][
            "counterfactual_native_probes"
        ],
        "unobserved_semantics_cannot_activate_lens_cues": True,
        "observation_fingerprints": [
            observation.fingerprint for observation in observations
        ],
        "evidence_owner": "existing_eight_measured_native_lenses",
        "factual_assertions_authorized": False,
        "causal_assertions_authorized": False,
        "additional_native_training_examples": 0,
        "actual_cue_supported_lenses": sum(
            row["cue_support_present"] for row in records
        ),
        "positively_supported_native_observation_links": sum(
            len(row["native_observation_cue_provenance"])
            for row in records
        ),
        "operator_selected_lenses_without_cue_support": sum(
            row["operator_requested_not_evidence"]
            and not row["cue_support_present"] for row in records
        ),
        "routes": records,
    }
    report["route_digest"] = _digest(report)
    return report
