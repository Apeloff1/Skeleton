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


def test_cortex_game_creation_finetune_planner_qa_and_closed_loop_build():
    from skeleton.cortex.heads import PacingHead, head_from_snapshot
    from skeleton.cortex.hemispheres import LeftHemisphere, RightHemisphere
    from skeleton.cortex.midbrain import Midbrain
    from skeleton.cortex.neocortex import JeevesCortex
    from skeleton.cortex.pfc import PrefrontalCortex
    from skeleton.distributed.mesh.service_discovery import ServiceRegistry
    from skeleton.distributed.mesh.traffic_splitter import TrafficSplitter
    from skeleton.forge.game_builder import (
        RESULT_FIELDS,
        build_playable_game,
        finetuned_game_creation_hooks,
        public_payload,
    )

    # 1. Verify PacingHead and MoE integration
    ph = PacingHead(dim=8, seed=29)
    vec = [0.2, -0.1, 0.4, 0.3, -0.2, 0.1, 0.5, -0.3]
    loss0 = ph.loss(vec, (0.75, 0.65, 0.85, 0.80))
    for _ in range(10):
        ph.step(vec, (0.75, 0.65, 0.85, 0.80), lr=0.2)
    assert ph.loss(vec, (0.75, 0.65, 0.85, 0.80)) < loss0
    restored_ph = head_from_snapshot(ph.snapshot())
    assert restored_ph.predict(vec) == ph.predict(vec)

    # 2. Verify hemisphere, midbrain, and PFC game-creation domain analyzers
    left = LeftHemisphere()
    math_env = left.analyze_game_math("soulslike extraction ttk elite dread", {"era": "soulslike"})
    assert math_env["era"] == "soulslike"
    assert math_env["enemy_hp"]["trash"] > 0
    assert math_env["fixed_tick"]["hz"] == 60
    assert math_env["economy_equilibrium"]["inflation_guarded"] is True

    right = RightHemisphere()
    spatial_env = right.synthesize_spatial_aesthetic_profile(
        "metroidvania backtrack lock key",
        {"era": "metroidvania"},
    )
    assert spatial_env["level_topology"] == "ability_gated_lattice"
    assert spatial_env["art_scale_ladder"]["allocates_65536_buffer"] is False

    mid = Midbrain()
    stage_route = mid.route_game_stage("compile ttk hp dps sim", stage="prove")
    assert stage_route["primary_tract"] == "left"
    assert stage_route["fire_left"] is True

    pfc = PrefrontalCortex()
    slice_plan = pfc.plan_game_slice("build a soulslike extraction slice", {"era": "soulslike", "genre": "action"})
    assert slice_plan["veto"] is False
    assert "single_authoritative_state_writer" in slice_plan["vertical_slice_gates"]

    # 3. Verify JeevesCortex.finetune_for_game_creation and planner/QA hooks inside build_playable_game
    neo = JeevesCortex()
    ft_report = neo.finetune_for_game_creation(epochs=1, rounds=1, include_az_curricula=True, grow_capacity=False)
    assert ft_report["kind"] == "cortex-game-creation-finetune"
    assert len(ft_report["stages"]) == 4
    assert neo.predict_pacing("soulslike extraction ttk elite dread") is not None

    planner_hook, qa_hook, _ = finetuned_game_creation_hooks(neo, finetune_rounds=0, learn_on_qa=True)
    build_res = build_playable_game(
        "A tight top-down soulslike extraction arena with readable telegraphs",
        era="soulslike",
        playtest_mode="off",
        max_rounds=2,
        planner=planner_hook,
        qa=qa_hook,
    )
    assert build_res["ok"] is True
    prod = build_res["spec"].get("production") or {}
    assert "encounter_mix" in prod
    assert "ttk_envelope" in prod
    assert "fixed_tick_contract" in prod
    assert "art_scale_ladder" in prod
    assert build_res["qa"]["passed"] is True
    assert build_res["qa"]["learning"]["learned"] == 1
    pub = public_payload(build_res)
    for field in RESULT_FIELDS:
        assert field in pub

    # 4. Verify end-to-end build_and_learn_game convenience pipeline
    e2e = neo.build_and_learn_game(
        "Boomer shooter arena with fast movement and armor pickups",
        era="boomer_shooter",
        playtest_mode="off",
    )
    assert e2e["build"]["ok"] is True
    assert e2e["learning"]["learned"] == 1
    assert e2e["learning"]["reward"] > 0.0

    # 5. Verify mesh game-stage routing and service discovery
    reg = ServiceRegistry()
    reg.register(
        "worker-sim",
        "game-forge",
        "10.0.0.10:9000",
        capabilities=["encounter_sim", "left_analytic", "ttk_sim"],
    )
    reg.register(
        "worker-layout",
        "game-forge",
        "10.0.0.11:9000",
        capabilities=["world_layout", "right_gestalt", "room_graph"],
    )
    reg.heartbeat("worker-sim", load=0.2, latency_ms=18.0, error_rate=0.0)
    reg.heartbeat("worker-layout", load=0.2, latency_ms=18.0, error_rate=0.0)
    sim_node = reg.pick_for_game_stage("game-forge", "encounter_sim")
    layout_node = reg.pick_for_game_stage("game-forge", "world_layout")
    assert sim_node is not None and sim_node["instance_id"] == "worker-sim"
    assert layout_node is not None and layout_node["instance_id"] == "worker-layout"

    splitter = TrafficSplitter(rng=random.Random(7))
    splitter.add_backend("stage-fast", weight=100, quality_score=1.0)
    splitter.record("stage-fast", latency_ms=12.0, error=False)
    routed = splitter.route_game_stage("spec_compile", session_id="game-sess-1", remaining_deadline_s=30.0)
    assert routed == "stage-fast"


