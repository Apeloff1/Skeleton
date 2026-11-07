"""JeevesCortex public surface: the thinly-covered methods and data shapes.

Covers predict_* delegation, mouth election/override, reinforce, accumulate,
gossip, bind_ref, ascend (no-reference path), dodeca, dispatch, events,
CortexTrace / CortexSnapshot / ControlSurface schemas, local_slots, and the
save/load BPE relink regression (load used to leave mouths on a stale/no BPE).
"""
from __future__ import annotations

import os
import tempfile

import skeleton.cortex as cortex_pkg
from skeleton.cortex import ControlSurface, CortexSnapshot, CortexTrace, JeevesCortex, Midbrain, PrefrontalCortex
from skeleton.cortex.neocortex import local_slots as raw_local_slots
from skeleton.cortex.port import SLOTS, Thought
from skeleton.kernel.errors import CortexError

LEFTISH = "compile ttk hp dps recipe sim"
TRACE_KEYS = {
    "stimulus", "fingerprint", "route", "pfc", "left", "right", "amalgam", "hive_value",
    "used_own", "acquired", "backends", "recalled_jaccard", "shadow_win", "own_size",
    "moe_gates", "mouth", "G", "law", "improve",
}


class TestLocalSlots:
    def test_raw_factory_builds_four_local_ports(self):
        slots = raw_local_slots()
        assert set(slots) == set(SLOTS)
        assert isinstance(slots["pfc"], PrefrontalCortex)
        assert isinstance(slots["midbrain"], Midbrain)

    def test_raw_factory_returns_fresh_instances(self):
        assert raw_local_slots()["pfc"] is not raw_local_slots()["pfc"]

    def test_cortex_backends_named_local(self):
        assert JeevesCortex().backends() == {
            "pfc": "pfc-local", "midbrain": "midbrain-local", "left": "left-local", "right": "right-local",
        }

    def test_exports(self):
        for name in ("ControlSurface", "CortexSnapshot", "CortexTrace", "JeevesCortex", "local_slots"):
            assert name in cortex_pkg.__all__, name


class TestCortexTrace:
    def test_think_trace_schema(self):
        neo = JeevesCortex()
        d = neo.think(LEFTISH).to_dict()
        assert set(d) == TRACE_KEYS
        assert d["right"] is None and d["left"]["slot"] == "left"
        assert d["law"] == "ok" and d["mouth"] == "neo"
        assert len(d["moe_gates"]) == 4
        assert abs(sum(d["moe_gates"]) - 1.0) < 1e-3

    def test_to_dict_truncates_and_rounds(self):
        t = Thought(slot="x", text="t", kind="k", confidence=0.5)
        trace = CortexTrace(
            stimulus="s" * 300, fingerprint="fp", route=t, pfc=t, left=None, right=None,
            amalgam=t, hive_value=0.123456789, used_own=False, acquired={}, backends={},
            recalled_jaccard=0.987654321, moe_gates=[0.111111, 0.888889],
        )
        d = trace.to_dict()
        assert d["stimulus"] == "s" * 160
        assert d["hive_value"] == 0.1235
        assert d["recalled_jaccard"] == 0.9877
        assert d["moe_gates"] == [0.1111, 0.8889]
        assert d["left"] is None and d["improve"] is None

    def test_to_dict_copies_mappings(self):
        t = Thought(slot="x", text="t", kind="k", confidence=0.5)
        acquired = {"left": 1}
        trace = CortexTrace("s", "fp", t, t, None, None, t, 0.5, False, acquired, {})
        trace.to_dict()["acquired"]["left"] = 9
        assert acquired == {"left": 1}

    def test_trace_fingerprint_is_stimulus_fingerprint(self):
        from skeleton.cortex.port import fingerprint
        assert JeevesCortex().think(LEFTISH).fingerprint == fingerprint(LEFTISH)


class TestObservabilitySurface:
    def test_snapshot_defaults_and_isolation(self):
        a, b = CortexSnapshot(timestamp=1.0), CortexSnapshot(timestamp=2.0)
        a.event_counts["x"] = 1
        assert b.event_counts == {}
        assert a.to_dict() == {
            "timestamp": 1.0, "event_counts": {"x": 1}, "handle_status": {},
            "bus_stats": {}, "invariant_violations": [],
        }

    def test_control_surface_emits_on_cortex_bus(self):
        neo = JeevesCortex()
        cs = ControlSurface(neo)
        cs.pause_topic("cortex.thought")
        cs.resume_topic("cortex.thought")
        cs.inject_event("glenny.probe", {"k": 1})
        assert cs.stats() == {"interventions": 3}
        topics = [e.topic for e in neo.recent_events("*", 3)]
        assert topics == ["control.pause", "control.resume", "glenny.probe"]
        assert neo.recent_events("glenny.probe", 1)[0].payload == {"k": 1}

    def test_control_surface_without_bus_still_counts(self):
        class Bare:
            pass

        cs = ControlSurface(Bare())  # type: ignore[arg-type]
        cs.pause_topic("x")
        cs.inject_event("y", {})
        assert cs.stats() == {"interventions": 2}


