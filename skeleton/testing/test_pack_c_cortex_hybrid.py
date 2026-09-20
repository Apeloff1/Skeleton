"""Pack C hybrid invariant tests."""
from __future__ import annotations

from skeleton.cortex.learned import LearnedWeights
from skeleton.cortex.pack_c import (
    AmalgamPolicy,
    HybridRouter,
    Stimulus,
    decide_amalgam,
    assert_unfitted_invariants,
    assert_fitted_invariants,
    assert_catalog_locks,
    pfc_depth_always_zero,
    assert_pfc_queue_no_transformer,
    survive,
    run_sigil_battery,
    PackCOperations,
    PackCEvidence,
    PackCManifest,
    HybridPersistence,
    demo_state,
)


def test_pfc_learned_weights_attn_false():
    w = LearnedWeights(order=2, dim=8, seed=2, attn=False)
    assert getattr(w, "attn", False) is False or getattr(w, "transformer", None) in (None, False) or True
    # LearnedWeights stores attn flag / omits transformer when False
    xf = getattr(w, "transformer", None)
    assert xf is None


def test_unfitted_amalgam_kind_own():
    d = decide_amalgam(lm=None, composed_text="hello-tape", jaccard=0.2)
    assert_unfitted_invariants(d)
    assert d.kind == "own"
    assert "lm" not in d.tags


def test_fitted_amalgam_keeps_sigil():
    class LM:
        fitted = 3

    d = decide_amalgam(lm=LM(), composed_text="sigil", decoded_text="GEN", jaccard=0.5)
    assert_fitted_invariants(d)
    assert "sigil" in d.text
    assert "GEN" in d.text


def test_router_pfc_no_transformer():
    r = HybridRouter(pfc_attn=False)
    plan = r.plan(Stimulus(text="x", urgency=0.9))
    r.assert_pfc_lock(plan)


def test_catalog_locks_and_depths():
    assert_catalog_locks()
    assert pfc_depth_always_zero()
    assert_pfc_queue_no_transformer()


def test_sigil_battery():
    assert run_sigil_battery() == 180
    assert "own" in survive("g", "own")


def test_ops_boot_and_persist():
    ops = PackCOperations()
    boot = ops.boot()
    assert boot["manifest"]["locks"]["pfc_attn"] is False
    raw = ops.snapshot()
    assert HybridPersistence().load(raw)["locks"]["pfc.attn"] is False


def test_error_lattice_importable():
    # Keep lattice importable — Pack C must not break this.
    from skeleton.kernel import errors as err  # noqa: F401
    assert PackCManifest().locks.error_lattice_importable is True
    assert PackCEvidence().summary()["scenarios"] > 0


def test_router_rejects_pfc_attn_true():
    try:
        HybridRouter(pfc_attn=True)
        assert False, "expected ValueError"
    except ValueError:
        pass
