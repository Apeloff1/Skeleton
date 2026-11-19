"""AAA game-creation pretraining fills every active Jeeves weight."""
from __future__ import annotations

from skeleton.cortex.neocortex import JeevesCortex


def _ready():
    neo = JeevesCortex()
    neo.train(epochs=1)
    neo.step_dynamic_weights("soulslike extraction ttk elite dread")
    neo.speak_dynamic("forge run", n=2, seed=1)
    return neo


def test_mass_pretrain_refuses_before_full_use():
    neo = JeevesCortex()
    steps = neo.transformer.steps
    adaptive = neo.dynamic_weights.adaptive.steps
    refused = neo.mass_pretrain_for_game_creation()
    assert refused["kind"] == "jeeves-aaa-mass-pretrain"
    assert refused["pretrained"] is False
    assert refused["reason"] == "usage_incomplete"
    assert refused["shadow_weights_promoted"] is False
    assert neo.transformer.steps == steps
    assert neo.dynamic_weights.adaptive.steps == adaptive
    assert neo._weight_mass_pretrain_receipt is None


def test_mass_pretrain_fills_every_active_weight_once(tmp_path):
    neo = _ready()
    before_steps = neo.transformer.steps
    before_adaptive = neo.dynamic_weights.adaptive.steps
    trained = neo.mass_pretrain_for_game_creation()
    assert trained["pretrained"] is True
    assert trained["once"] is True
    assert trained["level"] == "aaa"
    assert trained["domain"] == "game_creation"
    assert trained["shadow_weights_promoted"] is False
    assert trained["weights_steps"] > before_steps + 500
    assert trained["adaptive_steps"] > before_adaptive
    fill = trained["fill"]
    assert fill["filled"] is True
    for name in ("weights", "rms_weights", "adaptive_weights", "reactive_weights"):
        bank = fill["banks"][name]
        assert bank["zeros"] == 0
        assert bank["nonfinite"] == 0
        assert bank["nonzero"] == bank["cells"]
        assert bank["cells"] > 0
    assert fill["shadow_trials"]
    assert min(fill["shadow_trials"].values()) >= 4
    assert fill["inactive_cells"]["gelu_gate"] > 0
    assert fill["inactive_cells"]["rms_bias"] > 0
    assert trained["receipt"]["epochs"] == 3
    assert trained["receipt"]["passes"] == 1
    assert len(trained["receipt"]["digest"]) == 64

    frozen_steps = neo.transformer.steps
    frozen_adaptive = neo.dynamic_weights.adaptive.steps
    repeat = neo.mass_pretrain_for_game_creation()
    assert repeat["pretrained"] is False
    assert repeat["reason"] == "already_mass_pretrained"
    assert neo.transformer.steps == frozen_steps
    assert neo.dynamic_weights.adaptive.steps == frozen_adaptive

    path = tmp_path / "jeeves-aaa.json"
    neo.save(path)
    restored = JeevesCortex()
    restored.load(path)
    held = restored.mass_pretrain_for_game_creation()
    assert held["reason"] == "already_mass_pretrained"
    assert held["pretrained"] is False
    assert held["fill"]["filled"] is True
