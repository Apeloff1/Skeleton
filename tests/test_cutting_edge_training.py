"""AdamW training, min-p sampling, and lossless speculative verification."""

from __future__ import annotations

import random

import numpy as np
import pytest

from skeleton.ai.model_runtime.runtime_contracts import (
    GenerationConfig,
    RuntimeContractError,
    RuntimeLimits,
)
from skeleton.ai.runtime.inference.local import LocalInferenceRequest
from skeleton.ai.runtime.inference.neural import NeuralLMConfig, NeuralLMError, NumpyRecurrentLM
from skeleton.cortex.attn import sample_logits
from skeleton.cortex.speculative import greedy_speculative
from skeleton.cortex.transformer import TinyTransformer


def _mouth(**kwargs) -> TinyTransformer:
    seed = kwargs.pop("seed", 11)
    model = TinyTransformer(
        vocab=("alpha", "beta", "gamma", "delta"),
        dim=8,
        ctx=6,
        n_heads=2,
        n_layers=1,
        d_ff=16,
        seed=seed,
        **kwargs,
    )
    model.tie()
    return model


def test_adamw_sequence_lowers_loss_and_rejects_bad_policy():
    torch = pytest.importorskip("torch")
    model = _mouth()
    model.to("torch", prefill_query_chunk=4, max_grad_norm=1.0)
    ids = [1, 2, 3, 2, 1]
    before = model.perplexity("alpha beta gamma")
    for _ in range(25):
        model.adamw_sequence(ids, 0.001, weight_decay=0.001, z_loss=1e-4)
    after = model.perplexity("alpha beta gamma")
    assert after < before
    assert model.steps >= 25
    with pytest.raises(ValueError):
        model.adamw_sequence(ids, 0.0)
    with pytest.raises(ValueError):
        model.adamw_sequence([1], 0.01)
    fresh = _mouth()
    with pytest.raises(RuntimeError):
        fresh.adamw_sequence(ids, 0.01)
    assert torch.is_floating_point(model._accel._E)


def test_adamw_moments_survive_snapshot_sync():
    pytest.importorskip("torch")
    model = _mouth()
    model.to("torch", prefill_query_chunk=4, max_grad_norm=1.0)
    ids = [1, 2, 3, 1]
    model.adamw_sequence(ids, 0.01)
    moments = len(model._accel._adam_moments)
    assert moments > 0
    model.snapshot()
    model.adamw_sequence(ids, 0.01)
    assert model._accel._adam_moments
    model.to("torch", prefill_query_chunk=4, max_grad_norm=1.0)
    assert model._accel._adam_moments == {}


def test_byte_adamw_is_deterministic_and_not_serialized():
    config = NeuralLMConfig(hidden_size=8, seed=5)
    first = NumpyRecurrentLM(model_id="edge", config=config)
    second = NumpyRecurrentLM(model_id="edge", config=config)
    corpus = ("ab ab ab", "abab")
    first.train(corpus, epochs=3, learning_rate=0.05, optimizer="adamw", weight_decay=0.01)
    second.train(corpus, epochs=3, learning_rate=0.05, optimizer="adamw", weight_decay=0.01)
    assert first.model_digest == second.model_digest
    assert first.loss(corpus) < NumpyRecurrentLM(model_id="edge", config=config).loss(corpus)
    assert "adam" not in first.to_dict()["parameters"]
    with pytest.raises(NeuralLMError):
        first.train_document("ab", optimizer="lion")


def test_default_byte_sampling_digest_is_unchanged_by_policy_defaults():
    plain = LocalInferenceRequest(prompt="ab", max_output_tokens=4, seed=3)
    explicit = LocalInferenceRequest(
        prompt="ab",
        max_output_tokens=4,
        seed=3,
        temperature=1,
        top_k=0,
        top_p=1,
        min_p=0,
        repetition_penalty=1,
    )
    assert plain.digest == explicit.digest
    shifted = LocalInferenceRequest(prompt="ab", max_output_tokens=4, seed=3, min_p=0.1)
    assert shifted.digest != plain.digest
    model = NumpyRecurrentLM(config=NeuralLMConfig(hidden_size=8, seed=9))
    model.train(("abcabc",), epochs=2, learning_rate=0.08)
    import threading
    base = model.infer(plain, threading.Event())
    again = model.infer(plain, threading.Event())
    assert base.text == again.text
    peaked = model.infer(
        LocalInferenceRequest(prompt="ab", max_output_tokens=4, seed=3, temperature=0.0),
        threading.Event(),
    )
    assert peaked.text


