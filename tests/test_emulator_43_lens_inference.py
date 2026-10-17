"""43 canonical Jeeves lens model outputs: source and governance custody."""
from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from skeleton.jeeves.game_learning import _digest
from skeleton.jeeves import game_emulator_triangle_semantic_inference as lens_inference


def _fixture(monkeypatch):
    from skeleton.ai.model_runtime import native_llm_runtime

    source = {
        "source_trace_sha256": "a" * 64,
        "source_receipt_sha256": "b" * 64,
        "unique_source_transitions": 3,
        "companion_viewing": {
            "frame_sequence_sha256": "c" * 64,
            "native_rgb24_frames_optically_inspected": 3,
        },
        "ai_playing": {
            "actual_tabular_q_updates": 2,
            "counterfactual_native_probes": 2,
        },
        "repetition": {"replayed_native_steps": 6},
        "grounded_lens_evidence": {
            "reward_and_consequence": {
                "measured_reward_sequence_sha256": "d" * 64,
            },
        },
    }
    catalog = [{
        "lens_key": "authored_semantic_" + str(i),
        "lens_role": "prediction",
        "lens_family": "game",
        "question": "What additional real gameplay observation would falsify this pattern?",
        "prediction_to_test": "Future repeated native gameplay might show a new pattern.",
        "failure_mode": "No semantic interpretation is directly observed.",
        "governance_fingerprint": f"{i + 12:064x}",
    } for i in range(43)]
    route = {
        "actually_routed_lenses": 43,
        "routes": catalog,
        "canonical_catalog_sha256": "e" * 64,
        "route_digest": "f" * 64,
        "governance_fingerprint": "9" * 64,
    }
    monkeypatch.setattr(lens_inference, "verify_training_triangle", lambda *_: None)
    monkeypatch.setattr(lens_inference, "verify_native_adversarial_review", lambda *_: None)
    monkeypatch.setattr(
        lens_inference, "route_episode_semantic_lenses",
        lambda _source, **_kwargs: route,
    )
    class FakeNativeRuntime:
        model_digest = "8" * 64
        def __init__(self):
            self.calls = []
        def assert_model_unchanged(self):
            return None
        def generate(self, prompt, config):
            data = json.loads(prompt.split("\n")[-1])
            self.calls.append(data["lens_key"])
            value = json.dumps({
                "lens_key": data["lens_key"],
                "native_trace_sha256": data["native_trace_sha256"],
                "hypothesis": "A repeat might identify a measurable difference in the native state.",
                "falsifier": "A controlled independent replay may disprove this possible pattern.",
                "epistemic_state": "unverified_hypothesis",
            })
            rr = SimpleNamespace(
                to_dict=lambda: {
                    "model_digest": "8" * 64,
                    "seed": config.seed,
                    "output_digest": "7" * 64,
                    "request_digest": "6" * 64,
                },
            )
            return SimpleNamespace(
                text=value, generated_ids=(1, 2),
                replay_receipt=rr,
                to_record=lambda: {
                    "model_digest": "8" * 64,
                    "output_digest": "7" * 64,
                    "request_digest": "6" * 64,
                    "generated_token_ids": [1, 2],
                },
            )
    monkeypatch.setattr(native_llm_runtime, "NativeLLMRuntime", FakeNativeRuntime)
    evidence = {"report_digest": "2" * 64}
    triangle = {"triangle_digest": "3" * 64,
                "episode_lens_references": [source]}
    adversarial = {"review_digest": "4" * 64,
                   "structured_source_bound_passes": 3}
    return evidence, triangle, adversarial, FakeNativeRuntime


def test_executes_43_actual_model_calls_and_preserves_one_game(monkeypatch):
    evidence, triangle, critic, Model = _fixture(monkeypatch)
    model = Model()
    receipt = lens_inference.run_native_semantic_lenses(
        evidence, triangle, critic, model, max_new_tokens=80,
    )
    assert len(model.calls) == 43
    assert len(set(model.calls)) == 43
    assert receipt["native_model_generations_executed"] == 43
    assert receipt["source_bound_interpretations"] == 43
    assert receipt["all_semantic_interpretations_valid"] is True
    assert receipt["actual_native_gameplay_steps_added_by_lenses"] == 0
    assert receipt["additional_independent_training_examples"] == 0
    assert receipt["production_jeeves_weight_updates"] == 0
    assert receipt["semantic_hypotheses_admitted_as_ground_truth"] is False
    lens_inference.verify_native_semantic_lenses(evidence, triangle, critic, receipt)


