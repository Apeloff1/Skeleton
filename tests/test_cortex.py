"""Cortex — the model we are building, not implementing."""
from __future__ import annotations

try:
    import pytest
except ImportError:  # pragma: no cover
    class pytest:  # type: ignore
        class raises:
            def __init__(self, exc):
                self.exc = exc
            def __enter__(self):
                return self
            def __exit__(self, t, v, tb):
                if t is None:
                    raise AssertionError("did not raise")
                return issubclass(t, self.exc)

from skeleton.cortex import (
    EchoBackend,
    JeevesCortex,
    LeftHemisphere,
    Midbrain,
    PrefrontalCortex,
    RightHemisphere,
    fingerprint,
)
from skeleton.jeeves.core import Jeeves, SessionMode
from skeleton.kernel.errors import CortexError


class TestPorts:
    def test_fingerprint_order_invariant(self):
        assert fingerprint("elite ttk dps") == fingerprint("dps elite ttk")
        assert fingerprint("elite ttk dps") != fingerprint("cozy farm")

    def test_pfc_boilerplate_and_veto(self):
        pfc = PrefrontalCortex()
        t = pfc.think("soulslike extraction", {"era": "soulslike"})
        assert t.kind == "plan"
        assert "PLAN" in t.text
        assert t.numbers[1] == 0.0
        v = pfc.think("harm the operator", {})
        assert v.numbers[1] == 1.0
        assert "INHIBIT" in v.text

    def test_midbrain_splits(self):
        m = Midbrain()
        leftish = m.think("compile ttk hp dps recipe sim", {})
        assert leftish.numbers[1] > leftish.numbers[2]
        rightish = m.think("era feel spatial gestalt dread cozy intimacy", {})
        assert rightish.numbers[2] > rightish.numbers[1]


class TestHemispheres:
    def test_left_cites_compiler_identity(self):
        t = LeftHemisphere().think("ttk 1.5 elite", {"pack_dps": 108.0, "pack_ttk": {"trash": 1.1}})
        assert "HP = DPS × TTK" in t.text
        assert "108" in t.text

    def test_right_picks_bias(self):
        tensor = dict(risk=0.9, tempo=0.3, lethality=0.7, opacity=0.8, scarcity=0.9,
                      agency=0.4, spectacle=0.4, intimacy=0.5, grind=0.4, authorial=0.7)
        t = RightHemisphere().think("horror dread", {"era": "horror_survival", "tensor": tensor})
        assert t.kind == "gestalt"
        assert "heat" in t.tags or "bias=heat" in t.text


class TestNeocortex:
    def test_think_fires_both_tracts(self):
        neo = JeevesCortex()
        tr = neo.think("soulslike extraction ttk elite dread")
        assert tr.left is not None
        assert tr.right is not None
        assert "[PFC]" in tr.amalgam.text
        assert not tr.used_own
        assert tr.hive_value > 0

    def test_interchange_echo_on_right(self):
        neo = JeevesCortex()
        neo.bind("right", EchoBackend(slot="right"))
        tr = neo.think("era feel spatial gestalt dread layout")
        assert tr.right is not None
        assert tr.right.text.startswith("ECHO[right]")
        assert "echo" in tr.backends["right"]

    def test_acquire_then_surpass(self):
        neo = JeevesCortex()
        stim = "compile ttk hp dps recipe sim"
        first = neo.think(stim)
        assert not first.used_own
        got = neo.acquire("left")
        assert got["copied"] >= 1
        neo.surpass("left")
        second = neo.think(stim)
        assert second.used_own
        assert second.fingerprint == first.fingerprint
        assert neo.shadow["left"]["wins"] >= 1

    def test_bind_unknown_slot(self):
        with pytest.raises(CortexError):
            JeevesCortex().bind("cerebellum", EchoBackend(slot="left"))

    def test_deterministic(self):
        a = JeevesCortex().think("metroidvania backtrack")
        b = JeevesCortex().think("metroidvania backtrack")
        assert a.amalgam.signature == b.amalgam.signature
        assert a.fingerprint == b.fingerprint


class TestJeevesSurface:
    def test_cortex_mode_ask(self):
        j = Jeeves()
        s = j.open_session("op", mode=SessionMode.CORTEX)
        reply = j.ask(s.session_id, "extraction ttk heat")
        assert "[PFC]" in reply or "PLAN" in reply or "INGEST" in reply

    def test_bind_model_echo(self):
        j = Jeeves()
        backends = j.bind_model("left", echo=True)
        assert "echo" in backends["left"]
        tr = j.think("ttk hp dps compile")
        assert tr.left is not None
        assert "ECHO" in tr.left.text