def test_min_p_keeps_only_the_peak_and_preserves_default_digest():
    logits = [0.0, 4.0, 0.2]
    rng = random.Random(1)
    assert sample_logits(logits, rng, min_p=0.9) == 1
    with pytest.raises(ValueError):
        sample_logits(logits, rng, min_p=1.5)
    limits = RuntimeLimits(max_context=32, max_new_tokens=8, max_total_tokens=40)
    config = GenerationConfig(max_new_tokens=4, min_p=0.05).validate(limits=limits, vocab_size=8)
    assert config.to_dict()["min_p"] == 0.05
    historical = GenerationConfig(max_new_tokens=4).validate(limits=limits, vocab_size=8)
    assert "min_p" not in historical.to_dict()
    with pytest.raises(RuntimeContractError):
        GenerationConfig(max_new_tokens=4, min_p=2).validate(limits=limits, vocab_size=8)


def test_speculative_publication_matches_verifier_greedy():
    verifier = _mouth()
    draft = _mouth(norm="rms", ffn_kind="swiglu")
    prefix = verifier._ids("alpha beta")
    published, result = greedy_speculative(verifier, draft, prefix, 5, proposals=3)
    greedy = []
    context = list(prefix)
    for _ in range(5):
        window = context[-verifier.ctx:]
        logits = verifier._logits(window)
        nxt = max(range(len(logits)), key=lambda index: (logits[index], -index))
        greedy.append(nxt)
        context.append(nxt)
    assert list(published) == greedy
    assert result.proposed >= result.accepted_count
    assert 0.0 <= result.acceptance_rate <= 1.0


def test_numpy_policy_min_p_is_deterministic():
    model = NumpyRecurrentLM(config=NeuralLMConfig(hidden_size=6, seed=2))
    request = LocalInferenceRequest(prompt="zz", max_output_tokens=3, seed=4, min_p=1.0)
    import threading
    first = model.infer(request, threading.Event())
    second = model.infer(request, threading.Event())
    assert first.text == second.text
    assert np.isfinite(model.loss(("zz",)))


def test_specialized_calibrate_and_cached_perplexity():
    model = _mouth(norm="rms", ffn_kind="swiglu")
    corpus = ["alpha beta gamma delta", "beta gamma alpha delta", "alpha beta gamma"]
    report = model.specialized_calibrate(corpus, epochs=2, lr=0.03, weight_decay=0.005)
    assert report["calibrated"] == 1
    assert report["final_ppl"] <= report["initial_ppl"]
    ppl_plain = model.perplexity("alpha beta gamma", cached=False)
    ppl_cached = model.perplexity("alpha beta gamma", cached=True)
    assert abs(ppl_plain - ppl_cached) < 1e-6
    gen = model.generate("alpha", n=4, seed=7, min_p=0.5)
    assert isinstance(gen, (list, tuple)) and len(gen) > 0


def test_cooperative_speculative_and_cooperative_gossip():
    from skeleton.cortex.gossip import adaptive_gossip, cooperative_decode, cooperative_logits
    from skeleton.cortex.speculative import cooperative_speculative

    v1 = _mouth(seed=11)
    v2 = _mouth(seed=17)
    draft = _mouth(norm="rms", ffn_kind="swiglu", seed=23)
    corpus = ["alpha beta gamma delta", "alpha beta gamma"]
    v1.fit(corpus, lr=0.04, schedule="cosine")
    v2.fit(corpus, lr=0.02, schedule="cosine")

    prefix = v1._ids("alpha beta")
    published, spec_res = cooperative_speculative([v1, v2], draft, prefix, 4, proposals=2, weights=[0.7, 0.3])
    assert len(published) == 4
    assert spec_res.proposed >= spec_res.accepted_count

    ens_logits = cooperative_logits([v1, v2], prefix, weights=[0.6, 0.4])
    assert len(ens_logits) == v1.V
    decoded = cooperative_decode([v1, v2], "alpha", n=4, seed=3, min_p=0.2)
    assert isinstance(decoded, str) and len(decoded) > 0

    gossip_res = adaptive_gossip(v2, v1, corpus, max_alpha=0.4)
    assert gossip_res["dst_ppl_after"] <= gossip_res["dst_ppl_before"] + 1e-6


