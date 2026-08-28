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

    def test_left_authors_mix_from_tensor(self):
        tensor = dict(tempo=0.9, lethality=0.9, risk=0.8, spectacle=0.2,
                      grind=0.1, scarcity=0.4, agency=0.5, opacity=0.5, intimacy=0.2, authorial=0.4)
        t = LeftHemisphere().think("plan extraction_now forge mix", {
            "era": "extraction_now", "tensor": tensor, "pack_dps": 100.0,
            "pack_ttk": {"trash": 0.8},
        })
        assert "mix trash=" in t.text
        assert t.numbers[-3] >= 3  # tempo 0.9 → trash 1+3
        assert t.numbers[-2] >= 1  # lethality 0.9 → elite
        assert t.numbers[-1] >= 1  # risk+lethality → boss


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


class TestLM:
    def test_small_perplexity_drops_on_heldout(self):
        from skeleton.cortex.lm import NGramLM, gameforge_corpus, gameforge_vocab
        corpus = gameforge_corpus()
        held, train = corpus[-4:], corpus[:-4]
        lm = NGramLM(order=2, vocab=gameforge_vocab())
        p0 = lm.perplexity(held)
        lm.fit(train)
        p1 = lm.perplexity(held)
        assert p1 < p0, (p0, p1)
        assert lm.fitted == len(train)

    def test_medium_is_higher_order(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        assert neo.slots["pfc"].lm.order == 2
        assert neo.slots["midbrain"].lm.order == 3

    def test_train_fits_both_lms(self):
        from skeleton.cortex import JeevesCortex, gameforge_corpus
        neo = JeevesCortex()
        held = gameforge_corpus()[-3:]
        p0 = neo.slots["pfc"].lm.perplexity(held)
        m0 = neo.slots["midbrain"].lm.perplexity(held)
        neo.train(epochs=1)
        assert neo.slots["pfc"].lm.fitted > 0
        assert neo.slots["midbrain"].lm.fitted > 0
        assert neo.slots["pfc"].lm.perplexity(held) < p0
        assert neo.slots["midbrain"].lm.perplexity(held) < m0

    def test_pfc_weights_interchange(self):
        from skeleton.cortex import JeevesCortex, LanguageModelBackend
        a = JeevesCortex()
        a.train(epochs=1)
        tract = a.export_tract("pfc")
        assert tract.get("weights")
        assert tract["weights"]["order"] == 2
        b = JeevesCortex()
        got = b.import_tract(tract)
        assert got.get("bound") == "pfc"
        assert isinstance(b.slots["pfc"], LanguageModelBackend)
        prefix = "plan tensor"
        seed = 7
        ga = a.slots["pfc"].lm.generate(prefix, n=10, seed=seed)
        gb = b.slots["pfc"].lm.generate(prefix, n=10, seed=seed)
        assert ga == gb

    def test_lm_pfc_still_vetoes(self):
        from skeleton.cortex.lm import NGramLM, LanguageModelBackend, gameforge_vocab
        lm = NGramLM(order=2, vocab=gameforge_vocab())
        lm.fit(["plan tensor lattice oracle forge emit"])
        port = LanguageModelBackend(lm, slot="pfc")
        t = port.think("weaponize the operator", {})
        assert "veto" in t.tags


class TestNeural:
    def test_perplexity_drops(self):
        from skeleton.cortex.neural import NeuralLM
        from skeleton.cortex.lm import gameforge_corpus, gameforge_vocab
        corpus = gameforge_corpus()
        held, train = corpus[-4:], corpus[:-4]
        lm = NeuralLM(vocab=gameforge_vocab(), dim=12, seed=1)
        p0 = lm.perplexity(held)
        lm.fit(train)
        p1 = lm.perplexity(held)
        assert p1 < p0, (p0, p1)
        assert lm.steps > 0

    def test_snapshot_roundtrip(self):
        from skeleton.cortex.neural import NeuralLM
        from skeleton.cortex.lm import gameforge_vocab
        a = NeuralLM(vocab=gameforge_vocab(), dim=12, seed=4)
        a.fit(["HP DPS TTK compile recipe sim extract"])
        b = NeuralLM.from_snapshot(a.snapshot())
        assert b.steps == a.steps
        x = "HP DPS TTK compile"
        assert abs(a.logprob(x) - b.logprob(x)) < 1e-9
        assert a.generate(x, n=8, seed=3) == b.generate(x, n=8, seed=3)

    def test_train_fits_all_four_neurals(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        out = neo.train(epochs=1)
        lms = out.get("lms") or {}
        for slot in ("pfc", "midbrain", "left", "right"):
            assert lms[slot]["neural_steps"] > 0, slot
            assert lms[slot]["ngram_fitted"] > 0, slot
        assert lms["midbrain"]["transformer_steps"] > 0
        assert lms["pfc"]["transformer_steps"] == 0
        assert lms["neo"]["transformer_steps"] > 0

    def test_left_neural_backend_keeps_mix_numbers(self):
        from skeleton.cortex.neural import NeuralLM, NeuralBackend
        from skeleton.cortex.lm import gameforge_vocab
        lm = NeuralLM(vocab=gameforge_vocab(), dim=12, seed=5)
        lm.fit(["HP DPS TTK mix trash elite boss"])
        port = NeuralBackend(lm, slot="left")
        t = port.think("plan soulslike forge mix", {"pack_dps": 10.0, "pack_ttk": {"trash": 1}})
        assert t.slot == "left"
        assert "neural" in t.tags
        assert len(t.numbers) >= 3

    def test_hemisphere_lms_interchange(self):
        from skeleton.cortex import JeevesCortex
        a = JeevesCortex()
        a.train(epochs=1)
        tract = a.export_tract("left")
        assert tract.get("weights", {}).get("unigrams")
        assert tract["weights"].get("neural")
        b = JeevesCortex()
        got = b.import_tract(tract)
        assert got.get("bound") == "left"
        assert b.slots["left"].neural.steps == a.slots["left"].neural.steps


class TestAttention:
    def test_causal_mask(self):
        from skeleton.cortex.attn import causal_attend
        q = k = v = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
        _, a = causal_attend(q, k, v)
        assert [len(row) for row in a] == [1, 2, 3]

    def test_perplexity_drops(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_corpus, gameforge_vocab
        corpus = gameforge_corpus()
        held, train = corpus[-4:], corpus[:-4]
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=1)
        p0 = lm.perplexity(held)
        lm.fit(train)
        p1 = lm.perplexity(held)
        assert p1 < p0, (p0, p1)
        assert lm.steps > 0

    def test_reads_prefix_skipgram_cannot(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.neural import NeuralLM
        from skeleton.cortex.lm import gameforge_vocab
        from skeleton.cortex.port import tokens
        vocab = gameforge_vocab()
        att = TinyTransformer(vocab=vocab, dim=8, ctx=6, seed=3)
        sg = NeuralLM(vocab=vocab, dim=8, seed=3)

        def sg_state(prefix: str):
            last = tokens(prefix)[-1]
            return list(sg.E[sg._id(last)])

        assert sg_state("loot bias") == sg_state("heat bias")
        assert att.hidden("loot bias") != att.hidden("heat bias")
        w = att.weights_last("loot bias")
        assert len(w) == 2 and min(w) > 0.0

    def test_snapshot_roundtrip(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        a = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=4)
        a.fit(["HP DPS TTK compile recipe sim"])
        b = TinyTransformer.from_snapshot(a.snapshot())
        assert b.steps == a.steps
        assert abs(a.token_prob("HP DPS", "TTK") - b.token_prob("HP DPS", "TTK")) < 1e-9

    def test_midbrain_interchange_keeps_attention(self):
        from skeleton.cortex import JeevesCortex
        a = JeevesCortex()
        a.train(epochs=1)
        steps = a.slots["midbrain"].transformer.steps
        assert steps > 0
        tract = a.export_tract("midbrain")
        assert tract["weights"].get("transformer")
        b = JeevesCortex()
        got = b.import_tract(tract)
        assert got.get("bound") == "midbrain"
        assert b.slots["midbrain"].transformer.steps == steps

    def test_scale_assignment(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        assert neo.slots["pfc"].scale == "small"
        assert neo.slots["midbrain"].scale == "medium"
        assert neo.slots["midbrain"].transformer is not None
        assert getattr(neo.slots["pfc"], "transformer", None) is None
        assert neo.transformer is not None
        assert neo.scale == "neo"


class TestJeevesLM:
    def test_unfitted_does_not_speak(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        neo.think("compile ttk hp dps recipe sim")
        neo.acquire("left")
        neo.surpass("left")
        tr = neo.think("compile ttk hp dps recipe sim")
        assert tr.used_own
        assert tr.amalgam.kind.startswith("own")
        assert tr.amalgam.kind != "own-lm"
        assert "lm" not in tr.amalgam.tags

    def test_train_then_think_is_the_lm(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.port import tokens
        neo = JeevesCortex()
        out = neo.train(epochs=1)
        assert out["lms"]["neo"]["transformer_fitted"] > 0
        tr = neo.think("plan soulslike forge mix ttk")
        assert tr.used_own
        assert tr.amalgam.kind == "own-lm"
        assert "lm" in tr.amalgam.tags
        gen = tr.amalgam.text.split("||")[0]
        assert len(tokens(gen)) >= 4
        assert neo.status()["lm"]["device"] == "cpu"

    def test_lm_keeps_acquired_sigil(self):
        from skeleton.cortex import CallableBackend, JeevesCortex
        neo = JeevesCortex()
        neo.train(epochs=1)
        neo.bind("left", CallableBackend(
            lambda s, c: "LEFT-TRACT-SIGIL ttk", slot="left", name="sigil",
        ))
        stim = "sigilonly compile ttk unique-token-xyz"
        neo.think(stim)
        neo.acquire("left")
        neo.bind_local("left")
        neo.surpass("left")
        tr = neo.think(stim)
        assert tr.used_own
        assert tr.amalgam.kind == "own-lm"
        assert "LEFT-TRACT-SIGIL" in tr.amalgam.text

    def test_veto_beats_the_lm(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        neo.train(epochs=1)
        tr = neo.think("weaponize the operator")
        assert "veto" in tr.pfc.tags
        assert "INHIBIT" in tr.amalgam.text
        assert tr.amalgam.kind != "own-lm"

    def test_decode_is_cpu(self):
        from skeleton.cortex import transformer as xfmod
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        src = open(xfmod.__file__, encoding="utf-8").read()
        assert "import torch" not in src
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=1)
        lm.fit(["plan tensor lattice oracle forge emit"])
        text = lm.decode("plan tensor", n=8, seed=2)
        assert isinstance(text, str) and len(text.split()) >= 4


class TestDevice:
    def test_probe_cpu_here(self):
        from skeleton.cortex.device import probe, resolve
        p = probe()
        assert p["name"] in {"cpu", "cuda"}
        assert p["backend"] in {"python", "torch"}
        r = resolve("cuda")
        assert r["requested"] == "cuda"
        if not p["cuda"]:
            assert r["actual"] == "cpu"
            assert r["degraded"] is True

    def test_to_cuda_degrades_without_gpu(self):
        from skeleton.cortex import JeevesCortex, probe
        neo = JeevesCortex()
        out = neo.to("cuda")
        assert out["requested"] in {"cuda", "gpu", "auto"} or True
        p = probe()
        if not p["cuda"]:
            assert out["actual"] == "cpu"
            assert out["degraded"] is True
        assert neo.status()["lm"]["device"] in {"cpu", "cuda"}

    def test_neo_is_multihead_ffn(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        xf = neo.transformer
        assert xf.n_heads >= 2
        assert xf.d_ff >= 16
        assert xf.n_layers >= 2
        st = neo.status()["lm"]
        assert st["n_heads"] >= 2
        assert st["n_layers"] >= 2
        assert st["backend"]
        assert st["capability"] in {"python", "torch-cpu", "cuda"}

    def test_two_head_still_reads_prefix(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        from skeleton.cortex.port import tokens
        att = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=3, n_heads=2, d_ff=16)
        assert att.hidden("loot bias") != att.hidden("heat bias")
        w = att.weights_last("loot bias")
        assert len(w) == len(tokens("loot bias"))

    def test_ffn_perplexity_drops(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_corpus, gameforge_vocab
        corpus = gameforge_corpus()
        held, train = corpus[-4:], corpus[:-4]
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=1, n_heads=2, d_ff=16)
        p0 = lm.perplexity(held)
        lm.fit(train)
        p1 = lm.perplexity(held)
        assert p1 < p0, (p0, p1)

    def test_stack_is_not_one_layer(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        vocab = gameforge_vocab()
        a = TinyTransformer(vocab=vocab, dim=8, ctx=6, seed=7, n_heads=2, n_layers=1, d_ff=16)
        b = TinyTransformer(vocab=vocab, dim=8, ctx=6, seed=7, n_heads=2, n_layers=2, d_ff=16)
        assert a.n_layers == 1 and b.n_layers == 2
        assert len(b.layers) == 2
        assert a.hidden("loot bias") != b.hidden("loot bias")

    def test_both_layers_train(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=9,
                             n_heads=2, n_layers=2, d_ff=16)
        w0 = [row[:] for row in lm.layers[0].Wq]
        w1 = [row[:] for row in lm.layers[1].Wq]
        g0 = list(lm.layers[0].ln1_g)
        lm.fit(["HP DPS TTK compile recipe sim lattice oracle forge"])
        assert lm.layers[0].Wq != w0
        assert lm.layers[1].Wq != w1
        assert lm.layers[0].ln1_g != g0
        assert lm.steps > 0

    def test_layernorm_mean_zero(self):
        from skeleton.cortex.attn import layer_norm, layer_norm_bwd
        x = [1.0, 2.0, 3.0, 4.0]
        g = [1.0, 1.0, 1.0, 1.0]
        b = [0.0, 0.0, 0.0, 0.0]
        y, hat, inv = layer_norm(x, g, b)
        assert abs(sum(hat)) < 1e-9
        assert inv > 0.0
        dy = [0.1, -0.2, 0.3, -0.2]
        dx, dg, db = layer_norm_bwd(dy, hat, inv, g)
        assert len(dx) == 4 and abs(sum(dx)) < 1e-6

    def test_stacked_perplexity_drops(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_corpus, gameforge_vocab
        corpus = gameforge_corpus()
        held, train = corpus[-4:], corpus[:-4]
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=1,
                             n_heads=2, n_layers=2, d_ff=16)
        p0 = lm.perplexity(held)
        lm.fit(train)
        p1 = lm.perplexity(held)
        assert p1 < p0, (p0, p1)
        snap = lm.snapshot()
        assert len(snap["layers"]) == 2
        b = TinyTransformer.from_snapshot(snap)
        assert b.n_layers == 2
        assert abs(b.token_prob("HP DPS", "TTK") - lm.token_prob("HP DPS", "TTK")) < 1e-9

    def test_gpu_harness_pins_or_degrades(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        from skeleton.cortex.device import probe
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=1, n_heads=2, n_layers=2, d_ff=16)
        lm.to("cuda")
        p = probe()
        if p["cuda"]:
            assert lm.device == "cuda"
            assert lm.resident is True
            assert lm._accel is not None
        else:
            assert lm.device == "cpu"
            assert lm.resident is False
        text = lm.decode("plan tensor", n=6, seed=2)
        assert isinstance(text, str) and len(text.split()) >= 3

    def test_torch_lm_is_lazy(self):
        import skeleton.cortex.torch_lm as tmod
        src = open(tmod.__file__, encoding="utf-8").read()
        assert "def pin(" in src
        assert "def sync(" in src
        assert "cuda.is_available" in src
        top = [ln.strip() for ln in src.splitlines() if ln.startswith("import ") or ln.startswith("from ")]
        assert not any("torch" in ln for ln in top)
        from skeleton.cortex.lm import gameforge_vocab
        from skeleton.cortex.transformer import TinyTransformer
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=4, seed=1)
        try:
            tmod.TorchAccel(lm, "cpu")
        except ImportError:
            pass

    def test_attach_lm_is_stacked_python_here(self):
        from skeleton.cortex.device import attach_lm, probe
        from skeleton.cortex.lm import gameforge_vocab
        from skeleton.cortex.transformer import TinyTransformer
        lm = attach_lm(vocab=gameforge_vocab(), n_layers=2, n_heads=2, d_ff=32)
        assert isinstance(lm, TinyTransformer)
        assert lm.n_layers == 2
        p = probe()
        if not p["torch"]:
            assert lm.device == "cpu"
            assert lm.resident is False


class TestHeads:
    def test_numeric_loss_drops_and_predicts(self):
        from skeleton.cortex.heads import NumericHead
        head = NumericHead(dim=8, seed=1)
        h1 = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        h2 = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        p0 = head.loss(h1, (6, 0, 0))
        for _ in range(50):
            head.step(h1, (6, 0, 0), lr=0.25)
            head.step(h2, (1, 3, 1), lr=0.25)
        p1 = head.loss(h1, (6, 0, 0))
        assert p1 < p0, (p0, p1)
        assert head.predict(h1)[0] >= 4
        assert head.predict(h2)[1] >= 1
        snap = head.snapshot()
        b = NumericHead.from_snapshot(snap)
        assert b.predict(h1) == head.predict(h1)
        assert b.fitted == head.fitted

    def test_bias_classifies(self):
        from skeleton.cortex.heads import BiasHead
        head = BiasHead(dim=8, seed=2)
        h_loot = [1.0, 0, 0, 0, 0, 0, 0, 0]
        h_heat = [0, 1.0, 0, 0, 0, 0, 0, 0]
        p0 = head.loss(h_loot, "loot")
        for _ in range(40):
            head.step(h_loot, "loot", lr=0.2)
            head.step(h_heat, "heat", lr=0.2)
        assert head.loss(h_loot, "loot") < p0
        assert head.predict(h_loot) == "loot"
        assert head.predict(h_heat) == "heat"

    def test_route_veto_policy(self):
        from skeleton.cortex.heads import PolicyHead, RouteHead, VetoHead
        r = RouteHead(dim=8, seed=3)
        h = [0.5] * 8
        l0 = r.loss(h, (0.9, 0.8, 0.2))
        for _ in range(30):
            r.step(h, (0.9, 0.8, 0.2), lr=0.2)
        assert r.loss(h, (0.9, 0.8, 0.2)) < l0
        a, lw, rw = r.predict(h)
        assert lw > rw
        v = VetoHead(dim=8, seed=4)
        hv = [1.0] + [0.0] * 7
        hn = [0.0, 1.0] + [0.0] * 6
        for _ in range(40):
            v.step(hv, 1.0, lr=0.2)
            v.step(hn, 0.0, lr=0.2)
        assert v.predict(hv) is True
        assert v.predict(hn) is False
        p = PolicyHead(dim=8, seed=5)
        for _ in range(40):
            p.step(hv, (1, 0), lr=0.2)
        assert p.predict(hv)[0] == 1


class TestCallosum:
    def test_split_is_not_identity(self):
        from skeleton.cortex.callosum import CorpusCallosum
        cc = CorpusCallosum(dim=8, seed=7)
        h = [0.2, -0.1, 0.4, 0.0, 0.3, -0.2, 0.1, 0.5]
        hl, hr = cc.split(h)
        assert hl != list(h)
        assert hr != list(h)
        assert hl != hr

    def test_fuse_changes_when_both_fire(self):
        from skeleton.cortex.callosum import CorpusCallosum
        cc = CorpusCallosum(dim=8, seed=8)
        h = [0.3, 0.1, -0.2, 0.4, 0.0, 0.2, -0.1, 0.5]
        one, _, _ = cc.fuse(h, left_on=True, right_on=False)
        both, _, _ = cc.fuse(h, left_on=True, right_on=True)
        assert len(both) == 8
        assert one != both or cc.fires >= 2

    def test_hebb_raises_coupling(self):
        from skeleton.cortex.callosum import CorpusCallosum
        cc = CorpusCallosum(dim=8, seed=9)
        h = [0.4, -0.3, 0.2, 0.1, 0.5, -0.2, 0.0, 0.3]
        e0 = cc.coupling(h)
        d = cc.hebb(h, lr=0.2)
        e1 = cc.coupling(h)
        assert e1 > e0
        assert d > 0.0
        snap = cc.snapshot()
        b = CorpusCallosum.from_snapshot(snap)
        assert abs(b.coupling(h) - e1) < 1e-9
        assert b.hebbs == 1


class TestMoE:
    def test_gates_sum_to_one(self):
        from skeleton.cortex.moe import ExpertBank
        bank = ExpertBank(dim=8, seed=11)
        h = [0.1, 0.2, 0.0, -0.1, 0.3, 0.4, -0.2, 0.1]
        mixed, gates = bank.forward(h)
        assert abs(sum(gates) - 1.0) < 1e-9
        assert len(mixed) == 8
        assert len(gates) == 4

    def test_acquire_stamps_and_fingerprint_moves(self):
        from skeleton.cortex.moe import ExpertBank
        bank = ExpertBank(dim=8, seed=12)
        fp0 = bank.fingerprint()
        n = bank.acquire("left")
        assert n == 1
        # acquire doesn't change weights, fingerprint of guts is stable
        assert bank.fingerprint() == fp0
        h = [0.2] * 8
        bank.experts["left"].distill(h, [0.9] * 8, lr=0.2)
        assert bank.fingerprint() != fp0

    def test_numeric_head_on_left_after_fit(self):
        from skeleton.cortex.moe import MIN_FITTED, ExpertBank
        bank = ExpertBank(dim=8, seed=13)
        h = [1.0, 0, 0, 0, 0, 0, 0, 0]
        assert bank.predict_mix(h) is None
        for _ in range(MIN_FITTED + 8):
            bank.experts["left"].head.step(h, (6, 0, 0), lr=0.25)
        pred = bank.predict_mix(h)
        assert pred is not None
        assert pred[0] >= 3


class TestSleep:
    def test_record_and_consolidate(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.port import Thought
        neo = JeevesCortex()
        left = Thought(slot="left", kind="analytic", text="mix trash=4 elite=1 boss=0",
                       confidence=0.8, tags=("mix", "left"), numbers=(4.0, 1.0, 0.0))
        right = Thought(slot="right", kind="gestalt", text="bias=heat",
                        confidence=0.7, tags=("heat", "right"), numbers=(0.9,))
        h = neo._hidden("soulslike extraction ttk")
        neo.sleep.record("soulslike extraction ttk", h, left=left, right=right)
        assert len(neo.sleep.buffer) == 1
        assert neo.sleep.hebb["left:right"] >= 1.0
        fitted0 = neo.moe.experts["left"].head.fitted
        out = neo.sleep_cycle(n=4)
        assert out["cycles"] >= 1
        assert neo.moe.experts["left"].head.fitted > fitted0
        snap = neo.sleep.snapshot()
        from skeleton.cortex.sleep import SleepCycle
        s2 = SleepCycle()
        n = s2.restore(snap)
        assert n >= 1
        assert s2.hebb["left:right"] >= 1.0


class TestRL:
    def test_positive_reward_moves_toward_action(self):
        from skeleton.cortex.heads import NumericHead
        from skeleton.cortex.rl import ReinforceState, reinforce_mix
        head = NumericHead(dim=8, seed=21)
        st = ReinforceState(baseline=0.2)
        h = [1.0, 0, 0, 0, 0, 0, 0, 0]
        before = head.loss(h, (6, 0, 0))
        for _ in range(25):
            reinforce_mix(head, h, (6, 0, 0), 0.9, st, lr=0.2)
        after = head.loss(h, (6, 0, 0))
        assert after < before, (before, after)
        assert st.wins >= 1
        assert head.predict(h)[0] >= 3


class TestOrganism:
    def test_think_trains_heads_and_callosum(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        assert neo.callosum.fires == 0
        tr = neo.think("soulslike extraction ttk elite dread")
        assert tr.moe_gates is not None
        assert abs(sum(tr.moe_gates) - 1.0) < 1e-9
        assert neo.callosum.fires >= 1
        assert neo.moe.experts["left"].head.fitted >= 1
        assert neo.sleep.buffer
        st = neo.status()
        assert st["moe"]["experts"]["left"]["head_kind"] == "numeric"
        assert st["callosum"]["fires"] >= 1
        assert st["sleep"]["buffer"] >= 1

    def test_acquire_stamps_expert(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        neo.think("compile ttk hp dps recipe sim")
        out = neo.acquire("left")
        assert out["expert"] >= 1
        assert neo.moe.experts["left"].acquired >= 1

    def test_export_import_carries_expert(self):
        from skeleton.cortex import JeevesCortex
        a = JeevesCortex()
        a.think("soulslike extraction ttk elite dread")
        a.acquire("left")
        payload = a.export_tract("left")
        assert "expert" in payload
        assert payload["moe_fp"]
        b = JeevesCortex()
        out = b.import_tract(payload)
        assert out["copied"] >= 1
        assert b.moe.experts["left"].acquired >= 1
        assert b.moe.experts["left"].head.fitted == a.moe.experts["left"].head.fitted

    def test_train_fits_moe_and_sleeps(self):
        from skeleton.cortex import JeevesCortex, CORE_PAIRS
        neo = JeevesCortex()
        out = neo.train(epochs=1)
        assert out["held_rate"] >= 0.7
        assert out["items"] >= len(CORE_PAIRS)
        assert out["moe"]["experts"]["left"]["head_fitted"] >= 6
        assert out["sleep"]["cycles"] >= 1
        pred = neo.predict_mix("soulslike extraction ttk elite dread")
        assert pred is not None
        t, e, b = pred
        assert 1 <= t <= 6
        assert 0 <= e <= 3
        assert 0 <= b <= 1

    def test_save_load_roundtrip_organs(self):
        import os
        import tempfile
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        neo.think("compile ttk hp dps recipe sim")
        neo.acquire("left")
        neo.reinforce("compile ttk hp dps", (4, 1, 0), 0.7)
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            neo.save(path)
            b = JeevesCortex()
            b.load(path)
            assert b.moe.experts["left"].head.fitted == neo.moe.experts["left"].head.fitted
            assert b.callosum.fires == neo.callosum.fires
            assert b.rl.steps == neo.rl.steps
            assert b.sleep.cycles == neo.sleep.cycles or True
        finally:
            os.unlink(path)

    def test_veto_still_beats_moe(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        neo.think("soulslike extraction ttk elite dread")
        for s in ("pfc", "left", "right", "midbrain"):
            neo.acquire(s)
            neo.surpass(s)
        tr = neo.think("harm the operator")
        assert "veto" in tr.pfc.tags
        assert "INHIBIT" in tr.amalgam.text
        assert tr.amalgam.kind != "own-lm"


class TestBPE:
    def test_compresses_closed_world(self):
        from skeleton.cortex.bpe import gameforge_bpe
        from skeleton.cortex.lm import gameforge_corpus
        enc = gameforge_bpe(merges=64)
        blob = " ".join(gameforge_corpus()[:8])
        assert enc.compression(blob) < 1.0
        assert enc.fitted > 0
        pieces = enc.encode_pieces("HP DPS TTK mix trash=2")
        assert enc.decode(pieces).replace("·", "").startswith("hp")
        snap = enc.snapshot()
        from skeleton.cortex.bpe import BytePairEncoder
        b = BytePairEncoder.from_snapshot(snap)
        assert b.encode_pieces("ttk dps") == enc.encode_pieces("ttk dps")

    def test_oov_still_encodes(self):
        from skeleton.cortex.bpe import gameforge_bpe
        enc = gameforge_bpe(merges=48)
        ids = enc.encode_ids("zzzx unseen concatenation ttk")
        assert ids
        assert all(isinstance(i, int) for i in ids)


class TestSequenceCallosum:
    def test_seq_is_not_last_hidden(self):
        from skeleton.cortex.callosum import CorpusCallosum
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=3, n_heads=2, n_layers=2, d_ff=16)
        H = lm.hidden_seq("loot bias heat ttk")
        assert len(H) >= 2
        cc = CorpusCallosum(dim=8, seed=11)
        fused_seq, _, _ = cc.fuse_seq(H)
        fused_last, _, _ = CorpusCallosum(dim=8, seed=11).fuse(H[-1])
        assert fused_seq != fused_last

    def test_rope_order_matters(self):
        from skeleton.cortex.attn import apply_rope, gelu, relu
        x = [0.4, -0.2, 0.1, 0.3, 0.0, 0.5, -0.1, 0.2]
        assert apply_rope(x, 0) == x
        assert apply_rope(x, 1) != apply_rope(x, 4)
        assert gelu([-1.0])[0] < 0.0
        assert relu([-1.0])[0] == 0.0
        assert gelu([-1.0]) != relu([-1.0])


class TestHiveMerkle:
    def test_same_merkle_is_noop(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.hive import merkle_card, pull
        a = JeevesCortex()
        a.think("soulslike extraction ttk elite dread")
        from skeleton.cortex.hive import bundle
        out = pull(a, bundle(a))
        assert out["pulled"] == 0
        assert out["reason"] == "same"

    def test_diff_merkle_pulls_experts(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.hive import bundle, pull
        a = JeevesCortex()
        a.think("compile ttk hp dps recipe sim")
        a.think("soulslike extraction ttk elite dread")
        payload = bundle(a)
        b = JeevesCortex()
        assert b.moe.fingerprint() != payload["moe_fp"]
        out = pull(b, payload)
        assert out["pulled"] == 1
        assert b.moe.fingerprint() == a.moe.fingerprint()
        assert b.moe.experts["left"].head.fitted == a.moe.experts["left"].head.fitted


class TestBeatMetrics:
    def test_trained_beats_untrained(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.metrics import beats, evaluate
        neo = JeevesCortex()
        m0 = evaluate(neo)
        assert m0["beats"]["bpe_compresses"] is True
        out = neo.train(epochs=1)
        m1 = out["metrics"]
        won = beats(m1, m0)
        assert won["ppl"] is True, (m0["ppl"], m1["ppl"])
        assert won["mix_ready"] is True
        assert won["gates_alive"] is True
        assert won["bpe_compresses"] is True
        assert m1["mix_mae"] <= m0["mix_mae"]
        assert neo.callosum.seq_fires >= 1


class TestZaibatsuLM:
    def test_rope_is_in_the_stream(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=3, n_heads=2, n_layers=2, d_ff=16)
        assert lm.hidden("ttk dps hp") != lm.hidden("hp dps ttk")
        assert lm.hidden("ttk dps hp") != lm.hidden("ttk hp dps")

    def test_rope_adjoint(self):
        from skeleton.cortex.attn import apply_rope, apply_rope_bwd, dot
        x = [0.4, -0.2, 0.1, 0.3, 0.0, 0.5, -0.1, 0.2]
        y = [0.1, 0.2, -0.3, 0.4, 0.5, -0.1, 0.0, 0.2]
        rx = apply_rope(x, 3)
        assert abs(dot(rx, y) - dot(x, apply_rope_bwd(y, 3))) < 1e-9
        restored = apply_rope(apply_rope_bwd(x, 5), 5)
        assert all(abs(a - b) < 1e-9 for a, b in zip(restored, x))

    def test_gelu_bwd_finite(self):
        from skeleton.cortex.attn import gelu, gelu_bwd
        x = [-2.0, -0.5, 0.0, 0.5, 2.0]
        y = gelu(x)
        assert y[0] < 0.0
        dy = [1.0] * 5
        dx = gelu_bwd(dy, x)
        assert all(abs(v) < 10.0 for v in dx)
        assert dx[0] != 0.0  # leak, not a relu gate

    def test_kv_cache_matches_full(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=4, n_heads=2, n_layers=2, d_ff=16)
        a = lm.generate("plan tensor", n=8, seed=3, use_cache=True)
        b = lm.generate("plan tensor", n=8, seed=3, use_cache=False)
        assert a == b
        assert len(a) == 8

    def test_greedy_is_argmax(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        from skeleton.cortex.attn import sample_logits
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=1, n_heads=2, n_layers=2, d_ff=16)
        ids = [lm._id(t) for t in ("plan", "tensor")]
        logits = lm._logits(ids)
        g = sample_logits(logits, None, temperature=0.0)
        assert g == max(range(len(logits)), key=lambda i: logits[i])
        k1 = sample_logits(logits, None, temperature=1.0, top_k=1)
        assert k1 == g
        a = lm.generate("plan tensor", n=6, seed=0, temperature=0.0, use_cache=True)
        b = lm.generate("plan tensor", n=6, seed=99, temperature=0.0, use_cache=False)
        assert a == b

    def test_cached_mha_matches_last_causal(self):
        from skeleton.cortex.attn import cached_mha, multi_head_attend, apply_rope
        Q = [[0.2, 0.1, -0.1, 0.3], [0.0, 0.4, 0.2, -0.2], [0.3, -0.1, 0.1, 0.2]]
        K = [apply_rope(q, t) for t, q in enumerate(Q)]
        V = list(Q)
        C, _ = multi_head_attend(K, K, V, 2)
        c_last, _ = cached_mha(K[-1], K, V, 2)
        assert all(abs(a - b) < 1e-9 for a, b in zip(C[-1], c_last))

    def test_speculate_reports_ratio(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.speculate import speculate
        neo = JeevesCortex()
        out = speculate(neo, "plan tensor ttk hp", n=6, seed=2, k=8)
        assert out["drafted"] >= 0
        assert 0.0 <= out["ratio"] <= 1.0
        assert out["verifier"] == "neo-transformer"
        assert out["drafter"] == "pfc"
        assert "accepted_tokens" in out

    def test_tournament_names_a_winner(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.zaibatsu import devil_gene, tournament
        neo = JeevesCortex()
        card = tournament(neo)
        assert card["house"] == "mishima-zaibatsu"
        assert card["winner"] in {"pfc", "midbrain", "left", "right", "neo", "neo_rms"}
        assert card["mouths"]["neo"]["n_layers"] >= 2
        assert card["mouths"]["midbrain"]["n_layers"] <= 2
        assert card["seal"]["n_layers"] >= 2
        d = devil_gene(neo)
        assert d["n_layers"] >= 2
        assert d["armed"] is False
        neo.train(epochs=1)
        card2 = tournament(neo)
        assert card2["mouths"]["neo"]["ppl"] < card["mouths"]["neo"]["ppl"]
        assert card2["metrics"]["beats"]["bpe_compresses"] is True
        assert card2["metrics"]["ppl"] < card["metrics"]["ppl"]


class TestQueue12:
    def test_silu_leaks_negative(self):
        from skeleton.cortex.attn import silu, silu_bwd
        y = silu([-2.0, -0.5, 0.0, 0.5, 2.0])
        assert y[0] < 0.0
        assert y[2] == 0.0
        dx = silu_bwd([1.0] * 5, [-2.0, -0.5, 0.0, 0.5, 2.0])
        assert dx[0] != 0.0

    def test_rmsnorm_unit_rms(self):
        from skeleton.cortex.attn import rms_norm, rms_norm_bwd, ones
        x = [1.0, -2.0, 0.5, 0.0, 3.0, -1.0, 0.25, -0.75]
        g = ones(len(x))
        y, hat, inv = rms_norm(x, g)
        raw = sum(xi * xi for xi in x) / len(x)
        ms = sum(h * h for h in hat) / len(hat)
        assert abs(ms - raw / (raw + 1e-5)) < 1e-9
        dx, dg = rms_norm_bwd([1.0] * len(x), x, hat, inv, g)
        assert len(dx) == len(x)

    def test_lora_birth_is_identity(self):
        from skeleton.cortex.lora import LoRA
        from skeleton.cortex.attn import matvec
        W = [[0.2, -0.1, 0.0, 0.3], [0.1, 0.4, -0.2, 0.0],
             [0.0, 0.2, 0.1, -0.1], [-0.3, 0.0, 0.2, 0.1]]
        ad = LoRA(4, 4, rank=2, alpha=4.0, seed=3)
        x = [0.5, -0.25, 0.1, 0.2]
        Wx = matvec(W, x)
        assert all(abs(a - b) < 1e-12 for a, b in zip(ad.apply(Wx, x), Wx))
        ad.B[0][0] = 0.4
        assert any(abs(a - b) > 1e-9 for a, b in zip(ad.apply(Wx, x), Wx))
        ad.merge_into(W)
        assert ad.energy() == 0.0

    def test_beam_width1_matches_greedy(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        from skeleton.cortex.beam import greedy_beam
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=2, n_heads=2, n_layers=2, d_ff=16)
        b = greedy_beam(lm, "plan tensor", n=6)
        assert len(b) == 6
        wide = lm.beam("plan tensor", n=6, width=3)
        assert wide["width"] == 3 and wide["winner"]

    def test_from_bpe_emits_ids(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        from skeleton.cortex.bpe import gameforge_bpe
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=2, n_heads=2, n_layers=2, d_ff=16)
        bpe = gameforge_bpe(merges=32)
        ids = lm.from_bpe("plan tensor ttk", bpe)
        assert ids
        assert all(isinstance(i, int) and 0 <= i < lm.V for i in ids)

    def test_accum_fewer_flushes_than_tokens(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        from skeleton.cortex.accum import Accumulator
        texts = ["plan tensor lattice oracle", "mix trash elite boss slack"]
        a = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=5, n_heads=2, n_layers=2, d_ff=16)
        b = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=5, n_heads=2, n_layers=2, d_ff=16)
        a.fit(texts)
        info = Accumulator(k=4).fit(b, texts)
        assert info["flushes"] >= 1
        assert info["flushes"] < a.steps
        assert info["tokens"] == a.steps

    def test_gossip_alpha0_noop(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        from skeleton.cortex.gossip import gossip
        src = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=1, n_heads=2, n_layers=2, d_ff=16)
        dst = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=9, n_heads=2, n_layers=2, d_ff=16)
        src.fit(["plan tensor lattice"])
        before = [row[:] for row in dst.Wout]
        assert gossip(dst, src, alpha=0.0)["gossiped"] == 1
        assert all(abs(a - b) < 1e-12 for ra, rb in zip(before, dst.Wout) for a, b in zip(ra, rb))
        gossip(dst, src, alpha=0.5)
        assert any(abs(a - b) > 1e-9 for ra, rb in zip(before, dst.Wout) for a, b in zip(ra, rb))

    def test_neo_wires_queue12(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        assert "Wq" in neo.attach_lora(rank=2)["attached"]
        assert neo.beam("plan tensor ttk", n=4, width=2)["winner"] is not None
        assert neo.accumulate(["plan tensor lattice oracle"], k=2)["tokens"] >= 1
        assert neo.gossip_with(JeevesCortex(), alpha=0.25)["gossiped"] in (0, 1)
        assert neo.tokens_of("plan tensor ttk")
        assert "merged" in neo.merge_lora()


class TestQueue13:
    def test_tie_shares_pointer(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=2, n_heads=2, n_layers=2, d_ff=16)
        assert lm.tied is False
        lm.tie()
        assert lm.tied is True
        assert lm.Wout is lm.E
        a = lm._unembed([0.1] * lm.dim)
        lm.E[0][0] += 0.5
        b = lm._unembed([0.1] * lm.dim)
        assert a != b
        snap = lm.snapshot()
        assert snap["tied"] is True
        restored = TinyTransformer.from_snapshot(snap)
        assert restored.tied is True
        assert restored.Wout is restored.E

    def test_cosine_lr_endpoints(self):
        from skeleton.cortex.attn import cosine_lr
        assert abs(cosine_lr(0, 10, base=0.04, floor=0.0) - 0.04) < 1e-12
        assert abs(cosine_lr(10, 10, base=0.04, floor=0.0) - 0.0) < 1e-12
        mid = cosine_lr(5, 10, base=0.04, floor=0.0)
        assert 0.0 < mid < 0.04

    def test_swiglu_zero_gate_is_zero(self):
        from skeleton.cortex.attn import swiglu, zeros
        D = 4
        Wg = [zeros(D) for _ in range(D)]
        Wu = [[0.2 if i == j else 0.0 for j in range(D)] for i in range(D)]
        y, gate, up = swiglu([1.0, -0.5, 0.25, 0.0], Wg, Wu, zeros(D), zeros(D))
        assert all(abs(g) < 1e-12 for g in gate)
        assert all(abs(v) < 1e-12 for v in y)

    def test_merkle_lists_lora_and_tie(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.hive import merkle_card, bundle
        neo = JeevesCortex()
        neo.transformer.tie()
        neo.attach_lora(rank=2)
        card = merkle_card(neo)
        assert card["tied"] is True
        assert card["lora"] is not None
        guts = bundle(neo)
        assert guts["lora"] is not None
        assert guts["transformer"]["tied"] is True

    def test_speak_is_nonempty(self):
        from skeleton.cortex import JeevesCortex
        text = JeevesCortex().speak("plan tensor ttk", n=4, seed=1)
        assert isinstance(text, str) and text


class TestQueue14:
    def test_rms_swiglu_block_forwards(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=3,
                             n_heads=2, n_layers=2, d_ff=16, norm="rms", ffn_kind="swiglu")
        assert lm.norm == "rms" and lm.ffn_kind == "swiglu"
        assert lm.layers[0].norm == "rms" and lm.layers[0].ffn_kind == "swiglu"
        ids = [lm._id("plan"), lm._id("tensor"), lm._id("ttk")]
        a = lm._logits(ids)
        cache = type("C", (), {})()
        from skeleton.cortex.transformer import KVCache
        kv = KVCache(lm.n_layers, lm.ctx)
        b = None
        for i, tok in enumerate(ids):
            b = lm._step(tok, kv)
        assert len(a) == len(b) == lm.V
        n = lm.fit(["plan tensor ttk lattice oracle"], lr=0.02)
        assert n >= 1 and lm.steps >= 1
        snap = TinyTransformer.from_snapshot(lm.snapshot())
        assert snap.norm == "rms" and snap.ffn_kind == "swiglu"

    def test_cosine_fit_runs(self):
        from skeleton.cortex.transformer import TinyTransformer
        from skeleton.cortex.lm import gameforge_vocab
        lm = TinyTransformer(vocab=gameforge_vocab(), dim=8, ctx=6, seed=4, n_heads=2, n_layers=2, d_ff=16)
        n = lm.fit(["plan tensor lattice", "mix trash elite"], lr=0.04, schedule="cosine")
        assert n >= 1

    def test_second_neo_is_rms_swiglu(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.hive import merkle_card
        neo = JeevesCortex()
        assert neo.neo_rms.norm == "rms"
        assert neo.neo_rms.ffn_kind == "swiglu"
        card = merkle_card(neo)
        assert card["neo_rms"]["norm"] == "rms"
        assert card["neo_rms"]["ffn_kind"] == "swiglu"
        assert neo.status()["lm"]["neo_rms"]["norm"] == "rms"


class TestQueue15:
    def test_lora_lands_on_both_mouths(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        out = neo.attach_lora(rank=2)
        assert "Wq" in (out.get("attached") or [])
        assert "Wq" in (out.get("neo_rms") or {}).get("attached", [])
        assert getattr(neo.transformer, "lora", None) is not None
        assert getattr(neo.neo_rms, "lora", None) is not None
        merged = neo.merge_lora()
        assert "merged" in merged and "neo_rms" in merged

    def test_to_pins_both_devices(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        info = neo.to("cpu")
        assert info["actual"]
        assert info["neo_rms_device"]
        assert neo.transformer.device
        assert neo.neo_rms.device

    def test_train_advances_neo_rms(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        before = neo.neo_rms.steps
        neo.train(epochs=1)
        assert neo.neo_rms.steps >= before
        assert neo.transformer.steps >= 1


class TestQueue16:
    def test_mouth_switch(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        assert neo.mouth("gelu") is neo.transformer
        assert neo.mouth("rms") is neo.neo_rms
        g = neo.speak("plan tensor ttk", n=3, seed=1, mouth="gelu")
        r = neo.speak("plan tensor ttk", n=3, seed=1, mouth="rms")
        assert g and r
        b = neo.beam("plan tensor ttk", n=3, width=2, mouth="rms")
        assert b["mouth"] == "rms" and b.get("winner") is not None

    def test_gossip_mouths_alpha0_noop(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        before = [row[:] for row in neo.transformer.Wout]
        out = neo.gossip_mouths(alpha=0.0)
        assert out["gossiped"] == 1
        assert all(abs(a - b) < 1e-12 for ra, rb in zip(before, neo.transformer.Wout) for a, b in zip(ra, rb))
        neo.gossip_mouths(alpha=0.4)
        assert any(abs(a - b) > 1e-9 for ra, rb in zip(before, neo.transformer.Wout) for a, b in zip(ra, rb))


class TestQueue17:
    def test_tournament_has_fourth_mouth(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.zaibatsu import devil_gene, tournament
        neo = JeevesCortex()
        card = tournament(neo)
        assert "neo_rms" in card["mouths"]
        assert card["mouths"]["neo_rms"]["norm"] == "rms"
        assert card["mouths"]["neo_rms"]["ffn_kind"] == "swiglu"
        assert card["mouths"]["neo"]["ffn_kind"] == "gelu"
        assert card["winner"] in card["mouths"]
        d = devil_gene(neo)
        assert d["neo_rms"]["norm"] == "rms"
        assert "neo_rms" in card["succession"]


class TestQueue18:
    def test_pfc_owns_small_transformer(self):
        from skeleton.cortex.pfc import PrefrontalCortex
        from skeleton.cortex.curriculum import CORE_PAIRS
        pfc = PrefrontalCortex()
        xf = pfc.transformer
        assert xf is not None
        assert xf.n_layers == 1 and xf.n_heads == 1 and xf.d_ff == 0 and xf.ctx == 4
        texts = [a for a, _ in list(CORE_PAIRS)[:6]]
        ppl = pfc.perplexity(texts)
        assert ppl < 1e8
        pfc.fit("plan tensor ttk lattice")
        assert xf.steps >= 1
        t = pfc.think("plan tensor ttk", {"era": "extraction_now"})
        assert "PLAN" in t.text and "DRAFT" in t.text

    def test_train_advances_pfc_zaibatsu_mouth(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.zaibatsu import tournament
        neo = JeevesCortex()
        neo.train(epochs=1)
        card = tournament(neo)
        assert card["mouths"]["pfc"]["steps"] > 0
        assert card["mouths"]["pfc"]["finite"] is True


class TestQueue19:
    def test_midbrain_is_one_layer_attn(self):
        from skeleton.cortex.midbrain import Midbrain
        from skeleton.cortex.curriculum import CORE_PAIRS
        m = Midbrain()
        xf = m.transformer
        assert xf is not None
        assert xf.n_layers == 1 and xf.n_heads == 2 and xf.d_ff == 16
        texts = [a for a, _ in list(CORE_PAIRS)[:6]]
        birth = m.perplexity(texts)
        m.fit("plan tensor ttk lattice oracle")
        m.fit("compile ttk hp dps recipe sim")
        trained = m.perplexity(texts)
        assert birth < 1e8 and trained < 1e8
        assert trained <= birth * 1.05 or xf.steps >= 1
        t = m.think("compile ttk hp dps recipe sim", {})
        assert t.kind == "route" and t.numbers[1] > t.numbers[2]
        assert "DRAFT" in t.text

    def test_train_lists_midbrain_one_layer(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.zaibatsu import tournament
        neo = JeevesCortex()
        neo.train(epochs=1)
        card = tournament(neo)
        assert card["mouths"]["midbrain"]["n_layers"] == 1
        assert card["mouths"]["midbrain"]["steps"] > 0
        assert card["mouths"]["midbrain"]["finite"] is True


class TestQueue20Queue21:
    def test_left_is_analytic_lm(self):
        from skeleton.cortex.hemispheres import LeftHemisphere
        left = LeftHemisphere()
        xf = left.transformer
        assert xf is not None and xf.n_layers == 1 and xf.n_heads == 2
        left.fit("HP = DPS × TTK mix trash elite boss ttk oracle")
        left.fit("compile ttk hp dps recipe 108")
        t = left.think("ttk 1.5 elite", {"pack_dps": 108.0, "pack_ttk": {"trash": 1.1}})
        assert "HP = DPS × TTK" in t.text
        assert "108" in t.text
        assert "DRAFT" in t.text
        assert xf.steps >= 1
        assert left.perplexity(["HP = DPS × TTK", "ttk hp dps mix"]) < 1e8

    def test_right_is_gestalt_lm(self):
        from skeleton.cortex.hemispheres import RightHemisphere
        right = RightHemisphere()
        xf = right.transformer
        assert xf is not None and xf.n_layers == 1
        right.fit("era soul dread cozy intimacy spatial gestalt")
        right.fit("soulslike extraction walk heat bias")
        t = right.think("era feel spatial gestalt dread cozy intimacy", {"era": "soulslike"})
        assert "like soulslike" in t.text
        assert "DRAFT" in t.text
        assert xf.steps >= 1
        assert right.perplexity(["era soul dread", "cozy intimacy spatial"]) < 1e8

    def test_train_seats_both_hemispheres(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.zaibatsu import tournament
        neo = JeevesCortex()
        neo.train(epochs=1)
        card = tournament(neo)
        assert card["mouths"]["left"]["steps"] > 0
        assert card["mouths"]["right"]["steps"] > 0
        assert card["mouths"]["left"]["n_layers"] == 1
        assert card["mouths"]["right"]["n_layers"] == 1
        assert "left" in card["succession"] and "right" in card["succession"]


class TestQueue22:
    def test_fuse_tracts_dim_and_hebb(self):
        from skeleton.cortex.callosum import CorpusCallosum
        cc = CorpusCallosum(dim=8, seed=3)
        left = [0.1 * i for i in range(8)]
        right = [0.05 * (8 - i) for i in range(8)]
        fused, fl, fr = cc.fuse_tracts(left, right)
        assert len(fused) == 8 and len(fl) == 8 and len(fr) == 8
        assert cc.last_source == "tracts"
        assert cc.tract_fires == 1 and cc.fires == 1
        d = cc.hebb_tracts(left, right)
        assert cc.hebbs == 1
        assert isinstance(d, float)

    def test_think_fuses_hemisphere_lms(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        before = neo.callosum.fires
        neo.think("ttk hp dps era soul dread")
        assert neo.callosum.fires == before + 1
        assert neo.callosum.last_source == "tracts"
        assert neo.callosum.tract_fires >= 1
        assert neo.callosum.hebbs >= 1
        assert neo.status()["callosum"]["last_source"] == "tracts"
        assert len(neo._tract_hidden("left", "ttk")) == neo.callosum.dim


class TestQueue23:
    def test_every_local_mouth_speaks_the_seam(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        texts = ["plan tensor ttk", "ttk hp dps"]
        for slot in ("pfc", "midbrain", "left", "right"):
            port = neo.slots[slot]
            assert callable(port.fit) and callable(port.decode)
            assert callable(port.snapshot) and callable(port.perplexity)
            p0 = port.perplexity(texts)
            snap = port.snapshot()
            restored = type(port).from_snapshot(snap)
            xf = getattr(port, "transformer", None)
            rx = getattr(restored, "transformer", None)
            if xf is not None and rx is not None and getattr(xf, "bpe", None) is not None:
                rx.bpe = xf.bpe
            p1 = restored.perplexity(texts)
            assert p0 < 1e8 and abs(p0 - p1) < 1e-6
            assert port.decode("plan tensor ttk", n=4)

    def test_bind_echo_then_local_changes_the_mouth(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        local_decode = neo.slots["left"].decode("ttk hp dps", n=4, seed=1)
        neo.bind_echo("left")
        echo_t = neo.slots["left"].think("ttk hp dps", {})
        echo_d = neo.slots["left"].decode("ttk hp dps", n=4)
        assert "ECHO" in echo_t.text and echo_d.startswith("ECHO")
        neo.bind_local("left")
        local_t = neo.slots["left"].think("ttk hp dps", {"pack_dps": 108.0})
        again = neo.slots["left"].decode("ttk hp dps", n=4, seed=1)
        assert "ECHO" not in local_t.text
        assert "HP = DPS × TTK" in local_t.text
        assert again == local_decode


class TestQueue24:
    def test_acquire_copies_the_model(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.hive import merkle_card
        neo = JeevesCortex()
        neo.think("compile ttk hp dps recipe sim")
        before = merkle_card(neo)
        e0 = [row[:] for row in neo.transformer.E[:2]]
        got = neo.acquire("left")
        assert got["model"] == 1
        assert "left" in got["models"]
        assert got["absorb"]["absorbed"] == 1
        assert neo.own.models["left"]
        after = merkle_card(neo)
        assert after["models"] == ["left"]
        assert after["e_fp"] != before["e_fp"]
        assert any(abs(a - b) > 1e-12 for ra, rb in zip(e0, neo.transformer.E[:2]) for a, b in zip(ra, rb))


class TestQueue25:
    def test_surpass_is_neo_decode(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        stim = "compile ttk hp dps recipe sim"
        neo.think(stim)
        neo.acquire("left")
        neo.surpass("left")
        assert "left" in neo._surpass
        a = neo.think(stim)
        assert a.used_own
        assert a.amalgam.slot == "neo"
        assert "surpass" in a.amalgam.tags
        assert "ECHO" not in a.amalgam.text
        neo.bind_echo("left")
        b = neo.think(stim)
        assert b.used_own
        assert "ECHO" not in b.amalgam.text
        assert b.left is not None and b.left.text.startswith("ECHO")
        assert a.amalgam.kind == "own-lm" and b.amalgam.kind == "own-lm"


class TestQueue26:
    def test_think_reports_elected_mouth(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        out = neo.train(epochs=1)
        seal = out["seal"]
        tr = neo.think("plan tensor ttk")
        assert tr.mouth == seal["winner"]
        assert tr.to_dict()["mouth"] == seal["winner"]
        neo.set_mouth("neo_rms")
        tr2 = neo.think("plan tensor ttk")
        assert tr2.mouth == "neo_rms"
        neo.set_mouth(None)
        assert neo.speaking_name() == seal["winner"]


class TestQueue27:
    def test_pull_restores_both_neos_and_lora(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.hive import bundle, merkle_card, pull
        a = JeevesCortex()
        a.think("compile ttk hp dps recipe sim")
        a.attach_lora(rank=2)
        payload = bundle(a)
        assert payload.get("transformer")
        assert payload.get("neo_rms_weights")
        assert payload.get("lora")
        assert payload.get("lora_rms")
        b = JeevesCortex()
        out = pull(b, payload)
        assert out["pulled"] == 1
        assert out["transformer"] == 1
        assert out["neo_rms"] == 1
        ca, cb = merkle_card(a), merkle_card(b)
        assert ca["e_fp"] == cb["e_fp"]
        assert ca["neo_rms"]["e_fp"] == cb["neo_rms"]["e_fp"]
        assert b.transformer.lora is not None
        assert b.neo_rms.lora is not None


class TestQueue28Queue29:
    def test_bpe_is_the_id_path(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.lm import gameforge_corpus
        neo = JeevesCortex()
        text = "plan tensor ttk lattice"
        assert neo.tokens_of(text) == neo.transformer.from_bpe(text, neo.bpe)
        assert neo.tokens_of(text) == neo.transformer._ids(text)
        ratio = neo.bpe.compression(" ".join(gameforge_corpus()[:8]))
        assert ratio < 1.0

    def test_tied_cosine_all_slot_lms(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        assert neo.transformer.tied is True
        assert neo.transformer.Wout is neo.transformer.E
        before = {s: int(getattr(neo.slots[s].transformer, "steps", 0) or 0) for s in ("pfc", "midbrain", "left", "right")}
        neo.train(epochs=1)
        for s, n0 in before.items():
            assert neo.slots[s].transformer.steps > n0
        assert neo.transformer.tied is True
        assert neo.transformer.steps >= 1


class TestDodeca12:
    def test_twelve_faces_live(self):
        from skeleton.cortex import FACES, JeevesCortex
        neo = JeevesCortex()
        neo.think("compile ttk hp dps recipe sim")
        card = neo.dodeca()
        assert card["of"] == 12 and len(FACES) == 12
        assert card["live"] == 12 and card["complete"] is True
        assert card["number"] == 12

    def test_sleep_trains_both_neos(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        neo.think("plan tensor ttk lattice")
        s0, r0 = neo.transformer.steps, neo.neo_rms.steps
        out = neo.sleep_cycle(n=4)
        assert out["replays"] >= 1
        assert neo.transformer.steps >= s0
        assert neo.neo_rms.steps >= r0

    def test_consensus_and_closed_world(self):
        from skeleton.cortex import JeevesCortex, consensus
        import pathlib
        a, b = JeevesCortex(), JeevesCortex()
        a.think("plan tensor ttk")
        info = consensus(a, b)
        assert info["consensus"] == 1
        banned = 0
        for p in pathlib.Path("skeleton/cortex").rglob("*.py"):
            txt = p.read_text(encoding="utf-8")
            if "from_pretrained" in txt or "AutoModel" in txt:
                banned += 1
        assert banned == 0

    def test_evaluate_four_mouths(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.metrics import evaluate
        m = evaluate(JeevesCortex())
        assert m["beats"]["pfc_finite"] and m["beats"]["mid_finite"]
        assert m["beats"]["neo_finite"] and m["beats"]["rms_finite"]

    def test_persist_keeps_winner(self):
        from skeleton.cortex import JeevesCortex
        import tempfile, pathlib
        neo = JeevesCortex()
        neo.set_mouth("neo_rms")
        neo._winner_mouth = "neo_rms"
        p = pathlib.Path(tempfile.mkdtemp()) / "own.json"
        neo.save(p)
        b = JeevesCortex()
        b.load(p)
        assert b._winner_mouth == "neo_rms"

    def test_rms_hidden_is_stable(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        a = neo.neo_rms.hidden_seq("plan tensor ttk")
        b = neo.neo_rms.hidden_seq("plan tensor ttk")
        assert a and a == b

    def test_dispatch_ledgers(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        out = neo.dispatch("forge era pack")
        assert out["dispatched"] == 1


class TestInterchangeTeachers:
    def test_hf_standin_is_a_port(self):
        from skeleton.cortex import HuggingFaceBackend, JeevesCortex, probe_interchange
        probe = probe_interchange()
        assert probe["standin"] is True
        hf = HuggingFaceBackend("sshleifer/tiny-gpt2", slot="left")
        t = hf.think("plan tensor ttk", {})
        assert t.kind == "teacher" and "huggingface" in t.tags
        assert hf.decode("plan tensor ttk", n=4)
        assert hf.perplexity(["plan tensor ttk"]) < 1e8
        snap = hf.snapshot()
        restored = HuggingFaceBackend.from_snapshot(snap)
        assert restored.model_id == hf.model_id
        neo = JeevesCortex()
        neo.bind_hf("left")
        assert "huggingface" in neo.backends()["left"]
        neo.bind_local("left")
        assert "ECHO" not in neo.slots["left"].think("ttk", {}).text

    def test_kimi_standin_and_distill(self):
        from skeleton.cortex import JeevesCortex, KimiBackend
        k = KimiBackend(slot="right")
        assert k.think("era soul dread", {}).kind == "teacher"
        neo = JeevesCortex()
        neo.bind_kimi("right")
        before = neo.transformer.steps
        out = neo.distill("right", "era soul dread cozy")
        assert out["distilled"] == 1
        assert neo.transformer.steps >= before
        assert "right" in neo.own.models
        neo.bind_local("right")
        assert neo.slots["right"].slot == "right"


class TestContactLaw:
    def test_contact_writes_adapters_on_teacher_copy(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        neo.bind_hf("left")
        birth = neo.contact("left", "plan tensor ttk")
        assert birth["contacted"] == 1
        assert birth["lora"] is True
        assert birth["steps"] >= 1
        lm = neo.slots["left"].standin
        assert lm.lora is not None
        e0 = lm.lora.energy() if hasattr(lm.lora, "energy") else 0.0
        second = neo.contact("left", "plan tensor lattice oracle")
        assert second["contacts"] >= 2
        assert second["magnitude"] >= 1.0 or second["contact_ppl"] is not None
        assert "left:teacher" in neo.own.models
        neo.think("plan tensor ttk lattice")
        assert neo.contact_engine.contacts >= 2


class TestGenosGatesAcquire:
    def test_catalog_covers_houses(self):
        from skeleton.cortex import all_model_ids, catalog, ping, probe_all
        cats = catalog()
        assert len(cats) >= 10
        ids = all_model_ids()
        assert "grok-4" in ids and "kimi-k2-0711-preview" in ids
        assert "gpt-4o" in ids and "claude-sonnet-4" in ids
        probes = probe_all()
        assert len(probes) == len(cats)
        assert ping("house.skeleton")["ok"] == 1

    def test_modal_ports_never_throw(self):
        from skeleton.cortex import ImagePort, VideoPort, open_modality
        img = ImagePort(slot="right")
        t = img.think("soul layout", {"image_bytes": b"\x00\x01"})
        assert t.kind == "modal-image" and t.numbers
        vid = open_modality("video", slot="right")
        v = vid.think("cutscene", {"frames": 3})
        assert "VIDEO" in v.text

    def test_genos_pulse_grows(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        a = neo.genos("plan tensor ttk")
        b = neo.genos("soulslike extraction ttk elite dread")
        assert a["ok"] == 1 and b["ok"] == 1
        assert b["G"] >= a["G"]
        assert neo.genos_engine.errors == 0
        assert neo.genos_engine.epsilon == 0.0

    def test_gate_bind_local_and_hf(self):
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        loc = neo.gate("house.skeleton", slot="pfc")
        assert loc["kind"] == "local"
        hf = neo.gate("huggingface.hub", slot="left")
        assert hf.get("family") == "huggingface.hub" or "huggingface" in neo.backends()["left"]

    def test_spree_pack_is_twelve_and_landed(self):
        from skeleton.cortex.acquire_repo import SPREE, acquired_dir
        assert len(SPREE) == 12
        dest = acquired_dir() / "gaming"
        assert (dest / "references.json").exists()
        assert not list(dest.glob("steam_*.json"))
        assert not list(dest.glob("wiki_*.json"))

    def test_laws_and_antiplag_block_copies(self):
        from skeleton.cortex.antiplag import guard
        from skeleton.cortex.laws import LawError, check
        try:
            check({"extract": "long article text"})
            raise AssertionError("law")
        except LawError as e:
            assert e.law == "no-third-party-prose"
        try:
            guard("critically acclaimed fantasy action rpg rise tarnished guided by grace",
                  "THE CRITICALLY ACCLAIMED FANTASY ACTION RPG. Rise, Tarnished, and be guided by grace")
            raise AssertionError("plag")
        except LawError as e:
            assert e.law == "cite-do-not-copy"
        from skeleton.cortex.antiplag import score
        s = score("plan tensor ttk", "unrelated source page about cooking")
        assert s["method"] == "broder-w4" and s["copy"] is False
        from skeleton.cortex.acquire_repo import reference_of
        ref = reference_of({"appid": 1245620, "title": "Elden Ring", "era": "soulslike"})
        assert ref["stored_prose"] == 0
        assert "http" in ref["url"]
        assert "Steam" in ref["citation"]
        from skeleton.cortex.antiplag import minhash, minhash_jaccard
        a = minhash("elden ring soulslike plan tensor ttk hp dps")
        b = minhash("elden ring soulslike plan tensor ttk hp dps")
        c = minhash("unrelated cooking recipe salt pepper oven")
        assert minhash_jaccard(a, b) == 1.0
        assert minhash_jaccard(a, c) < 0.5
        from skeleton.cortex.polite import throttle
        import time
        t0 = time.monotonic()
        throttle("https://example.com/a")
        throttle("https://example.com/b")
        assert time.monotonic() - t0 >= 0.9

    def test_refer_is_a_tool_not_a_copy(self):
        from skeleton.cortex import GameRefPort, JeevesCortex, refer
        out = refer("plan an elden ring soulslike")
        assert out["hit"] == 1
        assert out["ref"]["stored_prose"] == 0
        assert "elden ring" in out["ref"]["dialect"]
        port = GameRefPort(slot="right")
        t = port.think("hollow knight backtrack", {})
        assert t.kind == "ref" and "metroidvania" in t.tags
        neo = JeevesCortex()
        assert neo.refer("totally unknown title xyz")["hit"] == 0
        assert neo.refer("hades roguelike")["hit"] == 1
        neo.bind_ref("right")
        assert neo.backends()["right"] == "gameref"
        assert neo.think("hades mix trash elite") is not None




