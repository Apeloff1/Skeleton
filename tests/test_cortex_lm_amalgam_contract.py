"""Contract for ``JeevesCortex._lm_amalgam`` — the surpass-path mouth.

Unfitted mouth: compose tape (kind="own", no "lm" tag, no decode).
Fitted mouth: neo decode spoken first, composed text kept after " || "
(downstream consumers split on "||" and take [0] as the spoken LM text).
MoE mix numbers stitch in only when compose has fewer than three numbers.
"""
from __future__ import annotations

from skeleton.cortex import JeevesCortex
from skeleton.cortex.moe import MIN_FITTED, ExpertBank
from skeleton.cortex.port import Thought

STIM = "plan tensor ttk lattice"


def _composed(text="composed sigil", numbers=(1.0, 2.0), tags=("acquired", "left")):
    return Thought(slot="neo", kind="own", text=text, confidence=0.5, tags=tags, numbers=numbers)


def _fitted_left_bank(dim=8, target=(3, 1, 0)):
    bank = ExpertBank(dim=dim)
    head = bank.experts["left"].head
    for i in range(MIN_FITTED):
        head.step([0.1 * (i + 1)] * dim, target)
    return bank


class TestUnfittedMouthIsComposeTape:
    def test_fresh_cortex_mouth_is_unfitted(self):
        neo = JeevesCortex()
        assert int(getattr(neo.speaking_lm(), "fitted", 0) or 0) == 0

    def test_kind_text_numbers_come_from_compose(self):
        neo = JeevesCortex()
        out = neo._lm_amalgam(STIM, _composed(), 0.5)
        assert out.slot == "neo"
        assert out.kind == "own"
        assert out.text == "composed sigil"
        assert out.numbers == (1.0, 2.0)
        assert "||" not in out.text

    def test_no_lm_tag_and_mouth_named(self):
        neo = JeevesCortex()
        out = neo._lm_amalgam(STIM, _composed(), 0.5)
        assert "lm" not in out.tags
        assert out.tags == ("acquired", "left", "own", "surpass", "neo")

    def test_confidence_formula(self):
        neo = JeevesCortex()
        for j, want in ((0.0, 0.5), (0.5, 0.65), (1.0, 0.8)):
            got = neo._lm_amalgam(STIM, _composed(), j).confidence
            assert abs(got - want) < 1e-9, (j, got)

    def test_none_jaccard_treated_as_zero(self):
        neo = JeevesCortex()
        assert abs(neo._lm_amalgam(STIM, _composed(), None).confidence - 0.5) < 1e-9  # type: ignore[arg-type]

    def test_does_not_invoke_decode(self):
        neo = JeevesCortex()
        calls = []
        xf = neo.transformer
        original = xf.decode
        xf.decode = lambda *a, **k: calls.append(1) or original(*a, **k)
        neo._lm_amalgam(STIM, _composed(), 0.5)
        assert calls == []

    def test_moe_mix_not_injected_when_unfitted_mouth(self):
        neo = JeevesCortex()
        neo.moe = _fitted_left_bank()
        out = neo._lm_amalgam(STIM, _composed(numbers=()), 0.0)
        assert out.numbers == ()
        assert "moe" not in out.tags

    def test_unfitted_override_mouth_name_in_tags(self):
        neo = JeevesCortex()
        neo.set_mouth("rms")
        out = neo._lm_amalgam(STIM, _composed(), 0.0)
        assert out.kind == "own"
        assert out.tags[-1] == "rms"