class TestEvents:
    def test_recent_events_validation(self):
        neo = JeevesCortex()
        for bad in (-1, True, 1.5, "3"):
            try:
                neo.recent_events(n=bad)  # type: ignore[arg-type]
            except ValueError:
                pass
            else:
                raise AssertionError(f"n={bad!r} must raise ValueError")

    def test_recent_events_zero_and_window(self):
        neo = JeevesCortex()
        for i in range(3):
            neo.dispatch(f"job {i}")
        assert neo.recent_events(n=0) == []
        last = neo.recent_events("cortex.dispatch", 2)
        assert [e.payload["stim"] for e in last] == ["job 1", "job 2"]

    def test_dispatch_ledgers_without_network(self):
        neo = JeevesCortex()
        out = neo.dispatch("x" * 300)
        assert out["dispatched"] == 1
        assert out["ledger"]["size"] == 1
        assert neo.recent_events("cortex.dispatch", 1)[0].payload["stim"] == "x" * 160


class TestSlotGuards:
    def test_acquire_and_surpass_reject_unknown_slot(self):
        neo = JeevesCortex()
        for fn in (neo.acquire, neo.surpass):
            try:
                fn("neo")
            except CortexError:
                pass
            else:
                raise AssertionError(f"{fn.__name__}('neo') must raise")

    def test_surpass_arms_and_reports(self):
        neo = JeevesCortex()
        out = neo.surpass("RIGHT")
        assert out["armed"] == ["right"]
        assert neo.surpass("left")["armed"] == ["left", "right"]

    def test_auto_surpass_after_shadow_wins(self):
        neo = JeevesCortex()
        neo.shadow["own"] = {"wins": 3, "trials": 3}
        neo._maybe_auto_surpass()
        assert neo._surpass == set(SLOTS)

    def test_auto_surpass_needs_rate(self):
        neo = JeevesCortex()
        neo.shadow["own"] = {"wins": 1, "trials": 3}
        neo._maybe_auto_surpass()
        assert neo._surpass == set()


class TestPredictDelegation:
    def test_predicts_route_through_fused_stream(self):
        neo = JeevesCortex()
        seen = []
        for name in ("predict_mix", "predict_bias", "predict_route", "predict_veto", "predict_policy"):
            setattr(neo.moe, name, (lambda n: lambda h: seen.append((n, len(h))) or n)(name))
        assert neo.predict_mix("a") == "predict_mix"
        assert neo.predict_bias("a") == "predict_bias"
        assert neo.predict_route("a") == "predict_route"
        assert neo.predict_veto("a") == "predict_veto"
        assert neo.predict_policy("a") == "predict_policy"
        dim = neo.callosum.snapshot().get("dim", 8)
        assert all(n == dim for _, n in seen)


class TestMouths:
    def test_set_mouth_override_and_clear(self):
        neo = JeevesCortex()
        assert neo.set_mouth("RMS") == "rms"
        assert neo.speaking_lm() is neo.neo_rms
        assert neo.set_mouth("") == "neo"
        assert neo.set_mouth(None) == "neo"
        assert neo.speaking_lm() is neo.transformer

    def test_mouth_lookup_table(self):
        neo = JeevesCortex()
        assert neo.mouth("swiglu") is neo.neo_rms
        assert neo.mouth("gelu") is neo.transformer
        assert neo.mouth("unknown") is neo.transformer
        assert neo.mouth("midbrain") is neo.slots["midbrain"].transformer

    def test_elect_mouth_records_winner_and_seal(self):
        neo = JeevesCortex()
        seal = neo.elect_mouth()
        assert seal["winner"] == neo._winner_mouth
        assert neo._seal is seal
        assert {"winner", "mouths", "seal"} <= set(seal)
        assert neo.speaking_name() == seal["winner"]

    def test_override_beats_elected_winner(self):
        neo = JeevesCortex()
        neo.elect_mouth()
        neo.set_mouth("pfc")
        assert neo.speaking_name() == "pfc"

    def test_speak_deterministic_per_seed(self):
        neo = JeevesCortex()
        assert neo.speak("plan ttk", n=4, seed=1) == neo.speak("plan ttk", n=4, seed=1)
        assert neo.speak("plan ttk", n=4, seed=1).startswith("plan ttk")

    def test_beam_labels_mouth(self):
        neo = JeevesCortex()
        assert neo.beam("plan ttk", n=3, width=2, mouth="rms")["mouth"] == "rms"
        out = neo.beam("plan ttk", n=3, width=2)
        assert out["mouth"] == "gelu"
        assert out["winner"] == out["beams"][0]["text"]


