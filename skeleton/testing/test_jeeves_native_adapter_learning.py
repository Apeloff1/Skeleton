"""Actual CPU adapter gradients, candidate folding and fenced worker integration."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_checkpoint import portable_model_snapshot
from skeleton.ai.training.flgb_training_runtime import digest_json
from skeleton.ai.training.native_adapter_learning import (
    NativeAdapterPolicy, fit_native_output_adapter, _factor_gradient,
    _gradient_mix, _update, _delta_norm, _project_radius, _OnlineSensitivity,
)
from skeleton.ai.training.shadow_idle_training import ShadowIdleTrainingWorker, ShadowTrainingPaused
from skeleton.ai.training.shadow_native_trainer import ShadowNativeTrainer,ShadowNativeTrainingPolicy
from skeleton.ai.training.shadow_weight_intake import ShadowKnowledge,ShadowKnowledgeQueue
from skeleton.ai.training.shadow_weight_ledger import ShadowWeightLedger
from skeleton.ai.training.shadow_weights import ShadowWeightError,SourceAttestation
from skeleton.cortex.attn import softmax
from skeleton.cortex.lora import LoRA,LoRABank
from skeleton.cortex.transformer import TinyTransformer


def pin(text):
    return sha256(text.encode("utf-8")).hexdigest()


def runtime():
    return NativeLLMRuntime(TinyTransformer(
        vocab=("alpha","beta","gamma","delta","hello","world","render","mesh","shader","code","test","local"),
        dim=8,ctx=24,n_heads=2,n_layers=2,d_ff=8,seed=61,
    ))


CORPUS=("alpha beta gamma delta alpha beta gamma delta",
        "render mesh shader code test local hello world",
        "alpha beta gamma delta alpha beta gamma delta")


def policy(**kwargs):
    return replace(NativeAdapterPolicy(initial_rank=1,maximum_rank=4,
                    rank_step=1,plateau_window=4,plateau_min_gain_ppm=1_000_000,
                    maximum_steps=128,maximum_prefix_tokens=24,
                    delta_radius_ppm=50000),**kwargs)


class AdapterMathTests(unittest.TestCase):
    def adapter(self):
        a=LoRA(3,4,rank=2,alpha=2.,seed=4)
        a.B=[[.05,.1],[-.1,.2],[.15,-.05]]
        return a

    def test_factor_gradient_agrees_with_finite_differences(self):
        adapter=self.adapter()
        y=[.7,-.4,.1,.2]
        baseline=[.1,.3,-.2]
        p=softmax(adapter.apply(baseline,y))
        gradient=_factor_gradient(adapter,y,[p[i]-float(i==1) for i in range(3)])
        def loss():
            return -math.log(softmax(adapter.apply(baseline,y))[1])
        eps=1e-6
        idx=0
        for matrix in (adapter.A,adapter.B):
            for row in matrix:
                for j in range(len(row)):
                    old=row[j]
                    row[j]=old+eps
                    a=loss()
                    row[j]=old-eps
                    b=loss()
                    row[j]=old
                    self.assertAlmostEqual(gradient[idx],(a-b)/(2*eps),places=7)
                    idx+=1

    def test_existing_lora_returns_gradient_from_preupdate_revision(self):
        adapter=self.adapter()
        y=[.5,-.2,.3,.1]
        dy=[.7,.2,-.9]
        original=adapter.snapshot()
        eps=1e-6
        expected=[]
        for j in range(len(y)):
            plus=y[:];minus=y[:]
            plus[j]+=eps;minus[j]-=eps
            a=sum(x*g for x,g in zip(adapter.delta(plus),dy))
            b=sum(x*g for x,g in zip(adapter.delta(minus),dy))
            expected.append((a-b)/(2*eps))
        actual=adapter.step(y,dy,.1)
        for observed,target in zip(actual,expected):
            self.assertAlmostEqual(observed,target,places=7)
        self.assertNotEqual(original,adapter.snapshot())

    def test_existing_lora_uses_adapted_logits_for_training(self):
        model=runtime().model
        bank=LoRABank(rank=2,alpha=2.0,seed=4)
        bank.attach(model,targets=("Wout",))
        adapter=bank.adapters["Wout"]
        adapter.B=[[float(i+1)*.1,-.15] for i in range(model.V)]
        ids=model._ids("alpha beta")
        hidden,_=model._forward(ids[:1])
        y=hidden[-1]
        p=softmax(adapter.apply(model._unembed(y),y))
        expected=[prob-float(i==ids[1]) for i,prob in enumerate(p)]
        with patch.object(adapter,"step",wraps=adapter.step) as actual:
            self.assertEqual(bank.fit_output(model,("alpha beta",),lr=.01),1)
        self.assertEqual(actual.call_args.args[1],expected)

    def test_retention_priority_projects_opposing_gradient(self):
        a=[-2.,1.]
        b=[1.,0.]
        mixed,projected=_gradient_mix(a,b,weight=.25,clip=100.,project=True)
        self.assertTrue(projected)
        self.assertEqual(mixed,[.25,.75])
        unconstrained,_=_gradient_mix(a,b,weight=.25,clip=100.,project=False)
        self.assertLess(unconstrained[0],0)

    def test_aligned_gradient_keeps_original_weighted_update(self):
        mixed,projected=_gradient_mix([1.,2.],[2.,1.],weight=.25,clip=100.,project=True)
        self.assertFalse(projected)
        self.assertEqual(mixed,[1.25,1.75])

    def test_gradient_norm_clips_and_rejects_nonfinite(self):
        grad,_=_gradient_mix([3.,4.],[0.,0.],weight=0.,clip=1.,project=True)
        self.assertAlmostEqual(math.hypot(*grad),1.)
        with self.assertRaises(ValueError):
            _gradient_mix([float("nan")],[0.],weight=0.,clip=1.,project=True)

    def test_update_is_simultaneous_and_nonfinite_fails_before_commit(self):
        adapter=self.adapter()
        before=adapter.snapshot()
        with self.assertRaises(ValueError):
            _update(adapter,[float("inf")]*14,.1)
        self.assertEqual(adapter.snapshot(),before)
        _update(adapter,[.5]*14,.1)
        for matrix,key in ((adapter.A,"A"),(adapter.B,"B")):
            for row,old in zip(matrix,before[key]):
                self.assertEqual(row,[v-.05 for v in old])

    def test_weighted_gram_norm_matches_dense_reference(self):
        a=self.adapter()
        r=[1.,2.,3.]
        c=[2.,3.,1.,4.]
        dense=[[a.scale*sum(a.B[i][k]*a.A[k][j] for k in range(a.rank))
                for j in range(a.in_dim)] for i in range(a.out_dim)]
        self.assertAlmostEqual(_delta_norm(a),math.sqrt(sum(x*x for row in dense for x in row)))
        self.assertAlmostEqual(_delta_norm(a,r,c),
            math.sqrt(sum(x*x*r[i]*c[j] for i,row in enumerate(dense) for j,x in enumerate(row))))

    def test_weighted_trust_region_projects_dense_equivalent_delta(self):
        a=self.adapter()
        r=[1.,2.,3.]
        c=[2.,3.,1.,4.]
        radius=_delta_norm(a,r,c)/4
        self.assertTrue(_project_radius(a,radius,r,c))
        self.assertLessEqual(_delta_norm(a,r,c),radius*(1+1e-9))
        self.assertLessEqual(_delta_norm(a),radius*(1+1e-9))

    def test_sensitivity_is_data_dependent_and_strength_zero_is_identity(self):
        s=_OnlineSensitivity(3,2,1.0)
        s.observe([.5,.4,.1],[2.,0.])
        rows,cols=s.weights()
        self.assertGreater(rows[0],rows[2])
        self.assertEqual(cols,[2.,1.])
        zero=_OnlineSensitivity(3,2,0.)
        zero.observe([.5,.4,.1],[2.,0.])
        self.assertEqual(zero.weights(),([1.]*3,[1.]*2))


class NativeAdapterTests(unittest.TestCase):
    def fit(self,candidate,**kwargs):
        return fit_native_output_adapter(candidate,CORPUS,policy=policy(**kwargs),
            expected_base_digest=candidate.model_digest,interrupt=lambda:None)

    def test_real_adaptation_preserves_backbone_and_changes_output(self):
        champion=runtime()
        candidate=NativeLLMRuntime.restore(champion.checkpoint())
        before=portable_model_snapshot(candidate.model)
        report=self.fit(candidate)
        after=portable_model_snapshot(candidate.model)
        self.assertNotEqual(before["Wout"],after["Wout"])
        for key in before:
            if key not in {"Wout","steps","fitted"}:
                self.assertEqual(before[key],after[key],key)
        self.assertEqual(report.base_model_digest,champion.model_digest)
        self.assertEqual(report.optimizer_steps,21)
        self.assertGreater(report.expansions,0)
        self.assertGreater(report.final_rank,report.initial_rank)
        self.assertLessEqual(report.trainable_parameters,4*(candidate.model.V+candidate.model.dim))
        self.assertLessEqual(report.delta_norm_ppm,50000)
        self.assertLessEqual(report.sensitivity_norm_ppm,50000)
        self.assertGreaterEqual(report.sensitivity_norm_ppm,report.delta_norm_ppm)
        self.assertEqual(report.merged_projection_digest,digest_json(after["Wout"]))
        champion.assert_model_unchanged()
        rebuilt=NativeLLMRuntime(candidate.model)
        self.assertNotEqual(rebuilt.model_digest,champion.model_digest)
        result=rebuilt.infer_text("alpha beta")
        self.assertEqual(len(result.logits),candidate.model.V)

    def test_exact_deterministic_folding_and_receipt(self):
        champion=runtime()
        a=NativeLLMRuntime.restore(champion.checkpoint())
        b=NativeLLMRuntime.restore(champion.checkpoint())
        x,y=self.fit(a),self.fit(b)
        self.assertEqual(x,y)
        self.assertEqual(a.model.Wout,b.model.Wout)

    def test_tied_output_matrix_rejected_before_mutation(self):
        m=runtime().model
        m.tie()
        candidate=NativeLLMRuntime(m)
        with self.assertRaisesRegex(ValueError,"untied"):
            self.fit(candidate)
        candidate.assert_model_unchanged()

    def test_rank_work_projection_and_step_budget_denials_are_precommit(self):
        for overrides in ({"maximum_rank":9},
                          {"factor_budget":2},
                          {"maximum_factor_work":1},
                          {"maximum_projection_parameters":1},
                          {"maximum_steps":1},
                          {"maximum_attention_work":1},
                          {"maximum_prefix_tokens":8}):
            candidate=runtime()
            with self.subTest(overrides=overrides),self.assertRaises(ValueError):
                self.fit(candidate,**overrides)
            candidate.assert_model_unchanged()

    def test_preemption_discards_unmerged_factors(self):
        candidate=runtime()
        def stop(*_args):
            raise ShadowTrainingPaused("preempt")
        with patch("skeleton.ai.training.native_adapter_learning._update",side_effect=stop):
            with self.assertRaises(ShadowTrainingPaused):
                self.fit(candidate)
        candidate.assert_model_unchanged()

    def test_wrong_base_rejected(self):
        candidate=runtime()
        with self.assertRaisesRegex(ValueError,"identity"):
            fit_native_output_adapter(candidate,CORPUS,policy=policy(),
                    expected_base_digest="0"*64,interrupt=lambda:None)
        candidate.assert_model_unchanged()

    def test_policy_manifest_binds_exact_learning_contract(self):
        default=ShadowNativeTrainingPolicy()
        special=replace(default,adapter_policy=policy())
        self.assertNotEqual(default.digest,special.digest)
        self.assertNotEqual(special.digest,replace(special,
            adapter_policy=policy(fisher_strength_ppm=0)).digest)
        for overrides in ({"teacher_retention_ppm":100000},
                          {"maximum_steps":1},
                          {"learning_rate_ppm":1000}):
            with self.subTest(overrides=overrides),self.assertRaises(ShadowWeightError):
                replace(special,**overrides)

    def test_real_durable_worker_stages_candidate_without_activating(self):
        champion=runtime()
        raw="\n".join(CORPUS)
        with TemporaryDirectory() as folder:
            root=Path(folder)
            corpus=root/"corpus.txt"
            corpus.write_text(raw,encoding="utf-8")
            sources=tuple(SourceAttestation("source-"+str(i),"root-"+str(i),
                pin("source bytes "+str(i)),pin("rights "+str(i)),
                "2026-11-01T00:00:00Z",990000,True) for i in range(3))
            item=ShadowKnowledge("adapter-fixture",pin(raw),champion.model_digest,
                "local-learning",950000,900000,"2026-11-01T00:00:00Z",sources)
            queue=ShadowKnowledgeQueue(root/"intake.sqlite")
            ledger=ShadowWeightLedger(root/"weights.sqlite",initial_model_digest=champion.model_digest)
            self.assertEqual(queue.enqueue(item).disposition,"training-ready")
            trainer=ShadowNativeTrainer(champion,corpus_path=lambda _:corpus,
                artifact_directory=root/"candidates",code_digest=pin("adapter-code"),
                policy=ShadowNativeTrainingPolicy(adapter_policy=policy()))
            worker=ShadowIdleTrainingWorker(queue,ledger,worker_id="adapter-worker",
                is_idle=lambda:True,trainer=trainer)
            receipt=worker.run_once()
            self.assertEqual(receipt.disposition,"staged")
            checkpoint_raw=Path(receipt.checkpoint_path).read_bytes()
            restored=NativeLLMRuntime.restore_json(checkpoint_raw)
            import json
            evidence_path=Path(receipt.learning_evidence_path)
            evidence_raw=evidence_path.read_bytes()
            evidence=json.loads(evidence_raw)
            self.assertEqual(evidence_path.name,
                             sha256(evidence_raw).hexdigest()+".adapter-evidence.json")
            self.assertEqual(evidence["candidate_checkpoint_bytes_sha256"],
                             sha256(checkpoint_raw).hexdigest())
            self.assertEqual(evidence["candidate_model_digest"],restored.model_digest)
            self.assertEqual(evidence["report"]["base_model_digest"],champion.model_digest)
            self.assertFalse(evidence["promotion_authorized"])
            self.assertNotEqual(restored.model_digest,champion.model_digest)
            self.assertEqual(restored.model.E,champion.model.E)
            self.assertNotEqual(restored.model.Wout,champion.model.Wout)
            champion.assert_model_unchanged()
            import sqlite3
            with sqlite3.connect(root/"weights.sqlite") as db:
                active=db.execute("SELECT value FROM shadow_meta WHERE key='active_model_digest'").fetchone()[0]
            self.assertEqual(active,champion.model_digest)

if __name__=="__main__":
    unittest.main()