def test_fleet_consensus_and_moe_cooperation():
    from skeleton.cortex.hive import fleet_consensus
    from skeleton.cortex.neocortex import JeevesCortex

    p1 = JeevesCortex()
    p2 = JeevesCortex()
    p1.transformer.fit(["steady alpha beta gamma trace", "soulslike ttk poise"], lr=0.04, schedule="cosine")
    p1.sleep.record("steady alpha beta gamma trace", [0.2] * p1.transformer.dim, slack=0.3)
    summary = fleet_consensus([p1, p2], texts=["steady alpha beta gamma trace"])
    assert summary["peers"] == 2
    assert summary["leader_index"] in (0, 1)
    assert summary["pulls"] >= 0

    coop = p1.moe.cooperate([0.2] * p1.transformer.dim)
    assert "gates" in coop and "entropy" in coop
    spoken = p1.cooperative_speak("steady", n=4, seed=2, min_p=0.1)
    assert isinstance(spoken["text"], str) and abs(sum(spoken["weights"]) - 1.0) < 1e-3

    sleep_res = p1.sleep.consolidate(p1, n=2, lr=0.04, prioritized=True)
    assert sleep_res.get("prioritized") is True


def test_accumulator_cosine_and_weight_decay():
    from skeleton.cortex.accum import accumulate_fit

    model = _mouth()
    before = model.perplexity("alpha beta gamma")
    res = accumulate_fit(
        model,
        ["alpha beta gamma delta", "alpha beta gamma"],
        k=2,
        lr=0.05,
        schedule="cosine",
        weight_decay=0.005,
    )
    assert res["schedule"] == "cosine"
    assert res["flushes"] >= 1
    assert model.perplexity("alpha beta gamma") <= before


def test_neural_trainer_adamw_and_native_transformer_policy(tmp_path):
    import hashlib
    import threading
    from datetime import UTC, datetime
    from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
    from skeleton.ai.runtime.inference.native_transformer import NativeTransformerModel
    from skeleton.ai.runtime.training import (
        DataQualityReport,
        DataQualityRule,
        DatasetManifest,
        DatasetRegistry,
        DatasetSplit,
        IngestEnvelope,
        TrainingRepository,
        TrainingRunManifest,
        corpus_digest,
    )
    from skeleton.ai.runtime.training.neural_trainer import NeuralLocalTrainer

    now = datetime(2026, 10, 4, 16, tzinfo=UTC)
    corpus = ("alpha beta", "beta alpha", "alpha beta gamma")
    datasets = DatasetRegistry(tmp_path / "datasets.sqlite3")
    ingest = IngestEnvelope.from_bytes(
        source_id="fixture://adamw-neural",
        payload="\n".join(corpus).encode(),
        parser_version="plain@1",
        classification="internal",
        rights=("training",),
        trusted=True,
        acquired_at=now,
    )
    datasets.register_ingest(ingest)
    dataset = DatasetManifest(
        dataset_id="adamw-fixture",
        version="1",
        splits=(DatasetSplit("train", corpus_digest(corpus), len(corpus)),),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training",),
        retention_class="model-development",
        parser_versions=("plain@1",),
    )
    datasets.register_dataset(dataset)
    datasets.record_quality(
        DataQualityReport.evaluate(
            dataset.digest,
            (DataQualityRule("validity", "valid_fraction", ">=", 1.0),),
            {"valid_fraction": 1.0},
        )
    )
    initial = NeuralLocalTrainer.initialize_model("run-adamw-1", hidden_size=8, seed=7)
    manifest = TrainingRunManifest(
        run_id="run-adamw-1",
        dataset_digest=dataset.digest,
        base_model_digest=initial.model_digest,
        code_digest=hashlib.sha256(b"adamw-code").hexdigest(),
        environment_digest=hashlib.sha256(b"float64-runtime").hexdigest(),
        seed=7,
        hyperparameters={},
        world_size=1,
        parallelism="single",
        resource_budget={"max_steps": 10000, "max_updates": 100, "max_documents": 100},
    )
    runs = TrainingRepository(tmp_path / "runs.sqlite3")
    trainer = NeuralLocalTrainer(datasets, runs)
    trained_model, artifact = trainer.train(
        manifest,
        corpus,
        hidden_size=8,
        epochs=2,
        learning_rate=0.05,
        optimizer="adamw",
        weight_decay=0.01,
        now=now,
    )
    assert artifact.final_loss < artifact.initial_loss
    restored_model, restored_artifact = trainer.load_artifact("run-adamw-1")
    assert restored_model.model_digest == trained_model.model_digest
    assert restored_artifact.training_receipt_digest == artifact.training_receipt_digest

    native_runtime = NativeLLMRuntime(_mouth(seed=3))
    native = NativeTransformerModel(native_runtime, model_id="tiny-native")
    req = LocalInferenceRequest(prompt="alpha", max_output_tokens=3, seed=5, temperature=0.8, min_p=0.2)
    out = native.infer(req, threading.Event())
    assert out.output_tokens >= 1