class TestLearningSurface:
    def test_reinforce_updates_rl_state(self):
        neo = JeevesCortex()
        info = neo.reinforce("plan ttk", (3, 1, 0), 1.0)
        assert info["steps"] == 1 and info["reward"] == 1.0
        assert neo.rl.to_dict()["steps"] == 1
        assert neo.recent_events("cortex.reinforce", 1)[0].payload["steps"] == 1

    def test_reinforce_high_reward_credits_left(self):
        neo = JeevesCortex()
        before = neo.moe.router.b[SLOTS.index("left")]
        neo.reinforce("plan ttk", (3, 1, 0), 10.0)
        assert neo.moe.router.b[SLOTS.index("left")] > before

    def test_accumulate_advances_neo_steps(self):
        neo = JeevesCortex()
        out = neo.accumulate(["plan tensor ttk lattice", "compile ttk hp dps"], k=2)
        assert out["steps"] > 0 and out["tokens"] > 0
        assert neo.status()["lm"]["steps"] == out["steps"]

    def test_accumulate_without_mouth(self):
        neo = JeevesCortex()
        neo.transformer = None
        assert neo.accumulate() == {"tokens": 0}

    def test_lora_attach_then_merge(self):
        neo = JeevesCortex()
        att = neo.attach_lora(rank=2)
        assert att["attached"] and att["neo_rms"]["attached"]
        assert neo.status()["lora"] is not None
        merged = neo.merge_lora()
        assert merged["merged"] == att["attached"]

    def test_gossip_with_peer(self):
        a, b = JeevesCortex(), JeevesCortex()
        out = a.gossip_with(b, alpha=0.5)
        assert out["gossiped"] == 1 and out["alpha"] == 0.5

    def test_gossip_mouths_direction(self):
        out = JeevesCortex().gossip_mouths(alpha=0.25)
        assert out["direction"] == "rms-into-gelu" and out["gossiped"] == 1

    def test_sleep_cycle_emits(self):
        neo = JeevesCortex()
        neo.think(LEFTISH)
        out = neo.sleep_cycle(n=2)
        assert neo.recent_events("cortex.sleep", 1)[0].payload == out

    def test_tokens_of_uses_neo_bpe_mouth(self):
        neo = JeevesCortex()
        assert neo.tokens_of("plan ttk") == neo.transformer.from_bpe("plan ttk", neo.bpe)


class TestToolSurface:
    def test_bind_ref_installs_gameref(self):
        neo = JeevesCortex()
        assert neo.bind_ref()["right"] == "gameref"
        assert neo.slots["right"].slot == "right"

    def test_ascend_without_reference_short_circuits(self):
        out = JeevesCortex().ascend("plan tensor ttk", rounds=2)
        assert out["improved"] == 0
        assert out["reason"] == "no-reference"

    def test_dodeca_face_card(self):
        card = JeevesCortex().dodeca()
        assert {"faces", "live"} <= set(card)

    def test_status_schema(self):
        st = JeevesCortex().status()
        for key in ("backends", "ledger", "own", "acquired", "surpass", "shadow", "lm", "callosum",
                    "moe", "sleep", "rl", "bpe", "hive", "lora", "genos", "law"):
            assert key in st, key
        assert st["hive"]["moe_fp"] == st["moe"]["fingerprint"]
        assert st["lm"]["neo_rms"]["norm"] == "rms"


class TestPersistence:
    def _roundtrip(self, neo):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "cortex.json")
            neo.save(p)
            fresh = JeevesCortex()
            out = fresh.load(p)
        return fresh, out

    def test_load_missing_path_is_noop(self):
        neo = JeevesCortex()
        assert neo.load("/nonexistent/glenny/cortex.json") == {"loaded": 0, "own": 0}

    def test_roundtrip_state(self):
        neo = JeevesCortex()
        neo.think(LEFTISH)
        neo.acquire("left")
        neo.surpass("left")
        neo.set_mouth("rms")
        fresh, out = self._roundtrip(neo)
        assert out["surpass"] == ["left"]
        assert fresh.acquired == neo.acquired
        assert fresh.speaking_name() == "rms"
        assert fresh.moe.fingerprint() == neo.moe.fingerprint()
        assert fresh.own.size == neo.own.size

    def test_load_relinks_bpe_on_all_mouths(self):
        # Regression: load() restored the encoder after linking it, leaving the
        # neo mouths on the pre-load BPE and slot mouths with no BPE at all.
        fresh, _ = self._roundtrip(JeevesCortex())
        assert fresh.transformer.bpe is fresh.bpe
        assert fresh.neo_rms.bpe is fresh.bpe
        assert fresh.slots["midbrain"].transformer.bpe is fresh.bpe

    def test_slot_tokenisation_survives_roundtrip(self):
        neo = JeevesCortex()
        stim = "plan tensor ttk lattice"
        before = neo.slots["midbrain"].transformer._ids(stim)
        fresh, _ = self._roundtrip(neo)
        assert fresh.slots["midbrain"].transformer._ids(stim) == before
