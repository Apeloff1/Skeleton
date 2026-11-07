"""Mixture-of-Experts contracts: Router, Expert, ExpertBank (skeleton.cortex.moe).

predict_* stay silent (None) until the owning head has MIN_FITTED steps, then
return the head's typed prediction over the gated mix. Snapshots round-trip
the guts exactly; fingerprint is content-addressed over weights only.
"""
from __future__ import annotations

import math

from skeleton.cortex import JeevesCortex
from skeleton.cortex.moe import MIN_FITTED, Expert, ExpertBank, Router
from skeleton.cortex.own import BIASES
from skeleton.cortex.port import SLOTS

H = [0.3, -0.2, 0.1, 0.5, -0.4, 0.2, 0.0, 0.1]


def _train(head, target, n=MIN_FITTED, dim=8):
    for i in range(n):
        head.step([0.05 * (i + 1) * (1 if j % 2 else -1) for j in range(dim)], target)


class TestRouter:
    def test_gate_is_probability_simplex(self):
        g = Router(dim=8).gate(H)
        assert len(g) == 4
        assert all(0.0 < x < 1.0 for x in g)
        assert math.isclose(sum(g), 1.0, rel_tol=1e-9)

    def test_gate_pads_and_truncates_input(self):
        r = Router(dim=8)
        assert r.gate(H[:3]) == r.gate(H[:3] + [0.0] * 5)
        assert r.gate(H + [9.0, 9.0]) == r.gate(H)

    def test_zero_hidden_gates_uniform(self):
        g = Router(dim=8).gate([0.0] * 8)
        assert all(math.isclose(x, 0.25) for x in g)

    def test_credit_biases_toward_expert(self):
        r = Router(dim=8)
        before = r.gate([0.0] * 8)
        r.credit(2, lr=0.5)
        after = r.gate([0.0] * 8)
        assert after[2] > before[2]
        assert r.steps == 1 and r.b[2] == 0.5

    def test_credit_out_of_range_is_noop(self):
        r = Router(dim=8)
        r.credit(-1)
        r.credit(4)
        assert r.steps == 0 and r.b == [0.0] * 4

    def test_seed_determinism(self):
        assert Router(dim=8, seed=5).W == Router(dim=8, seed=5).W
        assert Router(dim=8, seed=5).W != Router(dim=8, seed=6).W

    def test_snapshot_roundtrip(self):
        r = Router(dim=8, seed=3)
        r.credit(1)
        clone = Router.from_snapshot(r.snapshot())
        assert clone.W == r.W and clone.b == r.b and clone.steps == 1
        assert clone.gate(H) == r.gate(H)

    def test_snapshot_is_a_copy(self):
        r = Router(dim=8)
        snap = r.snapshot()
        snap["W"][0][0] = 99.0
        assert r.W[0][0] != 99.0

    def test_from_empty_snapshot_defaults(self):
        r = Router.from_snapshot({})
        assert (r.dim, r.n, r.steps) == (8, 4, 0)


class TestExpert:
    def test_head_kind_by_slot(self):
        kinds = {s: Expert(s, 8).head.kind for s in SLOTS}
        assert kinds == {"pfc": "veto", "midbrain": "route", "left": "numeric", "right": "bias"}

    def test_only_pfc_has_policy_aux(self):
        assert Expert("pfc", 8).aux is not None and Expert("pfc", 8).aux.kind == "policy"
        for s in ("midbrain", "left", "right"):
            assert Expert(s, 8).aux is None

    def test_dim_floor_is_four(self):
        assert Expert("left", 2).dim == 4

    def test_project_is_bounded_residual(self):
        ex = Expert("left", 8)
        out = ex.project(H)
        assert len(out) == 8
        for v, o in zip(H, out):
            assert abs(o - v) < 1.0  # tanh residual is strictly bounded

    def test_project_zero_weights_is_identity(self):
        ex = Expert("left", 8)
        ex.W = [[0.0] * 8 for _ in range(8)]
        assert ex.project(H) == H

    def test_distill_reduces_loss_and_counts(self):
        ex = Expert("left", 8, seed=1)
        teacher = [0.9, -0.9, 0.5, 0.0, 0.2, -0.3, 0.4, 0.1]
        first = ex.distill(H, teacher, lr=0.2)
        for _ in range(30):
            last = ex.distill(H, teacher, lr=0.2)
        assert last < first
        assert ex.distills == 31

    def test_snapshot_roundtrip_including_heads(self):
        ex = Expert("pfc", 8, seed=4)
        _train(ex.head, 1.0, n=2)
        ex.acquired = 3
        clone = Expert.from_snapshot(ex.snapshot())
        assert clone.slot == "pfc" and clone.acquired == 3
        assert clone.W == ex.W and clone.b == ex.b
        assert clone.head.kind == "veto" and clone.head.fitted == 2
        assert clone.aux is not None
        assert clone.project(H) == ex.project(H)