def test_forged_gen_model_or_lens_key_fails_even_if_json_resealed(monkeypatch):
    evidence, triangle, critic, Model = _fixture(monkeypatch)
    receipt = lens_inference.run_native_semantic_lenses(
        evidence, triangle, critic, Model(), max_new_tokens=80,
    )
    forged = deepcopy(receipt)
    forged["entries"][4]["lens_key"] = "different_lens"
    forged["semantic_review_digest"] = _digest({
        k: v for k, v in forged.items() if k != "semantic_review_digest"
    })
    with pytest.raises(ValueError, match="key sequence"):
        lens_inference.verify_native_semantic_lenses(evidence, triangle, critic, forged)
    forged = deepcopy(receipt)
    forged["entries"][1]["native_inference_receipt"]["seed"] = 900
    forged["semantic_review_digest"] = _digest({
        k: v for k, v in forged.items() if k != "semantic_review_digest"
    })
    with pytest.raises(ValueError, match="token custody"):
        lens_inference.verify_native_semantic_lenses(evidence, triangle, critic, forged)


def test_adversarial_critic_must_have_all_three_grounded_challenges(monkeypatch):
    evidence, triangle, critic, Model = _fixture(monkeypatch)
    critic["structured_source_bound_passes"] = 2
    with pytest.raises(ValueError, match="three"):
        lens_inference.run_native_semantic_lenses(
            evidence, triangle, critic, Model(),
        )


@pytest.mark.parametrize("text", [
    '{"lens_key":"other","native_trace_sha256":"abc"}',
    "this is not a structured model inference",
    '{"lens_key":"authored_semantic_0","native_trace_sha256":"a",'
    '"hypothesis":"whatever","falsifier":"unknown",'
    '"epistemic_state":"verified_success"}',
])
def test_unverified_semantic_model_prose_never_becomes_ground_truth(text):
    result = lens_inference._interpret(
        text, lens_key="authored_semantic_0", trace="a" * 64,
    )
    assert result["status"].startswith("manual_review_required")


def test_cli_provides_two_distinct_checkpoint_selection_fields():
    from scripts.training.rom_study import parser
    args = parser().parse_args([
        "execute-43-lenses",
        "--receipt", "/tmp/rom.json",
        "--review-receipt", "/tmp/critic.json",
        "--source-sha256", "a" * 64,
        "--critic-checkpoint", "/tmp/adversarial.json",
        "--semantic-checkpoint", "/tmp/semantic.json",
        "--output-dir", "/tmp/private",
    ])
    assert args.operation == "execute-43-lenses"
    assert args.max_new_tokens == 192
    assert args.critic_checkpoint != args.semantic_checkpoint


def test_unstructured_lens_response_is_kept_for_replay_not_certified(monkeypatch):
    evidence, triangle, critic, Model = _fixture(monkeypatch)
    original = Model.generate

    def one_unstructured_result(self, prompt, config):
        result = original(self, prompt, config)
        if len(self.calls) == 17:
            return SimpleNamespace(
                text="UNSTRUCTURED_REAL_GENERATION",
                generated_ids=result.generated_ids,
                replay_receipt=result.replay_receipt,
                to_record=result.to_record,
            )
        return result

    monkeypatch.setattr(Model, "generate", one_unstructured_result)
    receipt = lens_inference.run_native_semantic_lenses(
        evidence, triangle, critic, Model(), max_new_tokens=80,
    )
    assert receipt["native_model_generations_executed"] == 43
    assert receipt["source_bound_interpretations"] == 42
    assert receipt["all_semantic_lenses_executed"] is True
    assert receipt["all_semantic_interpretations_valid"] is False
    assert receipt["entries"][16]["interpretation"]["status"].startswith("manual_review_required")
    lens_inference.verify_native_semantic_lenses(evidence, triangle, critic, receipt)

    falsified = deepcopy(receipt)
    falsified["all_semantic_interpretations_valid"] = True
    falsified["semantic_review_digest"] = _digest({
        k: v for k, v in falsified.items() if k != "semantic_review_digest"
    })
    with pytest.raises(ValueError, match="completeness"):
        lens_inference.verify_native_semantic_lenses(evidence, triangle, critic, falsified)
