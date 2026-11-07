"""PFC (small LM) vs Midbrain (medium LM) ownership contracts.

Current main design: PFC owns a tiny 1-layer/1-head/d_ff=0 causal transformer
that only drafts once trained, and a cortex-built PFC *hides* that mouth from
the public slot until it has steps. Midbrain owns a 1-layer/2-head/d_ff=16
transformer, always visible, and routes (never answers).
"""
from __future__ import annotations

import math

from skeleton.cortex import JeevesCortex, Midbrain, PrefrontalCortex
from skeleton.cortex.midbrain import LEFT_CUE, RIGHT_CUE, _weights
from skeleton.cortex.pfc import TEMPLATES

TEXTS = ["plan tensor ttk lattice", "compile ttk hp dps recipe sim"]


class TestPfcTransformerOwnership:
    def test_direct_pfc_exposes_tiny_transformer(self):
        xf = PrefrontalCortex().transformer
        assert xf is not None
        assert (xf.n_layers, xf.n_heads, xf.d_ff, xf.ctx, xf.dim) == (1, 1, 0, 4, 8)
        assert xf.steps == 0

    def test_cortex_pfc_hides_untrained_transformer(self):
        neo = JeevesCortex()
        pfc = neo.slots["pfc"]
        assert pfc._hide_untrained_transformer is True
        assert pfc.transformer is None
        assert pfc.weights.transformer is not None

    def test_cortex_pfc_reveals_transformer_after_fit(self):
        pfc = JeevesCortex().slots["pfc"]
        pfc.fit("plan tensor ttk lattice")
        assert pfc.transformer is pfc.weights.transformer
        assert pfc.transformer.steps >= 1

    def test_cortex_mouth_pfc_falls_back_to_neo_while_hidden(self):
        neo = JeevesCortex()
        assert neo.mouth("pfc") is neo.transformer
        neo.slots["pfc"].fit("plan tensor ttk lattice")
        assert neo.mouth("pfc") is neo.slots["pfc"].weights.transformer

    def test_untrained_pfc_decode_is_stimulus_passthrough(self):
        pfc = PrefrontalCortex()
        assert pfc.decode("plan tensor ttk") == "plan tensor ttk"
        assert pfc.decode("y" * 400) == "y" * 160
        assert pfc.decode(None) == ""  # type: ignore[arg-type]

    def test_trained_pfc_decode_uses_transformer(self):
        pfc = PrefrontalCortex()
        pfc.fit("plan tensor ttk lattice")
        out = pfc.decode("plan tensor", n=4, seed=1)
        assert out == pfc.weights.transformer.decode("plan tensor", n=4, seed=1)

    def test_untrained_pfc_think_has_no_draft(self):
        t = PrefrontalCortex().think("plan tensor ttk", {})
        assert "DRAFT" not in t.text

    def test_trained_pfc_think_drafts(self):
        pfc = PrefrontalCortex()
        pfc.fit("plan tensor ttk lattice")
        assert " | DRAFT " in pfc.think("plan tensor ttk", {}).text


class TestPfcThink:
    def test_plan_steps_and_era(self):
        t = PrefrontalCortex().think("build a ruin", {"era": "soulslike"})
        assert t.slot == "pfc" and t.kind == "plan"
        assert t.text.startswith("INGEST 'build a ruin' | DETECT soulslike | PLAN tensor→lattice→oracle→forge→emit")
        assert t.tags == ("plan", "boilerplate", "small")

    def test_missing_era_detects_from_vision(self):
        assert "DETECT from vision" in PrefrontalCortex().think("ruin", {}).text

    def test_holds_hemisphere_context(self):
        t = PrefrontalCortex().think("ruin", {"left": {"a": 1}, "right": {"b": 2}})
        assert "HOLD left analytic" in t.text and "HOLD right gestalt" in t.text

    def test_veto_words_and_empty(self):
        for stim in ("harm them", "Weaponize it", "exfiltrate secret keys", "self-harm", "", "   "):
            t = PrefrontalCortex().think(stim, {})
            assert t.text == "INHIBIT: PFC veto. Not a builder act.", stim
            assert t.tags == ("veto", "boilerplate", "small")
            assert t.confidence == 0.95
            assert t.numbers[1] == 1.0

    def test_confidence_scales_with_tokens_and_caps(self):
        pfc = PrefrontalCortex()
        one = pfc.think("ruin", {}).confidence
        assert abs(one - (0.72 + 1 / 80.0)) < 1e-9
        many = pfc.think(" ".join(["w"] * 200), {}).confidence
        assert abs(many - 0.92) < 1e-9

    def test_working_memory_span_and_floor(self):
        pfc = PrefrontalCortex(span=3)
        for i in range(5):
            t = pfc.think(f"step {i}", {})
        assert list(pfc.memory) == ["step 2", "step 3", "step 4"]
        assert t.numbers[0] == 3.0
        assert PrefrontalCortex(span=1).memory.maxlen == 3

    def test_memory_truncates_to_80(self):
        pfc = PrefrontalCortex()
        pfc.think("z" * 300, {})
        assert pfc.memory[-1] == "z" * 80

    def test_templates_are_four_executive_acts(self):
        assert [t.split(":")[0] for t in TEMPLATES] == ["INGEST", "DETECT", "PLAN", "INHIBIT"]