def test_traffic_splitter_qos_routing_and_recovery():
    from skeleton.distributed.mesh.traffic_splitter import TrafficSplitter

    splitter = TrafficSplitter(rng=random.Random(42))
    splitter.add_backend("fast", weight=100, max_concurrency=2, quality_score=1.0)
    splitter.add_backend("slow", weight=100, max_concurrency=2, quality_score=0.6)

    for _ in range(25):
        splitter.record("fast", latency_ms=15.0, error=False)
        splitter.record("slow", latency_ms=250.0, error=False)

    fast_eff = splitter._backends["fast"].effective_weight(latency_budget_ms=50.0)
    slow_eff = splitter._backends["slow"].effective_weight(latency_budget_ms=50.0)
    assert fast_eff > slow_eff * 2.0

    actions = splitter.auto_rebalance(max_error_rate=0.1, max_latency_ms=100.0)
    assert any(a["backend"] == "slow" and a["reason"] == "high_latency" for a in actions)

    for _ in range(25):
        splitter.record("slow", latency_ms=20.0, error=False)
    rec_actions = splitter.auto_rebalance(max_error_rate=0.1, max_latency_ms=100.0, recover=True)
    assert any(a["backend"] == "slow" and a["reason"] == "recovered" for a in rec_actions)

    b1 = splitter.acquire_route("sess-1")
    b2 = splitter.acquire_route("sess-2")
    assert b1 is not None and b2 is not None
    splitter.release_route(b1, latency_ms=12.0, error=False)
    splitter.release_route(b2, latency_ms=14.0, error=False)


def test_adaptive_ratchet_and_quality_debt_ratchet():
    from skeleton.ai.game_builder.quality_debt import DebtItem, DebtSeverity, QualityDebtLedger
    from skeleton.learning.mirror_room.adversarial import (
        AdaptiveRatchetController,
        AdversarialRatchetPolicy,
    )

    policy = AdversarialRatchetPolicy()
    ctrl = AdaptiveRatchetController(policy)
    base_w, base_s = policy.weighted_gain_threshold(10), policy.strict_metric_gain_threshold(10)
    for idx in range(1, 10):
        ctrl.record_outcome(attempt=idx, accepted=True, observed_weighted_gain=0.002)
    adapt_w, adapt_s = ctrl.thresholds_for_attempt(10)
    assert adapt_w > base_w
    assert adapt_s > base_s

    for idx in range(10, 15):
        ctrl.record_outcome(attempt=idx, accepted=False, observed_weighted_gain=0.0)
    relaxed_w, _ = ctrl.thresholds_for_attempt(15)
    assert relaxed_w >= policy.weighted_gain_threshold(15)

    ledger = QualityDebtLedger(ceiling=12, protected_ceiling=4)
    ledger.add(
        DebtItem(
            debt_id="d1",
            axis="pacing",
            severity=DebtSeverity.MEDIUM,
            description="minor pacing gap",
            evidence_digest="0123456789abcdef0123456789abcdef",
            opened_round=1,
            protected=False,
        )
    )
    res = ledger.adaptive_ratchet(round_index=3, clean_streak=4, target_floor=2)
    assert res["after_ceiling"] < res["before_ceiling"]
    assert res["after_ceiling"] >= ledger.total_score


