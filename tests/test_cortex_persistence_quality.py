from __future__ import annotations

from skeleton.cortex import JeevesCortex


def test_cuda_request_contract_is_exact_even_when_hardware_degrades() -> None:
    neo = JeevesCortex()

    result = neo.to("cuda")

    assert result["requested"] == "cuda"
    assert result["cuda"] in {True, False}
    assert result["degraded"] is (not result["cuda"])
    if not result["cuda"]:
        assert result["actual"] == "cpu"
        assert neo.status()["lm"]["device"] == "cpu"


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