def test_transformer_redundancies_standby_self_healing_and_backup_inference():
    import threading
    from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
    from skeleton.ai.runtime.inference.native_transformer import NativeTransformerModel
    from skeleton.cortex.gossip import redundant_consensus_decode
    from skeleton.cortex.neocortex import JeevesCortex

    # 1. TinyTransformer standby checkpoint, NaN self-healing, and heavy_task_infer
    primary = _mouth(seed=31)
    backup1 = _mouth(seed=37, norm="rms", ffn_kind="swiglu")
    backup2 = _mouth(seed=41)
    corpus = ["alpha beta gamma delta", "beta gamma alpha"]
    primary.specialized_calibrate(corpus, epochs=2, lr=0.03)
    backup1.specialized_calibrate(corpus, epochs=2, lr=0.03)
    backup2.specialized_calibrate(corpus, epochs=2, lr=0.03)

    chk = primary.checkpoint_redundant_standby()
    assert chk["checkpointed"] == 1
    assert primary.validate_finite_weights()["healthy"] is True

    # Inject a non-finite weight into primary and verify heavy_task_infer self-heals from standby
    primary.layers[0].Wq[0][0] = float("nan")
    assert primary.validate_finite_weights()["healthy"] is False
    heavy_out = primary.heavy_task_infer(
        "alpha beta",
        n=12,
        seed=5,
        backup_models=[backup1, backup2],
        chunk_tokens=4,
    )
    assert heavy_out["is_heavy_task"] is True
    assert heavy_out["repaired_from_standby"] is True
    assert heavy_out["primary_healthy"] is True
    assert heavy_out["chunks_processed"] == 3
    assert len(heavy_out["token_ids"]) == 12

    # If standby is cleared and primary is corrupted, heavy_task_infer fails over to backup1
    primary._standby_snapshot = None
    primary.layers[0].Wq[0][0] = float("nan")
    failover_out = primary.heavy_task_infer(
        "alpha beta",
        n=8,
        seed=5,
        backup_models=[backup1, backup2],
    )
    assert failover_out["used_backup"] is True
    assert failover_out["failover_reason"] == "primary-nonfinite-weights"
    assert len(failover_out["token_ids"]) == 8

    # 2. Quorum consensus decode filters degraded models and tracks agreement
    cons = redundant_consensus_decode([primary, backup1, backup2], "alpha", n=6, seed=3)
    assert cons["healthy_models"] == 2
    assert cons["degraded_models"] == 1
    assert 0.0 < cons["quorum_agreement"] <= 1.0

    # 3. JeevesCortex redundant transformer ring & backup_infer
    neo = JeevesCortex()
    neo.train(epochs=1)
    sync_res = neo.sync_backup_transformer()
    assert sync_res["synced"] == 1
    ring = neo.redundant_transformers()
    assert ring["total_models"] >= 6
    assert ring["quorum_ready"] is True

    bi = neo.backup_infer("soulslike extraction ttk elite dread", n=12, seed=7, consensus=True)
    assert bi["kind"] == "heavy-backup-inference"
    assert isinstance(bi["text"], str)
    assert bi["consensus"]["healthy_models"] >= 3

    # 4. NativeTransformerModel backup_runtime failover
    good_rt = NativeLLMRuntime(backup1)
    bad_lm = _mouth(seed=53)
    bad_rt = NativeLLMRuntime(bad_lm)
    # Mutate bad_lm after NativeLLMRuntime creation so primary triggers RuntimeContractError and fails over to backup_runtime
    bad_lm.E[0][0] += 0.5
    native_with_backup = NativeTransformerModel(bad_rt, model_id="redundant-native", backup_runtime=good_rt)
    req = LocalInferenceRequest(prompt="alpha", max_output_tokens=3, seed=2)
    res = native_with_backup.infer(req, threading.Event())
    assert res.output_tokens >= 1
    assert native_with_backup.backup_failover_count == 1


