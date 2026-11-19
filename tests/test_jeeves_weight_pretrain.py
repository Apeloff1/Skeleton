"""Pretraining waits for full use at peak fidelity on the cutting-edge stack."""
from __future__ import annotations

from skeleton.cortex.neocortex import JeevesCortex


def test_pretrain_refuses_until_usage_and_fidelity_are_confirmed():
    neo = JeevesCortex()
    steps = neo.transformer.steps
    adaptive = neo.dynamic_weights.adaptive.steps
    refused = neo.pretrain_weights()
    assert refused["kind"] == "jeeves-weight-pretrain"
    assert refused["pretrained"] is False
    assert refused["once"] is True
    assert refused["reason"] == "usage_incomplete"
    assert refused["shadow_weights_promoted"] is False
    assert set(refused["confirmation"]["usage"]["missing"]) >= {
        "weights", "shadow_weights", "adaptive_weights", "reactive_weights",
    }
    assert neo.transformer.steps == steps
    assert neo.dynamic_weights.adaptive.steps == adaptive
    assert neo._weight_pretrain_receipt is None


def test_cutting_edge_stack_is_the_current_epoch():
    neo = JeevesCortex()
    edge = neo.confirm_weight_pretrain()["cutting_edge"]
    assert edge["cutting_edge"] is True
    assert edge["epoch"] == 2020
    assert edge["missing_capabilities"] == []
    assert edge["checks"]["rms_norm"] is True
    assert edge["checks"]["swiglu"] is True


def test_pretrain_runs_once_after_peak_confirmation(tmp_path):
    neo = JeevesCortex()
    neo.train(epochs=1)
    neo.step_dynamic_weights("soulslike extraction ttk elite dread")
    neo.speak_dynamic("forge run", n=2, seed=1)
    confirmation = neo.confirm_weight_pretrain()
    assert confirmation["authorized"] is True
    assert confirmation["usage"]["full"] is True
    assert confirmation["fidelity"]["peak"] is True
    assert confirmation["fidelity"]["score"] >= 0.94
    assert confirmation["cutting_edge"]["cutting_edge"] is True

    before_steps = neo.transformer.steps
    before_adaptive = neo.dynamic_weights.adaptive.steps
    before_shadow = confirmation["usage"]["shadow_trials"]
    trained = neo.pretrain_weights()
    assert trained["pretrained"] is True
    assert trained["once"] is True
    assert trained["shadow_weights_promoted"] is False
    assert trained["weights_steps"] > before_steps
    assert trained["adaptive_steps"] > before_adaptive
    assert trained["receipt"]["passes"] == 1
    assert trained["receipt"]["schedule"] == "cosine"
    assert trained["receipt"]["shadow_trials_after"] == before_shadow
    assert len(trained["receipt"]["digest"]) == 64

    again_steps = neo.transformer.steps
    again_adaptive = neo.dynamic_weights.adaptive.steps
    repeat = neo.pretrain_weights()
    assert repeat["pretrained"] is False
    assert repeat["reason"] == "already_pretrained"
    assert neo.transformer.steps == again_steps
    assert neo.dynamic_weights.adaptive.steps == again_adaptive

    path = tmp_path / "jeeves.json"
    neo.save(path)
    restored = JeevesCortex()
    restored.load(path)
    held = restored.pretrain_weights()
    assert held["reason"] == "already_pretrained"
    assert held["pretrained"] is False
