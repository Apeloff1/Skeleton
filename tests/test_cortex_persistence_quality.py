from __future__ import annotations

from skeleton.cortex import JeevesCortex
from skeleton.cortex.callosum import CorpusCallosum
from skeleton.cortex.midbrain import Midbrain


def test_cuda_request_contract_is_exact_even_when_hardware_degrades() -> None:
    neo = JeevesCortex()

    result = neo.to("cuda")

    assert result["requested"] == "cuda"
    assert result["cuda"] in {True, False}
    assert result["degraded"] is (not result["cuda"])
    if not result["cuda"]:
        assert result["actual"] == "cpu"
        assert neo.status()["lm"]["device"] == "cpu"


def test_bilateral_callosum_fusion_changes_the_fused_residual() -> None:
    cc = CorpusCallosum(dim=8, seed=8)
    hidden = [0.3, 0.1, -0.2, 0.4, 0.0, 0.2, -0.1, 0.5]

    unilateral, _, _ = cc.fuse(hidden, left_on=True, right_on=False)
    bilateral, _, _ = cc.fuse(hidden, left_on=True, right_on=True)

    assert cc.fires == 2
    assert bilateral != unilateral
    assert cc.last_attn_lr
    assert cc.last_attn_rl


def test_midbrain_fit_advances_steps_and_mutates_transformer_weights() -> None:
    midbrain = Midbrain()
    transformer = midbrain.transformer
    assert transformer is not None

    steps_before = transformer.steps
    weights_before = [row[:] for row in transformer.layers[0].Wq]

    midbrain.fit("plan tensor ttk lattice oracle")
    midbrain.fit("compile ttk hp dps recipe sim")

    assert transformer.steps > steps_before
    assert transformer.layers[0].Wq != weights_before


def test_teacher_contact_advances_lora_adapter_state() -> None:
    neo = JeevesCortex()
    neo.bind_hf("left")

    first = neo.contact("left", "plan tensor ttk")
    teacher_lm = neo.slots["left"].standin
    bank = teacher_lm.lora
    assert bank is not None
    first_adapter = bank.to_dict()

    second = neo.contact("left", "plan tensor lattice oracle")
    second_adapter = bank.to_dict()

    assert first["contacted"] == 1
    assert second["contacted"] == 1
    assert second["contacts"] > first["contacts"]
    assert first_adapter["steps"] > 0
    assert second_adapter["steps"] > first_adapter["steps"]
    assert second_adapter["energy"] > 0.0
    assert "left:lora" in neo.own.models


def test_sleep_replay_advances_both_neo_mouths() -> None:
    neo = JeevesCortex()
    neo.think("plan tensor ttk lattice")
    gelu_before = neo.transformer.steps
    rms_before = neo.neo_rms.steps

    result = neo.sleep_cycle(n=1)

    assert result["replays"] == 1
    assert neo.transformer.steps > gelu_before
    assert neo.neo_rms.steps > rms_before
    assert neo.sleep.cycles >= 1
    assert neo.sleep.replays >= 1


def test_sleep_state_roundtrips_non_default_values(tmp_path) -> None:
    neo = JeevesCortex()
    neo.sleep.record("persist-me", [0.125] * 8, slack=0.75)
    neo.sleep.cycles = 3
    neo.sleep.replays = 7
    neo.sleep.pruned = 2
    neo.sleep.hebb["left:right"] = 4.5
    expected = neo.sleep.snapshot()

    path = tmp_path / "cortex.json"
    neo.save(path)

    restored = JeevesCortex()
    result = restored.load(path)

    assert result["loaded"] >= 0
    assert restored.sleep.snapshot() == expected
    assert restored.sleep.cycles == 3
    assert restored.sleep.replays == 7
    assert restored.sleep.pruned == 2
    assert len(restored.sleep.buffer) == 1
    assert restored.sleep.buffer[0].stim == "persist-me"
    assert restored.sleep.hebb["left:right"] == 4.5