def test_repetition_automation_shadow_weight_parsing_and_hyperweights():
    from skeleton.cortex.neocortex import JeevesCortex

    neo = JeevesCortex()
    neo.train(epochs=1)

    # 1. Parse shadow weights
    parsed = neo.parse_shadow_weights()
    assert parsed["kind"] == "shadow-weight-parse"
    assert "own" in parsed["slot_metrics"]
    assert len(parsed["shadow_digest"]) == 64
    assert len(parsed["layer_deltas"]) >= 1

    # 2. Create and apply hyperweights
    bundle = neo.create_hyperweights(alpha=0.30, rank=4)
    assert bundle["kind"] == "hyperweight-bundle"
    assert bundle["schema_version"] == "skeleton.cortex.hyperweights.v1"
    assert len(bundle["bundle_digest"]) == 64
    assert len(bundle["layer_hyper_projections"]) == neo.transformer.n_layers

    applied = neo.apply_hyperweights(bundle, blend=0.20)
    assert applied["kind"] == "hyperweight-apply"
    assert applied["applied"] == 1
    assert applied["final_ppl"] <= applied["before_ppl"] * 1.05

    # 3. Run full spaced-repetition training automation
    auto = neo.run_repetition_automation(cycles=2, top_k=6, synthesize_hyperweights=True)
    assert auto["kind"] == "repetition-training-automation"
    assert auto["cycles_executed"] == 2
    assert auto["total_repetitions"] >= 12
    assert auto["tracked_cards"] >= 6
    assert auto["hyperweights"]["schema_version"] == "skeleton.cortex.hyperweights.v1"