class TestExpertBank:
    def test_four_experts_in_slot_order(self):
        bank = ExpertBank()
        assert list(bank.experts) == list(SLOTS)
        assert bank.router.n == len(SLOTS)

    def test_acquire_counts_and_unknown_slot(self):
        bank = ExpertBank()
        assert bank.acquire("LEFT") == 1
        assert bank.acquire("left") == 2
        assert bank.acquire("neo") == 0
        assert bank.acquire("") == 0

    def test_forward_is_gated_mix_of_projections(self):
        bank = ExpertBank(dim=8)
        mixed, gates = bank.forward(H)
        expect = [0.0] * 8
        for i, s in enumerate(SLOTS):
            p = bank.experts[s].project(H)
            for d in range(8):
                expect[d] += gates[i] * p[d]
        assert all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(mixed, expect))
        assert bank.forwards == 1

    def test_predicts_silent_until_min_fitted(self):
        bank = ExpertBank()
        for fn in (bank.predict_mix, bank.predict_bias, bank.predict_route, bank.predict_veto, bank.predict_policy):
            assert fn(H) is None
        assert bank.forwards == 0  # silent predicts never run forward

    def test_predict_mix_after_fit(self):
        bank = ExpertBank()
        _train(bank.experts["left"].head, (3, 1, 0), n=MIN_FITTED - 1)
        assert bank.predict_mix(H) is None
        _train(bank.experts["left"].head, (3, 1, 0), n=1)
        t, e, b = bank.predict_mix(H)
        assert isinstance(t, int) and 1 <= t <= 6 and 0 <= e <= 3 and b in (0, 1)

    def test_predict_bias_after_fit(self):
        bank = ExpertBank()
        _train(bank.experts["right"].head, "loot")
        assert bank.predict_bias(H) in BIASES

    def test_predict_route_after_fit(self):
        bank = ExpertBank()
        _train(bank.experts["midbrain"].head, (0.5, 1.0, 0.0))
        out = bank.predict_route(H)
        assert len(out) == 3 and all(isinstance(x, float) for x in out)

    def test_predict_veto_is_bool(self):
        bank = ExpertBank()
        _train(bank.experts["pfc"].head, 1.0)
        assert isinstance(bank.predict_veto(H), bool)

    def test_predict_policy_uses_aux_not_veto_head(self):
        bank = ExpertBank()
        _train(bank.experts["pfc"].head, 1.0)
        assert bank.predict_policy(H) is None
        _train(bank.experts["pfc"].aux, (1.0, 0.0))
        out = bank.predict_policy(H)
        assert len(out) == 2 and set(out) <= {0, 1}

    def test_credit_routes_to_router(self):
        bank = ExpertBank()
        bank.credit("right", lr=0.1)
        assert bank.router.b[SLOTS.index("right")] == 0.1
        bank.credit("neo")
        assert bank.router.steps == 1

    def test_fingerprint_content_addressed(self):
        a, b = ExpertBank(seed=7), ExpertBank(seed=7)
        assert a.fingerprint() == b.fingerprint()
        assert len(a.fingerprint()) == 16
        a.credit("left")
        assert a.fingerprint() != b.fingerprint()

    def test_fingerprint_ignores_counters(self):
        bank = ExpertBank()
        fp = bank.fingerprint()
        bank.forward(H)
        bank.acquire("left")
        assert bank.fingerprint() == fp

    def test_snapshot_roundtrip_preserves_fingerprint_and_predictions(self):
        bank = ExpertBank(seed=11)
        _train(bank.experts["left"].head, (2, 2, 1))
        bank.credit("left")
        bank.forward(H)
        clone = ExpertBank.from_snapshot(bank.snapshot())
        assert clone.fingerprint() == bank.fingerprint()
        assert clone.forwards == bank.forwards
        assert clone.predict_mix(H) == bank.predict_mix(H)

    def test_to_dict_schema(self):
        bank = ExpertBank()
        bank.acquire("pfc")
        d = bank.to_dict()
        assert set(d) == {"dim", "forwards", "fingerprint", "experts", "router_steps"}
        assert d["experts"]["pfc"] == {
            "acquired": 1, "distills": 0, "head_fitted": 0, "head_kind": "veto", "aux_fitted": 0,
        }
        assert d["experts"]["right"]["head_kind"] == "bias"


class TestCortexMoeWiring:
    def test_cortex_predicts_none_when_fresh(self):
        neo = JeevesCortex()
        for fn in (neo.predict_mix, neo.predict_bias, neo.predict_route, neo.predict_veto, neo.predict_policy):
            assert fn("plan ttk") is None

    def test_think_trains_heads_and_credits_router(self):
        neo = JeevesCortex()
        neo.think("compile ttk hp dps recipe sim")
        experts = neo.moe.to_dict()["experts"]
        assert experts["pfc"]["head_fitted"] == 1
        assert experts["midbrain"]["head_fitted"] == 1
        assert neo.moe.router.steps >= 3

    def test_cortex_predict_veto_after_repeated_think(self):
        neo = JeevesCortex()
        for _ in range(MIN_FITTED):
            neo.think("compile ttk hp dps recipe sim")
        assert isinstance(neo.predict_veto("compile ttk"), bool)
        assert neo.predict_route("compile ttk") is not None

    def test_acquire_stamps_expert(self):
        neo = JeevesCortex()
        out = neo.acquire("right")
        assert out["expert"] == 1
        assert neo.moe.experts["right"].acquired == 1

    def test_export_import_tract_carries_expert(self):
        src = JeevesCortex()
        _train(src.moe.experts["left"].head, (4, 2, 1))
        payload = src.export_tract("left")
        dst = JeevesCortex()
        dst.import_tract(payload)
        assert dst.moe.experts["left"].head.fitted == MIN_FITTED
        assert dst.moe.experts["left"].W == src.moe.experts["left"].W