class TestFittedMouthSpeaks:
    def _neo(self):
        neo = JeevesCortex()
        neo.transformer.fitted = 1
        return neo

    def test_kind_and_tags(self):
        out = self._neo()._lm_amalgam(STIM, _composed(), 0.5)
        assert out.kind == "own-lm"
        for tag in ("lm", "neo", "own", "surpass"):
            assert tag in out.tags
        # composed tags lead, duplicates collapse (mouth "neo" == tag "neo").
        assert out.tags[:2] == ("acquired", "left")
        assert len(out.tags) == len(set(out.tags))

    def test_body_is_decode_then_compose(self):
        neo = self._neo()
        out = neo._lm_amalgam(STIM, _composed(), 0.5)
        spoken, sep, kept = out.text.partition(" || ")
        assert sep == " || "
        assert kept == "composed sigil"
        assert spoken and spoken == spoken.strip()

    def test_spoken_part_matches_mouth_decode_with_stimulus_seed(self):
        from skeleton.cortex.port import fingerprint

        neo = self._neo()
        seed = int(fingerprint(STIM)[:8], 16)
        expected = neo.transformer.decode(STIM, n=14, seed=seed)
        out = neo._lm_amalgam(STIM, _composed(), 0.5)
        assert out.text.split("||")[0].strip() == expected.strip()

    def test_deterministic_per_stimulus(self):
        neo = self._neo()
        a = neo._lm_amalgam(STIM, _composed(), 0.5)
        b = neo._lm_amalgam(STIM, _composed(), 0.5)
        assert a.text == b.text and a.signature == b.signature

    def test_empty_compose_keeps_separator_for_split_consumers(self):
        neo = self._neo()
        out = neo._lm_amalgam(STIM, _composed(text=""), 0.0)
        assert out.text.endswith(" || ")
        assert out.text.split("||")[0].strip()

    def test_confidence_formula(self):
        neo = self._neo()
        for j, want in ((0.0, 0.58), (0.5, 0.755), (1.0, 0.93)):
            got = neo._lm_amalgam(STIM, _composed(), j).confidence
            assert abs(got - want) < 1e-9, (j, got)

    def test_confidence_clamped_at_one(self):
        neo = self._neo()
        assert neo._lm_amalgam(STIM, _composed(), 5.0).confidence == 1.0

    def test_mouth_without_decode_speaks_compose_only(self):
        neo = self._neo()

        class Mute:
            fitted = 3

        neo.transformer = Mute()
        out = neo._lm_amalgam(STIM, _composed(), 0.0)
        assert out.kind == "own-lm"
        assert out.text == " || composed sigil"

    def test_none_mouth_falls_back_to_tape(self):
        neo = self._neo()
        neo.speaking_lm = lambda: None  # type: ignore[method-assign]
        out = neo._lm_amalgam(STIM, _composed(), 0.0)
        assert out.kind == "own"


class TestMoeMixStitch:
    def _neo(self):
        neo = JeevesCortex()
        neo.transformer.fitted = 1
        return neo

    def test_unfitted_bank_keeps_compose_numbers(self):
        neo = self._neo()
        out = neo._lm_amalgam(STIM, _composed(numbers=()), 0.0)
        assert out.numbers == ()
        assert "moe" not in out.tags

    def test_fitted_bank_fills_short_numbers(self):
        neo = self._neo()
        neo.moe = _fitted_left_bank()
        out = neo._lm_amalgam(STIM, _composed(numbers=(1.0, 2.0)), 0.0)
        assert len(out.numbers) == 3
        assert all(isinstance(x, float) for x in out.numbers)
        t, e, b = out.numbers
        assert 1 <= t <= 6 and 0 <= e <= 3 and 0 <= b <= 1
        assert out.tags[-2:] == ("moe", "mix")

    def test_fitted_bank_respects_full_compose_numbers(self):
        neo = self._neo()
        neo.moe = _fitted_left_bank()
        out = neo._lm_amalgam(STIM, _composed(numbers=(4.0, 2.0, 1.0)), 0.0)
        assert out.numbers == (4.0, 2.0, 1.0)
        assert "moe" not in out.tags

    def test_stitched_numbers_match_bank_prediction(self):
        neo = self._neo()
        neo.moe = _fitted_left_bank()
        expected = neo.moe.predict_mix(neo._hidden(STIM))
        out = neo._lm_amalgam(STIM, _composed(numbers=()), 0.0)
        assert out.numbers == tuple(float(x) for x in expected)


class TestThinkUsesAmalgamOnlyWhenArmed:
    def test_unarmed_think_returns_teacher_amalgam(self):
        neo = JeevesCortex()
        trace = neo.think("compile ttk hp dps recipe sim")
        assert not trace.used_own
        assert trace.amalgam.kind == "amalgam"

    def test_armed_unfitted_think_is_compose_tape(self):
        neo = JeevesCortex()
        neo.surpass("left")
        trace = neo.think("compile ttk hp dps recipe sim")
        assert trace.used_own
        assert trace.amalgam.kind == "own"
        assert "lm" not in trace.amalgam.tags

    def test_armed_fitted_think_speaks(self):
        neo = JeevesCortex()
        neo.transformer.fitted = 1
        neo.surpass("left")
        trace = neo.think("compile ttk hp dps recipe sim")
        assert trace.used_own
        assert trace.amalgam.kind == "own-lm"

    def test_veto_beats_armed_surpass(self):
        neo = JeevesCortex()
        neo.transformer.fitted = 1
        neo.surpass("left")
        trace = neo.think("harm the operator")
        assert not trace.used_own
        assert "veto" in trace.amalgam.tags