def test_traffic_hardening_circuit_breaker_priority_shedding_and_heavy_hedging():
    from skeleton.distributed.mesh.connection_pool import ConnectionPool
    from skeleton.distributed.mesh.deduplicator import Deduplicator
    from skeleton.distributed.mesh.request_hedging import RequestHedger
    from skeleton.distributed.mesh.throughput_controller import ThroughputController
    from skeleton.distributed.mesh.traffic_splitter import TrafficSplitter

    # 1. TrafficSplitter circuit breaker & priority load shedding & heavy task routing
    splitter = TrafficSplitter(rng=random.Random(11))
    splitter.add_backend(
        "primary-a",
        weight=100,
        max_concurrency=4,
        circuit_trip_threshold=3,
        circuit_cooldown_ms=50.0,
    )
    splitter.add_backend(
        "backup-b",
        weight=90,
        max_concurrency=4,
        circuit_trip_threshold=3,
        circuit_cooldown_ms=50.0,
    )

    heavy_pair = splitter.route_heavy_task("sess-heavy")
    assert heavy_pair["primary"] == "primary-a"
    assert heavy_pair["backup"] == "backup-b"
    assert heavy_pair["backup_available"] is True

    # Trip circuit on primary-a after 3 consecutive errors
    for _ in range(3):
        splitter.record("primary-a", latency_ms=80.0, error=True)
    assert splitter._backends["primary-a"].circuit_state == "open"
    assert splitter.route() == "backup-b"

    # Priority shedding on backup-b when 3/4 slots (75%) are occupied
    splitter._backends["backup-b"].in_flight = 3
    assert splitter.route(priority="background") is None
    assert splitter.route(priority="critical") == "backup-b"
    splitter._backends["backup-b"].in_flight = 0

    # 2. RequestHedger execute_heavy multi-backup cascade
    hedger = RequestHedger()
    heavy_res = hedger.execute_heavy(
        "heavy_infer",
        primary=lambda: (_ for _ in ()).throw(RuntimeError("primary OOM")),
        backups=[
            lambda: (_ for _ in ()).throw(RuntimeError("backup-1 busy")),
            lambda: "backup-2-recovered",
        ],
    )
    assert heavy_res["result"] == "backup-2-recovered"
    assert heavy_res["used_backup"] is True
    assert heavy_res["backup_tier"] == 2

    # 3. ThroughputController priority-aware admission
    tc = ThroughputController()
    lane = tc.lane("cortex")
    lane.limit = 4.0
    lane.inflight = 3  # 75% utilization
    assert tc.acquire("cortex", priority="background") is False
    assert tc.acquire("cortex", priority="heavy") is True

    # 4. ConnectionPool health check & Deduplicator bounded eviction
    pool = ConnectionPool(health_check=lambda c: not c.broken)
    pool.warm("model-srv:9000", count=2)
    pool._pool("model-srv:9000").available[0].broken = True
    chk = pool.checkout("model-srv:9000")
    assert chk["acquired"] is True
    assert len(pool._pool("model-srv:9000").available) == 0

    dedup = Deduplicator(retention_s=3600.0, max_entries=3)
    for idx in range(5):
        dedup.execute(f"k-{idx}", {"id": idx}, lambda i=idx: f"ok-{i}")
    assert dedup.card()["records"] <= 3
    assert dedup._evictions >= 2


def test_console_and_rom_asset_training_and_budget_validation():
    from skeleton.cortex.improve import CONSOLE_ROM_ASSET_ASPECTS, console_rom_asset_corpus
    from skeleton.cortex.neocortex import JeevesCortex
    from skeleton.forge.hardware import (
        CONSOLE_ROM_PROFILES,
        compile_console_rom_envelope,
        get_console_rom_profile,
        list_console_rom_profiles,
        validate_rom_asset_budget,
    )

    profiles = list_console_rom_profiles()
    assert len(profiles) >= 14
    assert "gb_dmg_rom" in CONSOLE_ROM_PROFILES
    assert "nes_rom" in CONSOLE_ROM_PROFILES
    assert "snes_rom" in CONSOLE_ROM_PROFILES
    assert "genesis_rom" in CONSOLE_ROM_PROFILES
    assert "ps1_iso" in CONSOLE_ROM_PROFILES
    assert "n64_z64" in CONSOLE_ROM_PROFILES

    gb_prof = get_console_rom_profile("gameboy")
    assert gb_prof["key"] == "gb_dmg_rom"
    assert gb_prof["bytes_per_8x8_tile"] == 16
    assert gb_prof["six_tile_symbol_bytes"] == 96
    assert gb_prof["linker_bank0_symbol_addr"] == "00:0200"

    valid_gb = validate_rom_asset_budget(
        "gb_dmg_rom",
        {"tile_count": 6, "tile_bytes": 96, "sprites_total": 40, "sprites_per_scanline": 10, "palette_colors": 4},
    )
    assert valid_gb["valid"] is True

    invalid_gb = validate_rom_asset_budget(
        "gb_dmg_rom",
        {"tile_count": 6, "tile_bytes": 80, "sprites_total": 48, "allocated_bitmap_dim": 65536},
    )
    assert invalid_gb["valid"] is False
    assert len(invalid_gb["violations"]) == 3

    invalid_n64 = validate_rom_asset_budget("n64_z64", {"texture_bytes": 8192})
    assert invalid_n64["valid"] is False

    env = compile_console_rom_envelope("snes")
    assert env["profile_key"] == "snes_rom"
    assert env["rom_extension"] == ".sfc"
    assert len(env["palette"]) >= 4

    rom_corpus = console_rom_asset_corpus()
    assert len(CONSOLE_ROM_ASSET_ASPECTS) >= 14
    assert len(rom_corpus) >= 30

    neo = JeevesCortex()
    rom_train = neo.train_console_rom_assets(rounds=1)
    assert rom_train["trained"] == 1
    assert rom_train["console_count"] >= 14
    assert rom_train["ingested_exemplars"] >= 14
    recall_gb = neo.recall("gb_dmg_rom Game Boy 8bit rom asset tile sprite palette")
    assert len(recall_gb["hits"]) >= 1