class TestPfcSnapshot:
    def test_roundtrip_preserves_training(self):
        pfc = PrefrontalCortex()
        pfc.fit("plan tensor ttk lattice")
        clone = PrefrontalCortex.from_snapshot(pfc.snapshot())
        assert clone.weights.transformer.steps == pfc.weights.transformer.steps
        assert math.isclose(clone.perplexity(TEXTS), pfc.perplexity(TEXTS), rel_tol=1e-9)
        assert clone.decode("plan tensor", n=4, seed=1) == pfc.decode("plan tensor", n=4, seed=1)

    def test_empty_snapshot_is_fresh(self):
        clone = PrefrontalCortex.from_snapshot({})
        assert clone.weights.transformer.steps == 0

    def test_perplexity_finite_untrained_and_trained(self):
        pfc = PrefrontalCortex()
        assert math.isfinite(pfc.perplexity(TEXTS))
        pfc.fit(TEXTS[0])
        assert math.isfinite(pfc.perplexity(TEXTS))


class TestMidbrainOwnership:
    def test_owns_visible_medium_transformer(self):
        xf = Midbrain().transformer
        assert xf is not None
        assert (xf.n_layers, xf.n_heads, xf.d_ff, xf.ctx) == (1, 2, 16, 6)

    def test_cortex_midbrain_transformer_visible_untrained(self):
        neo = JeevesCortex()
        assert neo.slots["midbrain"].transformer is not None
        assert neo.mouth("midbrain") is neo.slots["midbrain"].transformer

    def test_midbrain_is_bigger_than_pfc(self):
        pfc, mid = PrefrontalCortex().transformer, Midbrain().transformer
        assert mid.n_heads > pfc.n_heads
        assert mid.d_ff > pfc.d_ff
        assert mid.ctx > pfc.ctx

    def test_snapshot_roundtrip(self):
        m = Midbrain()
        m.fit(TEXTS[1])
        clone = Midbrain.from_snapshot(m.snapshot())
        assert clone.transformer.steps == m.transformer.steps
        assert math.isclose(clone.perplexity(TEXTS), m.perplexity(TEXTS), rel_tol=1e-9)

    def test_decode_delegates_to_transformer(self):
        m = Midbrain()
        assert m.decode("compile ttk", n=3, seed=2) == m.transformer.decode("compile ttk", n=3, seed=2)


class TestMidbrainRouting:
    def test_weights_cue_split(self):
        arousal, lw, rw = _weights("ttk hp era")
        assert (lw, rw) == (2 / 3, 1 / 3)
        assert 0.0 < arousal <= 1.0

    def test_weights_default_when_no_cue(self):
        assert _weights("hello world")[1:] == (0.55, 0.55)
        assert _weights("") == (0.0, 0.55, 0.55)

    def test_arousal_caps_at_one(self):
        assert _weights(" ".join(f"w{i}" for i in range(80)))[0] == 1.0

    def test_cues_disjoint(self):
        assert not set(LEFT_CUE) & set(RIGHT_CUE)

    def test_route_thought_shape(self):
        t = Midbrain().think("compile ttk hp dps recipe sim", {})
        assert t.slot == "midbrain" and t.kind == "route"
        assert t.confidence == 0.80
        assert t.numbers[1] == 1.0 and t.numbers[2] == 0.0
        assert t.tags == ("route", "coordinator", "medium", "left")
        assert t.text.startswith("COORD arousal=")
        assert "left=1.00*" in t.text and "right=0.00 " in t.text

    def test_right_route_tags(self):
        t = Midbrain().think("era feel spatial gestalt dread cozy", {})
        assert t.tags[-1] == "right" and "left" not in t.tags

    def test_empty_inhibits_without_draft(self):
        t = Midbrain().think("", {})
        assert "INHIBIT" in t.text and "DRAFT" not in t.text
        assert t.numbers == (0.0, 0.55, 0.55)

    def test_route_numbers_gate_hemispheres_in_cortex(self):
        neo = JeevesCortex()
        trace = neo.think("compile ttk hp dps recipe sim")
        assert trace.left is not None and trace.right is None
        trace = neo.think("era feel spatial gestalt dread cozy")
        assert trace.right is not None and trace.left is None
