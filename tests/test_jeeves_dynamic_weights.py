"""Adaptive and reactive banks sit beside live transformer weights and shadow trials."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from skeleton.cortex import AdaptiveWeights, DynamicWeightState, JeevesCortex, ReactiveWeights
from skeleton.cortex.transformer import TinyTransformer


def _l2(left, right) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right)) ** 0.5


def _digest(payload) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_weight_inventory_names_all_four_banks():
    neo = JeevesCortex()
    inventory = neo.weight_inventory()
    assert inventory["kind"] == "jeeves-weight-inventory"
    assert set(inventory) >= {"weights", "shadow_weights", "adaptive_weights", "reactive_weights"}
    assert inventory["weights"]["owner"] == "transformer"
    assert inventory["weights"]["dim"] == neo.transformer.dim
    assert inventory["weights"]["steps"] == neo.transformer.steps
    assert inventory["weights"]["fitted"] == neo.transformer.fitted
    assert "slots" in inventory["shadow_weights"]
    assert "trials" in inventory["shadow_weights"]
    assert inventory["adaptive_weights"]["kind"] == "adaptive-weights"
    assert inventory["reactive_weights"]["kind"] == "reactive-weights"
    assert neo.status()["dynamic_weights"]["kind"] == "dynamic-weights"


def test_step_updates_dynamic_banks_without_touching_transformer():
    neo = JeevesCortex()
    embeddings = copy.deepcopy(neo.transformer.E)
    steps = neo.transformer.steps
    stimulus = "soulslike ttk elite"
    ids = neo.transformer._ids(stimulus)
    assert len(ids) >= 2
    reactive_before = neo.dynamic_weights.reactive.norm()
    stepped = neo.step_dynamic_weights(stimulus)
    assert stepped["kind"] == "dynamic-weight-step"
    assert stepped["pairs"] == len(ids) - 1
    assert neo.dynamic_weights.adaptive.steps == len(ids) - 1
    assert neo.dynamic_weights.reactive.norm() > reactive_before
    assert neo.transformer.E == embeddings
    assert neo.transformer.steps == steps
    decayed = neo.dynamic_weights.reactive.norm()
    neo.dynamic_weights.reactive.decay_once()
    assert neo.dynamic_weights.reactive.norm() < decayed

    lone = neo.transformer._ids("soulslike")
    assert lone == [lone[0]]
    assert len(lone) == 1
    adaptive_steps = neo.dynamic_weights.adaptive.steps
    writes = neo.dynamic_weights.reactive.writes
    single = neo.step_dynamic_weights("soulslike")
    assert single["pairs"] == 0
    assert neo.dynamic_weights.adaptive.steps == adaptive_steps
    assert neo.dynamic_weights.reactive.writes == writes + 1
    assert neo.transformer.E == embeddings
    assert neo.transformer.steps == steps


def test_nine_adaptive_steps_reduce_error_and_snapshot_roundtrips():
    weights = AdaptiveWeights(dim=4)
    for k in range(4):
        for j in range(4):
            assert weights.A[k][j] == (0.02 if j % 4 == k else 0.0)
    assert all(value == 0.0 for row in weights.B for value in row)
    assert weights.bias == [0.0, 0.0, 0.0, 0.0]
    hidden = [0.4, -0.2, 0.7, 0.1]
    target = [-0.3, 0.5, 0.1, -0.4]
    initial = _l2(weights.predict(hidden), target)
    for _ in range(9):
        weights.step(hidden, target)
    assert weights.steps == 9
    assert weights.last_error < initial
    for row in weights.A + weights.B:
        assert all(abs(value) <= 0.25 for value in row)
    assert all(abs(value) <= 0.25 for value in weights.bias)
    snap = weights.snapshot()
    restored = AdaptiveWeights(dim=4)
    restored.restore(snap)
    assert restored.snapshot() == snap
    report = restored.report()
    assert report["kind"] == "adaptive-weights"
    assert report["dim"] == 4
    assert report["rank"] == 4
    assert report["steps"] == 9
    assert report["digest"] == _digest(snap)
    assert report["bias_norm"] == pytest.approx(sum(v * v for v in restored.bias) ** 0.5)
    reactive = ReactiveWeights(dim=4, decay=0.5, eta=2.0)
    reactive.write([3.0, 0.0, 0.0, 0.0])
    assert reactive.M[0][0] == pytest.approx(1.0)
    assert reactive.read([4.0, 0.0, 0.0, 0.0])[0] == pytest.approx(1.0)
    reactive_report = reactive.report()
    assert reactive_report["kind"] == "reactive-weights"
    assert reactive_report["writes"] == 1
    assert reactive_report["decay"] == 0.5
    assert reactive_report["digest"] == _digest(reactive.snapshot())


def test_speak_dynamic_keeps_adaptive_transformer_and_shadow():
    neo = JeevesCortex()
    neo.step_dynamic_weights("soulslike ttk elite")
    adaptive_steps = neo.dynamic_weights.adaptive.steps
    transformer_steps = neo.transformer.steps
    embeddings = copy.deepcopy(neo.transformer.E)
    shadow = copy.deepcopy(neo.shadow)
    spoken = neo.speak_dynamic("soulslike ttk", n=3, seed=0)
    assert spoken["kind"] == "dynamic-speak"
    assert len(spoken["token_ids"]) == 3
    assert spoken["text"]
    assert spoken["adaptive_steps"] == adaptive_steps
    assert spoken["reactive_writes"] == 3
    assert spoken["weights_unchanged"] == transformer_steps
    assert neo.dynamic_weights.adaptive.steps == adaptive_steps
    assert neo.transformer.steps == transformer_steps
    assert neo.transformer.E == embeddings
    assert neo.shadow == shadow


def test_save_load_restores_dynamic_snapshot(tmp_path: Path):
    neo = JeevesCortex()
    neo.step_dynamic_weights("soulslike ttk elite")
    neo.dynamic_weights.reactive.write(neo._read_embedding(neo.transformer._ids("elite")[0]))
    before = neo.dynamic_weights.snapshot()
    path = tmp_path / "jeeves.json"
    neo.save(path)
    fresh = JeevesCortex()
    dim = fresh.transformer.dim
    fresh.dynamic_weights.adaptive.step([0.1] * dim, [-0.1] * dim)
    assert fresh.dynamic_weights.snapshot() != before
    fresh.load(path)
    assert fresh.dynamic_weights.snapshot() == before
    assert fresh.status()["dynamic_weights"]["digest"] == neo.dynamic_weights.report()["digest"]

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["dynamic_weights"]["dim"] = 4
    skipped = tmp_path / "skipped.json"
    skipped.write_text(json.dumps(raw), encoding="utf-8")
    skipped_neo = JeevesCortex()
    skipped_neo.load(skipped)
    assert skipped_neo.dynamic_weights.dim == skipped_neo.transformer.dim
    assert skipped_neo.dynamic_weights.adaptive.steps == 0

    small = TinyTransformer(vocab=["alpha", "beta"], dim=4, ctx=4, seed=3, n_heads=1, n_layers=1, d_ff=8)
    state = DynamicWeightState(4)
    state.adaptive.step([0.2, -0.1, 0.4, 0.3], [0.0, 0.2, -0.2, 0.1])
    state.reactive.write([0.2, -0.1, 0.4, 0.3])
    rebuilt = json.loads(path.read_text(encoding="utf-8"))
    rebuilt["transformer"] = small.snapshot()
    rebuilt["dynamic_weights"] = state.snapshot()
    resized = tmp_path / "resized.json"
    resized.write_text(json.dumps(rebuilt), encoding="utf-8")
    resized_neo = JeevesCortex()
    resized_neo.load(resized)
    assert resized_neo.transformer.dim == 4
    assert resized_neo.dynamic_weights.dim == 4
    assert resized_neo.dynamic_weights.snapshot() == state.snapshot()


def test_modulate_caps_residual_l2_and_logit_bias_uses_it():
    state = DynamicWeightState(4)
    for row in state.reactive.M:
        for index in range(4):
            row[index] = 1.0
    hidden = [1.0, 1.0, 1.0, 1.0]
    modulated = state.modulate(hidden)
    residual = [modulated[i] - hidden[i] for i in range(4)]
    hidden_norm = _l2(hidden, [0.0, 0.0, 0.0, 0.0])
    residual_norm = _l2(residual, [0.0, 0.0, 0.0, 0.0])
    assert residual_norm == pytest.approx(0.5 * hidden_norm)
    embeddings = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
    bias = state.logit_bias(hidden, embeddings)
    assert bias == pytest.approx([
        sum(a * b for a, b in zip(residual, row)) for row in embeddings
    ])


def test_rejects_bad_dimensions_and_nonfinite_inputs():
    with pytest.raises(ValueError):
        AdaptiveWeights(0)
    with pytest.raises(ValueError):
        AdaptiveWeights(4097)
    with pytest.raises(ValueError):
        AdaptiveWeights(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        AdaptiveWeights(4.0)  # type: ignore[arg-type]
    weights = AdaptiveWeights(4)
    with pytest.raises(ValueError):
        weights.step([1.0, 0.0, 0.0, float("nan")], [0.0, 0.0, 0.0, 0.0])
    with pytest.raises(ValueError):
        weights.step([1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0])
    reactive = ReactiveWeights(4)
    with pytest.raises(ValueError):
        reactive.write([float("inf"), 0.0, 0.0, 0.0])
    state = DynamicWeightState(4)
    with pytest.raises(ValueError):
        state.modulate([0.0, 0.0, float("-inf"), 0.0])
    with pytest.raises(ValueError):
        state.logit_bias([0.0, 1.0], [[0.0, 1.0]])


def test_runtime_mirror_matches_canonical_cortex_files():
    root = Path(__file__).resolve().parents[1]
    for name in ("dynamic_weights.py", "neocortex.py", "__init__.py"):
        canonical = (root / "skeleton" / "cortex" / name).read_bytes()
        mirror = (root / "skeleton" / "ai" / "runtime" / "cortex" / name).read_bytes()
        assert canonical == mirror