def test_hyperlora_ties_slerp_model_soup_constrained_jacobi_dream_dpo_and_zero_shot_blueprint():
    from skeleton.cortex.gossip import slerp_vectors, task_vector_soup_merge
    from skeleton.cortex.lora import ContextConditionedLoRA, HyperLoRABank
    from skeleton.cortex.neocortex import JeevesCortex
    from skeleton.cortex.speculative import GrammarBudgetLogitProcessor, lookahead_jacobi_decode
    from skeleton.distributed.mesh.deduplicator import Deduplicator
    from skeleton.distributed.mesh.throughput_controller import ThroughputController
    from skeleton.distributed.mesh.traffic_splitter import TrafficSplitter
    from skeleton.forge.hardware import synthesize_rom_tile_bank

    # 1. ContextConditionedLoRA & HyperLoRABank dynamic weight modulation
    lm = _mouth(seed=71)
    hbank = HyperLoRABank(ctx_dim=8, rank=2, alpha=4.0, seed=13)
    att = hbank.attach(lm)
    assert "Wout" in att["attached"]
    gates_a = hbank.bind_context([1.0, -0.5, 0.25, 0.8, -0.2, 0.1, 0.4, -0.9])
    gates_b = hbank.bind_context([-1.0, 0.5, -0.25, -0.8, 0.2, -0.1, -0.4, 0.9])
    assert gates_a["Wout"] != gates_b["Wout"]
    fit_res = hbank.fit_contextual(
        lm,
        [
            ([1.0, 0.0, 0.5, 0.2, 0.0, 0.0, 0.0, 0.0], "alpha beta gamma delta"),
            ([0.0, 1.0, -0.5, 0.2, 0.0, 0.0, 0.0, 0.0], "beta gamma alpha delta"),
        ],
        lr=0.05,
    )
    assert fit_res["steps"] > 0
    static_bank = hbank.compile_static_bank([1.0, 0.0, 0.5, 0.2, 0.0, 0.0, 0.0, 0.0])
    assert "Wout" in static_bank.adapters
    restored_hbank = HyperLoRABank.from_snapshot(hbank.snapshot())
    assert restored_hbank.to_dict()["hyper_steps"] == hbank.to_dict()["hyper_steps"]

    # 2. TIES-Merging + SLERP Model Soup across specialist transformers
    slerp_mid = slerp_vectors([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], 0.5)
    assert len(slerp_mid) == 3
    m_base = _mouth(seed=81)
    m_spec1 = _mouth(seed=83)
    m_spec2 = _mouth(seed=89)
    corpus = ["alpha beta gamma delta", "gamma delta alpha beta"]
    m_base.specialized_calibrate(corpus, epochs=1, lr=0.02)
    m_spec1.specialized_calibrate(corpus, epochs=3, lr=0.04)
    m_spec2.specialized_calibrate(corpus, epochs=3, lr=0.04)
    soup = task_vector_soup_merge(m_base, [m_spec1, m_spec2], corpus=corpus, density=0.75, scaling_lambda=0.85)
    assert soup["kind"] == "ties-slerp-model-soup"
    assert soup["donor_count"] == 2
    assert soup["ppl_after"] <= soup["ppl_before"] * 1.02

    # 3. Grammar & Budget Constrained Generation + Lookahead Jacobi Speculative Decode
    c_out = m_spec1.constrained_generate(
        "alpha",
        n=6,
        seed=11,
        banned_tokens=["epsilon"],
        required_tokens=["beta", "gamma"],
        no_repeat_ngram_size=2,
    )
    assert "epsilon" not in c_out["tokens"]
    assert c_out["all_required_satisfied"] is True

    proc = GrammarBudgetLogitProcessor(m_spec1.itos, required_tokens=["beta"], banned_tokens=["epsilon"])
    jacobi = lookahead_jacobi_decode(
        m_spec1,
        [m_spec2, m_base],
        m_spec1._ids("alpha beta"),
        8,
        lookahead_window=4,
        max_jacobi_iters=3,
        logit_processor=proc,
    )
    assert len(jacobi["token_ids"]) == 8
    assert jacobi["proposed"] >= 8
    assert "epsilon" not in jacobi["text"].split()

    # 4. Procedural Console/ROM Tile, Palette, OAM & PSG Audio Synthesizer
    gb_tiles = synthesize_rom_tile_bank("gb_dmg_rom", tile_count=6, seed=42, pattern="hero_crest")
    assert gb_tiles["total_tile_bytes"] == 96
    assert gb_tiles["bytes_per_8x8_tile"] == 16
    assert gb_tiles["linker_bank0_symbol"] == "00:0200"
    assert gb_tiles["budget_validation"]["valid"] is True
    assert len(gb_tiles["oam_table"]) == 6

    snes_tiles = synthesize_rom_tile_bank("snes_rom", tile_count=8, seed=42, pattern="boss_sigil")
    assert snes_tiles["total_tile_bytes"] == 256
    assert snes_tiles["bytes_per_8x8_tile"] == 32
    assert snes_tiles["budget_validation"]["valid"] is True

    # 5. Cortex Dreaming, DPO Alignment, Model Soup, and Zero-Shot Blueprint Compiler
    neo = JeevesCortex()
    neo.train(epochs=1)
    dream_out = neo.dream_cycle(dreams=4, lr=0.04)
    assert dream_out["kind"] == "counterfactual-dreaming"
    assert dream_out["dreamed"] == 4
    assert dream_out["accepted_dreams"] >= 1

    dpo_out = neo.dpo_align(
        "soulslike extraction",
        "ttk elite dread",
        "unk unk unk",
        chosen_mix=(3.0, 2.0, 1.0),
        rejected_mix=(8.0, 0.0, 0.0),
    )
    assert dpo_out["steps"] == 1
    assert "dpo_loss" in dpo_out

    soup_neo = neo.merge_model_soup()
    assert soup_neo["kind"] == "ties-slerp-model-soup"

    bp1 = neo.compile_zero_shot_blueprint(
        "soulslike extraction ttk elite dread",
        console_target="gb_dmg_rom",
        genre="soulslike",
        tile_count=6,
    )
    assert bp1["schema_version"] == "skeleton.cortex.zero_shot_blueprint.v1"
    assert bp1["cache_hit"] is False
    assert bp1["rom_assets"]["total_tile_bytes"] == 96
    bp2 = neo.compile_zero_shot_blueprint(
        "soulslike extraction ttk elite dread",
        console_target="gb_dmg_rom",
        genre="soulslike",
        tile_count=6,
    )
    assert bp2["cache_hit"] is True
    assert bp2["blueprint_digest"] == bp1["blueprint_digest"]

    # 6. Predictive Brownout Forecasting, Batch Coalescing, and Speculative Prefetch
    splitter = TrafficSplitter()
    splitter.add_backend("steady", weight=100)
    splitter.add_backend("spiking", weight=100)
    for lat in (40.0, 75.0, 110.0, 145.0):
        splitter.record("spiking", latency_ms=lat)
        splitter.record("steady", latency_ms=18.0)
    forecast = splitter.forecast_brownout(latency_budget_ms=100.0, horizon_steps=3)
    assert "spiking" in forecast["at_risk_backends"]
    assert "steady" in forecast["healthy_headroom_backends"]

    tc = ThroughputController()
    coal = tc.execute_coalesced_batch("inference", [1, 2, 3, 4, 5], lambda chunk: [x * 2 for x in chunk], max_batch_size=2)
    assert coal["executed"] is True
    assert coal["batches_run"] == 3
    assert coal["results"] == [2, 4, 6, 8, 10]

    dedup = Deduplicator()
    dedup.execute("stage:1", {"brief": "rpg"}, lambda: {"ok": 1})
    dedup.execute("stage:2", {"brief": "rpg"}, lambda: {"ok": 2})
    assert dedup.predict_next_key("stage:1") == "stage:2"
    pre = dedup.speculative_prefetch("stage:3", {"brief": "rpg"}, lambda: {"ok": 3})
    assert pre["prefetched"] is True
    replay = dedup.execute("stage:3", {"brief": "rpg"}, lambda: {"ok": 999})
    assert replay["replay"] is True
    assert replay["response"] == {"ok": 3}