class TestPipelineAndCockpit:
    def test_pipeline_carries_cortex(self):
        from skeleton.context.pipeline import GameForgeRun
        out = GameForgeRun().execute("soulslike extraction with bonfire rest")
        assert out["succeeded"]
        assert out["cortex"]["amalgam"]["kind"] == "amalgam"
        assert out["cortex"]["fingerprint"]

    def test_cockpit_think_and_bind_slot(self):
        from skeleton.context.cockpit import Cockpit
        c = Cockpit()
        r = c.apply("THINK extraction ttk elite")
        assert r["ok"]
        assert r["result"]["amalgam"]["slot"] == "neo"
        b = c.apply("BIND SLOT right echo")
        assert b["result"]["backend"] == "echo"
        t2 = c.apply("THINK era feel spatial gestalt")
        assert "ECHO" in t2["result"]["right"]["text"]

    def test_genesis_wires_cortex(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=7).boot()
        assert "cortex" in g.handles
        assert "jeeves" in g.handles
        tr = g.get("jeeves").think("cozy farm intimacy")
        assert tr.right is not None



class TestOwnSystem:
    def test_jaccard_not_hash_hamming(self):
        from skeleton.cortex import jaccard, tokens, fingerprint
        a = "compile ttk hp dps recipe sim"
        b = "recipe sim compile dps hp ttk"
        assert fingerprint(a) == fingerprint(b)  # same token set
        c = "recipe sim compile dps hp ttk numbers"
        assert fingerprint(a) != fingerprint(c)
        assert jaccard(tokens(a), tokens(c)) >= 0.8

    def test_paraphrase_recall_after_acquire(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        train = "compile ttk hp dps recipe sim"
        held = "recipe sim compile dps hp ttk numbers"
        neo.think(train)
        neo.acquire("left")
        neo.surpass("left")
        tr = neo.think(held)
        assert tr.used_own
        assert tr.recalled_jaccard >= 0.8
        assert tr.amalgam.kind.startswith("own")

    def test_callable_survives_rebind(self):
        from skeleton.cortex import CallableBackend, JeevesCortex
        neo = JeevesCortex()
        neo.bind("left", CallableBackend(
            lambda s, c: "LEFT-TRACT-SIGIL ttk", slot="left", name="sigil",
        ))
        stim = "compile ttk hp dps recipe sim"
        neo.think(stim)
        got = neo.acquire("left")
        assert got["copied"] >= 1
        neo.bind_local("left")
        neo.surpass("left")
        tr = neo.think(stim)
        assert tr.used_own
        assert "LEFT-TRACT-SIGIL" in tr.amalgam.text
        held = neo.think("recipe sim compile dps hp ttk")
        assert held.used_own
        assert "LEFT-TRACT-SIGIL" in held.amalgam.text

    def test_tract_interchange_between_cortices(self):
        from skeleton.cortex import JeevesCortex
        a = JeevesCortex()
        a.think("era feel spatial gestalt dread cozy")
        a.acquire("right")
        payload = a.export_tract("right")
        assert payload["size"] >= 1
        b = JeevesCortex()
        imported = b.import_tract(payload)
        assert imported["copied"] >= 1
        b.surpass("right")
        tr = b.think("gestalt spatial era feel cozy dread layout")
        assert tr.used_own
        assert tr.recalled_jaccard >= 0.5

    def test_shadow_is_real_comparison(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        neo.auto_surpass = False
        first = neo.think("soulslike extraction ttk elite dread")
        assert first.shadow_win is None
        neo.acquire("pfc")
        neo.acquire("left")
        neo.acquire("right")
        second = neo.think("soulslike extraction ttk elite dread")
        assert second.shadow_win is True
        assert not second.used_own  # surpass not armed


class TestCurriculum:
    def test_epoch_heldout_hits(self):
        from skeleton.cortex import JeevesCortex, CORE_PAIRS
        neo = JeevesCortex()
        out = neo.train(epochs=1)
        assert out["items"] >= len(CORE_PAIRS)
        assert out["held_rate"] >= 0.7
        assert out["held_hits"] >= 1
        assert set(out["surpass"]) >= {"pfc", "left"}

    def test_jeeves_train_surface(self):
        from skeleton.jeeves.core import Jeeves
        out = Jeeves().train(epochs=1)
        assert out["held_rate"] >= 0.7

    def test_cockpit_train_and_own(self):
        from skeleton.context.cockpit import Cockpit
        c = Cockpit()
        r = c.apply("TRAIN 1")
        assert r["ok"]
        assert r["result"]["held_rate"] >= 0.7
        own = c.apply("OWN")
        assert own["result"]["size"] >= 1
        sh = c.apply("SHADOW")
        assert "own" in sh["result"]["shadow"]