def test_cortex_self_learn_cycle_gaming_priors_and_capacity_increase():
    from skeleton.cortex.improve import gaming_and_adjacent_corpus
    from skeleton.cortex.neocortex import JeevesCortex
    from skeleton.cortex.port import negotiate_port_protocol
    from skeleton.cortex.production_profile import ENTERPRISE_PROFILES, plan_capacity_escalation

    assert "enterprise" in ENTERPRISE_PROFILES
    assert "sovereign" in ENTERPRISE_PROFILES
    plan = plan_capacity_escalation("legacy", genos_g=6.0, ratchet_streak=8)
    assert plan["escalated"] is True
    assert plan["parameter_scale_ratio"] > 1.0

    corpus = gaming_and_adjacent_corpus()
    assert len(corpus) >= 40

    neo = JeevesCortex()
    for slot, port in neo.slots.items():
        proto = negotiate_port_protocol(port)
        assert proto["compliant"] is True
        assert proto["self_learn_capable"] is True

    priors = neo.apply_gaming_weights(rounds=1)
    assert priors["applied"] == 1
    assert priors["gaming_domains"] >= 15
    assert priors["adjacent_domains"] >= 7

    cycle = neo.self_learn_cycle(rounds=1, apply_gaming=True, grow_on_streak=True)
    assert cycle["ratchet"]["passed"] is True
    assert cycle["ratchet"]["rolled_back"] is False
    assert cycle["G"] >= 1.0
    assert cycle["capacity_upgrade"] is not None
    assert neo.transformer.n_layers >= 3
    assert neo.transformer.lora.rank >= 4


def test_mesh_discovery_hedging_throughput_and_pool_upgrades():
    from skeleton.distributed.mesh.connection_pool import ConnectionPool
    from skeleton.distributed.mesh.request_hedging import RequestHedger
    from skeleton.distributed.mesh.service_discovery import ServiceRegistry
    from skeleton.distributed.mesh.throughput_controller import ThroughputController

    reg = ServiceRegistry()
    reg.register("node-a", "cortex", "10.0.0.1:8000", capabilities=["gaming", "self_learn"])
    reg.register("node-b", "cortex", "10.0.0.2:8000", capabilities=["gaming"])
    reg.heartbeat("node-a", load=0.15, latency_ms=12.0, error_rate=0.0)
    reg.heartbeat("node-b", load=0.75, latency_ms=140.0, error_rate=0.1)
    picked = reg.pick("cortex", strategy="adaptive_qos", preferred_capabilities=["gaming", "self_learn"])
    assert picked is not None and picked["instance_id"] == "node-a"

    hedger = RequestHedger()
    for _ in range(10):
        hedger.record_latency("llm", 10.0)
    out = hedger.execute(
        "llm",
        primary=lambda: (_ for _ in ()).throw(RuntimeError("primary timeout")),
        backup=lambda: "backup-ok",
    )
    assert out["result"] == "backup-ok"
    assert out["hedged"] is True
    assert out["hedge_won"] is True

    tc = ThroughputController()
    for _ in range(5):
        tc.acquire("infer")
        tc.release("infer", latency_ms=25.0, error=False)
    assert tc.current_limit("infer") > 10.0
    assert tc.lane("infer").min_latency_ms == 25.0

    pool = ConnectionPool()
    warmed = pool.warm("db:5432", count=3)
    assert warmed == 3
    chk = pool.checkout("db:5432")
    assert chk["acquired"] is True


