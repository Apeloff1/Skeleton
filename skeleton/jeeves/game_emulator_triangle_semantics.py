"""Bridge measured emulator evidence into Jeeves' existing semantic lens plane.

The canonical semantic registry contains substantially more operators than
the eight deterministic training measurements. Route up to 43 of those authored
operators for each native episode; never conflate a lens question with a new
pixel, reward, video interpretation, or independent training example.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any
from collections.abc import Sequence

from .game_learning import _digest

SCHEMA = "skeleton.jeeves.game_triangle_semantic_lens_routes.v1"
SEMANTIC_LENS_BUDGET = 43


class TriangleSemanticError(ValueError):
    """Canonical Jeeves lens routing or source evidence contract differs."""


@lru_cache(maxsize=1)
def _canonical_router():
    from skeleton.jeeves.agent.semantic_maximal import (
        MaximalLensRouter, MaximalSemanticRegistry,
    )

    catalog = MaximalSemanticRegistry()
    router = MaximalLensRouter(catalog)
    if len(catalog.all()) < SEMANTIC_LENS_BUDGET:
        raise TriangleSemanticError("Jeeves semantic catalog has fewer than 43 lenses")
    # Identity commits the actual upstream lens keys and complete semantics,
    # not a local forked list of vaguely similar categories.
    identities = [
        {
            "key": spec.key, "family": spec.family.value,
            "role": spec.role.value, "description": spec.description,
            "cues": list(spec.activation_cues), "asks": list(spec.asks),
            "predicts": spec.predicts, "failure_mode": spec.failure_mode,
            "minimum_observations": spec.minimum_observations,
            "pairwise": spec.pairwise, "sequential": spec.sequential,
            "rare": spec.rare,
        }
        for spec in catalog.all()
    ]
    return router, _digest(identities), len(identities)


def _source_observations(episode: dict[str, Any]):
    """Route lens QUESTIONS using positive native measurements only.

    Do not seed the router with unobserved terms like dialogue, camera,
    game-story, music, success or emotion in a negation sentence: the canonical
    lexical router would otherwise treat those unmeasured words as support.
    """
    from skeleton.jeeves.agent.semantic_lenses import SemanticObservation

    trace = episode["source_trace_sha256"]
    receipt = episode["source_receipt_sha256"]
    measured = episode["grounded_lens_evidence"]
    companion = episode["companion_viewing"]
    play = episode["ai_playing"]
    repeat = episode["repetition"]
    optical = companion["native_rgb24_frames_optically_inspected"]
    if type(optical) is not int or optical < 0:
        raise TriangleSemanticError("native optical frame count is invalid")
    visual_tags = (
        ("visual", "frame", "pixel", "color", "observation", "video")
        if optical else ("visual", "frame", "hash", "observation")
    )
    visual_description = (
        f"Measured native RGB24 pixel color and tile inspection for {optical} "
        f"frames; source frame sequence {companion['frame_sequence_sha256']}."
        if optical else
        "Native emulator frame SHA256 sequence only: "
        f"{companion['frame_sequence_sha256']}."
    )
    probes = play["counterfactual_native_probes"]
    if type(probes) is not int or probes < 0:
        raise TriangleSemanticError("native counterfactual count is invalid")
    probe_tags = (
        ("counterfactual", "probe", "alternative", "action", "simulation")
        if probes else ("controller", "action")
    )
    alternate_description = (
        f"Executed {probes} native alternate-action counterfactual probes and "
        f"{play['controller_only_probes']} controller-only probes."
        if probes else
        f"Executed {play['controller_only_probes']} native controller-only input inspections."
    )
    content = (
        ("visual", visual_description, visual_tags),
        (
            "audio",
            "Native measured audio waveform RMS sequence "
            f"{companion['audio_sequence_sha256']}.",
            ("audio", "sound", "waveform", "rms", "measurement", "signal"),
        ),
        (
            "control",
            "Native measured controller action and executed policy sequence "
            f"{measured['controller_action']['action_sequence_sha256']}; "
            f"{play['actual_native_steps']} native transitions, "
            f"{play['actual_q_table_updates']} Q updates.",
            ("game", "controller", "input", "action", "policy", "transition"),
        ),
        (
            "reward",
            "Native measured reward and consequence sequence "
            f"{measured['reward_and_consequence']['measured_reward_sequence_sha256']}.",
            ("reward", "consequence", "measurement", "feedback"),
        ),
        (
            "temporal",
            f"Native reverse checkpoints replayed {repeat['replayed_native_steps']} "
            f"steps across {repeat['reverse_checkpoint_count']} checkpoints.",
            ("time", "temporal", "repeat", "replay", "checkpoint", "sequence"),
        ),
        (
            "counterfactual",
            alternate_description,
            probe_tags,
        ),
    )
    return tuple(
        SemanticObservation(
            observation_id=f"{trace}:{name}", content=statement, position=i,
            source="verified_native_emulator_training_triangle",
            evidence_ids=(trace, receipt), tags=tags,
            metadata={
                "positive_measurements_only": True,
                "measured_native_pixel_frames": optical if name == "visual" else 0,
                "native_counterfactual_probes": probes if name == "counterfactual" else 0,
                "semantic_game_footage_interpretation_available": False,
            },
        )
        for i, (name, statement, tags) in enumerate(content)
    )


def route_episode_semantic_lenses(episode: dict[str, Any], *,
                                 max_lenses: int = SEMANTIC_LENS_BUDGET,
                                 requested_keys: Sequence[str] = (),
                                 ) -> dict[str, Any]:
    """Select real Jeeves lens definitions from six actual native evidence views."""
    if type(max_lenses) is not int or not 1 <= max_lenses <= SEMANTIC_LENS_BUDGET:
        raise TriangleSemanticError("semantic route budget must be 1..43")
    if (type(episode) is not dict
            or type(episode.get("grounded_lens_evidence")) is not dict
            or type(episode.get("companion_viewing")) is not dict
            or type(episode.get("ai_playing")) is not dict
            or type(episode.get("repetition")) is not dict):
        raise TriangleSemanticError("semantic routing requires source-audited episode")
    if (type(requested_keys) not in (list, tuple)
            or len(requested_keys) not in (0, SEMANTIC_LENS_BUDGET)
            or any(type(key) is not str or not key
                   or key != key.strip().casefold() for key in requested_keys)
            or len(set(requested_keys)) != len(requested_keys)
            or (requested_keys and max_lenses != SEMANTIC_LENS_BUDGET)):
        raise TriangleSemanticError("custom semantic lens allocation needs 43 unique canonical keys")
    router, catalog_digest, catalog_count = _canonical_router()
    observations = _source_observations(episode)
    if requested_keys:
        from skeleton.jeeves.agent.semantic_lenses import LensSelection
        catalog = {spec.key: spec for spec in router.registry.all()}
        if any(key not in catalog for key in requested_keys):
            raise TriangleSemanticError("requested lens missing from canonical Jeeves registry")
        # Operator pinning chooses WHICH lenses, not how strongly the
        # evidence activates them. Re-run Jeeves' own router to obtain scores
        # and enforce the canonical per-family and observation requirements.
        # The old path gave every requested lens 1.0, manufacturing evidence
        # support for lenses whose cues had never appeared in gameplay.
        eligible = router.select(
            observations, requested=requested_keys, max_lenses=max_lenses,
            max_per_family=20, perpendicular=False,
        )
        eligible_by_key = {spec.key: spec for spec in eligible.lenses}
        if set(eligible_by_key) != set(requested_keys):
            raise TriangleSemanticError(
                "operator-selected lenses exceed native observation or diversity limits"
            )
        selected = tuple(catalog[key] for key in requested_keys)
        selection = LensSelection(
            lenses=selected,
            activation_scores={
                spec.key: eligible.activation_scores[spec.key]
                for spec in selected
            },
            families=tuple(sorted({spec.family for spec in selected},
                                  key=lambda family: family.value)),
            perpendicular=False,
        )
    else:
        selection = router.select_maximal(
            observations, max_lenses=max_lenses, max_per_family=5,
            minimum_rare_when_supported=3,
        )
    if max_lenses == SEMANTIC_LENS_BUDGET and len(selection.lenses) != SEMANTIC_LENS_BUDGET:
        raise TriangleSemanticError("canonical registry did not supply the requested 43 lenses")
    # Apply Jeeves' existing scientific-governance profile. Selection is a
    # question-generation permission, never a factual or causal source.
    from skeleton.jeeves.agent.semantic_governance_bridge import SemanticGovernanceBridge
    governance = SemanticGovernanceBridge().assess(selection, observations=observations)
    if governance.factual_assertion_authorized or governance.causal_assertion_authorized:
        raise TriangleSemanticError("a semantic lens attempted to create evidence authority")
    if not selection.lenses or len(selection.lenses) > max_lenses:
        raise TriangleSemanticError("canonical semantic router selection outside policy")
    route: list[dict[str, Any]] = []
    for spec in selection.lenses:
        score = selection.activation_scores.get(spec.key)
        if type(score) not in (int, float) or not 0 <= score <= 1:
            raise TriangleSemanticError("semantic lens activation lacks native router score")
        decision = governance.decision_for(spec.key)
        if (decision is None or decision.factual_assertion_authorized
                or decision.causal_assertion_authorized):
            raise TriangleSemanticError("canonical semantic lens lacks safe governance decision")
        # Positive native terms only: observational limitations and absent
        # modalities do not activate e.g. music, characters or scene reading.
        # The canonical router still allocates a 43-question budget. This
        # separate evidence check prevents a routed question being mistaken
        # for measured support of its content or prediction.
        cue_provenance = []
        for observed in observations:
            observed_words = (
                observed.content + " " + " ".join(observed.tags)
            ).casefold()
            matched = sorted({
                cue for cue in spec.activation_cues
                if cue and cue in observed_words
            })
            if matched:
                cue_provenance.append({
                    "native_observation_id": observed.observation_id,
                    "native_observation_fingerprint": observed.fingerprint,
                    "matched_positive_cues": matched,
                })
        cues = tuple(sorted({
            cue for row in cue_provenance for cue in row["matched_positive_cues"]
        }))
        route.append({
            "matched_native_observation_cues": list(cues),
            "native_observation_cue_provenance": cue_provenance,
            "native_observation_cue_provenance_sha256": _digest(cue_provenance),
            "cue_support_present": bool(cues),
            "native_evidence_support_class": (
                "measured_native_cue_present"
                if cues else "hypothesis_only_without_matching_native_cue"
            ),
            "semantic_media_interpretation_verified": False,
            "operator_requested_not_evidence": bool(requested_keys),
            "governance_grade": decision.grade.value,
            "governance_fingerprint": decision.fingerprint,
            "factual_claims_allowed": False,
            "causal_claims_allowed": False,
            "lens_key": spec.key,
            "lens_family": spec.family.value,
            "lens_role": spec.role.value,
            "activation_score": round(float(score), 6),
            "question": spec.asks[0] if spec.asks else spec.description,
            "prediction_to_test": spec.predicts,
            "failure_mode": spec.failure_mode,
            "rare": bool(spec.rare),
            "observation_count_required": spec.minimum_observations,
            "state": "routed_interpretive_question_unanswered",
            "new_independent_evidence": 0,
            "training_ground_truth_label_available": False,
        })
    keys = [row["lens_key"] for row in route]
    if len(keys) != len(set(keys)):
        raise TriangleSemanticError("a lens was selected twice for the same native evidence")
    report = {
        "schema_version": SCHEMA,
        "source_native_trace_sha256": episode["source_trace_sha256"],
        "source_native_receipt_sha256": episode["source_receipt_sha256"],
        "canonical_registry": "skeleton.jeeves.agent.semantic_maximal.MaximalSemanticRegistry",
        "canonical_catalog_sha256": catalog_digest,
        "canonical_catalog_lens_count": catalog_count,
        "requested_max_lenses": max_lenses,
        "actually_routed_lenses": len(route),
        "operator_requested_lens_keys": list(requested_keys),
        "selection_mode": "operator_exact_43" if requested_keys else "canonical_dynamic_router",
        "governance_fingerprint": governance.fingerprint,
        "semantic_lenses_remain_hypotheses_not_source_evidence": True,
        "selection_is_dynamic_not_a_claim_of_exactly_43_catalog_lenses": True,
        "source_evidence_observation_count": len(observations),
        "native_rgb24_frames_measured": episode["companion_viewing"][
            "native_rgb24_frames_optically_inspected"
        ],
        "native_counterfactual_probes_measured": episode["ai_playing"][
            "counterfactual_native_probes"
        ],
        "unobserved_semantics_cannot_activate_lens_cues": True,
        "observation_fingerprints": [obs.fingerprint for obs in observations],
        "evidence_owner": "existing_eight_measured_native_lenses",
        "factual_assertions_authorized": False,
        "causal_assertions_authorized": False,
        "additional_native_training_examples": 0,
        "actual_cue_supported_lenses": sum(item["cue_support_present"] for item in route),
        "positively_supported_native_observation_links": sum(
            len(item["native_observation_cue_provenance"]) for item in route
        ),
        "operator_selected_lenses_without_cue_support": sum(
            item["operator_requested_not_evidence"]
            and not item["cue_support_present"] for item in route
        ),
        "routes": route,
    }
    report["route_digest"] = _digest(report)
    return report


def verify_episode_semantic_lenses(episode: dict[str, Any], saved: Any) -> None:
    """Re-route from canonical authored modules and compare exact source custody."""
    if type(saved) is not dict or saved.get("route_digest") != _digest({
        k: v for k, v in saved.items() if k != "route_digest"
    }):
        raise TriangleSemanticError("saved semantic lens route receipt digest differs")
    expected = route_episode_semantic_lenses(
        episode, max_lenses=saved.get("requested_max_lenses"),
        requested_keys=saved.get("operator_requested_lens_keys"),
    )
    if saved != expected:
        raise TriangleSemanticError("semantic lens route no longer matches source or catalog")
