"""Real native candidate learning and heldout qualification regressions."""
from __future__ import annotations

import time
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_checkpoint import portable_model_snapshot,snapshot_digest
from skeleton.ai.training.flgb_training_runtime import DatasetRights,DatasetRevision,digest_json,TrainingContractError
from skeleton.ai.training.contamination_scan import MaterializedExample,OverlapPolicy,scan_materialized_overlap
from skeleton.ai.training.native_retention_evaluation import (
    RetentionCase,RetentionPolicy,corpus_digest,evaluate_retention,
)
from skeleton.ai.training.shadow_native_trainer import ShadowNativeTrainer,ShadowNativeTrainingPolicy
from skeleton.ai.training.shadow_idle_training import ShadowTrainingPaused


def pin(text):
    return sha256(text.encode("utf-8")).hexdigest()


def text_row(text):
    return MaterializedExample(pin(text),text)


def make_runtime():
    return NativeLLMRuntime(TinyTransformer(
        vocab=("alpha","beta","gamma","delta","renderer","shader","mesh","cache",
               "code","test","local","world","hello","again"),dim=8,ctx=24,
        seed=73,n_heads=2,n_layers=2,d_ff=8,
    ))


class Idle:
    def __init__(self,stop_after=None):
        self.polls=0
        self.heartbeats=0
        self.stop_after=stop_after

    def require_idle(self):
        self.polls+=1
        if self.stop_after is not None and self.polls>=self.stop_after:
            raise ShadowTrainingPaused("interactive request")

    def heartbeat(self):
        self.require_idle()
        self.heartbeats+=1


class TeacherRetentionTrainingTests(unittest.TestCase):
    def make_pair(self):
        a=make_runtime()
        b=NativeLLMRuntime.restore(a.checkpoint())
        return a,b

    def test_soft_target_zero_matches_existing_supervised_update(self):
        a,b=self.make_pair()
        ids=list(a.encode("alpha beta").token_ids)
        target=a.encode("gamma").token_ids[0]
        teacher=a.infer_text("alpha beta").logits
        a.model._sgd(ids,target,.01)
        b.model._sgd_soft_target(ids,target,teacher,teacher_weight=0.,lr=.01)
        self.assertEqual(snapshot_digest(portable_model_snapshot(a.model)),
                         snapshot_digest(portable_model_snapshot(b.model)))

    def test_soft_target_weight_one_at_teacher_distribution_no_gradient(self):
        a,b=self.make_pair()
        ids=list(a.encode("alpha beta").token_ids)
        target=a.encode("gamma").token_ids[0]
        teacher=tuple(a.model._logits(ids))
        before=[row[:] for row in b.model.Wout]
        loss=b.model._sgd_soft_target(ids,target,teacher,teacher_weight=1.,lr=.01)
        self.assertGreater(loss,0)
        self.assertEqual(before,b.model.Wout)
        self.assertEqual(b.model.steps,a.model.steps+1)

    def test_nonzero_soft_targets_change_candidate_not_teacher(self):
        a,b=self.make_pair()
        ids=list(a.encode("alpha beta").token_ids)
        target=a.encode("gamma").token_ids[0]
        teacher=a.infer_text("alpha beta").logits
        before=a.model_digest
        b.model._sgd_soft_target(ids,target,teacher,teacher_weight=.25,lr=.05)
        a.assert_model_unchanged()
        self.assertEqual(a.model_digest,before)
        self.assertNotEqual(snapshot_digest(portable_model_snapshot(b.model)),before)

    def test_invalid_soft_target_inputs_rejected_before_mutation(self):
        a,b=self.make_pair()
        ids=list(a.encode("alpha beta").token_ids)
        logits=a.infer_text("alpha beta").logits
        for args,kwargs in (
            ((ids,0,logits[:-1]),dict(teacher_weight=.1,lr=.01)),
            ((ids,0,(float("nan"),)*len(logits)),dict(teacher_weight=.1,lr=.01)),
            (([],0,logits),dict(teacher_weight=.1,lr=.01)),
            ((ids,0,logits),dict(teacher_weight=True,lr=.01)),
            ((ids,0,logits),dict(teacher_weight=.1,lr=0.0)),
        ):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                b.model._sgd_soft_target(*args,**kwargs)
        b.assert_model_unchanged()

    def trainer(self,champion,**policy):
        folder=TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        return ShadowNativeTrainer(champion,corpus_path=lambda _:Path(folder.name)/"unused",
            artifact_directory=folder.name,code_digest=pin("trainer"),
            policy=ShadowNativeTrainingPolicy(**policy))

    def test_real_shadow_batch_distills_and_preserves_champion(self):
        a,b=self.make_pair()
        trainer=self.trainer(a,teacher_retention_ppm=250000,
                             teacher_min_target_probability_ppm=1)
        batch=("alpha beta gamma delta","renderer mesh shader cache")
        steps,soft=trainer._fit_retention_batch(b,batch,Idle())
        expected=sum(len(a.encode(line).token_ids)-1 for line in batch)
        self.assertEqual(steps,expected)
        self.assertEqual(soft,expected)
        self.assertNotEqual(snapshot_digest(portable_model_snapshot(b.model)),a.model_digest)
        a.assert_model_unchanged()

    def test_low_confidence_teacher_uses_hard_target(self):
        a,b=self.make_pair()
        trainer=self.trainer(a,teacher_retention_ppm=250000,
                             teacher_min_target_probability_ppm=1000000)
        n,soft=trainer._fit_retention_batch(b,("alpha beta gamma",),Idle())
        self.assertGreater(n,0)
        self.assertEqual(soft,0)
        a.assert_model_unchanged()

    def test_preempted_shadow_candidate_never_mutates_champion(self):
        a,b=self.make_pair()
        trainer=self.trainer(a,teacher_retention_ppm=250000,
                             teacher_min_target_probability_ppm=1)
        with self.assertRaises(ShadowTrainingPaused):
            trainer._fit_retention_batch(b,("alpha beta gamma delta",),Idle(stop_after=5))
        a.assert_model_unchanged()

    def test_teacher_policy_changes_manifest_identity_only_when_enabled(self):
        a=ShadowNativeTrainingPolicy()
        self.assertEqual(a.digest,replace(a,teacher_min_target_probability_ppm=1).digest)
        self.assertNotEqual(a.digest,replace(a,teacher_retention_ppm=1).digest)
        for value in (True,-1,500001):
            with self.assertRaises(Exception):
                replace(a,teacher_retention_ppm=value)


class MaterializedOverlapTests(unittest.TestCase):
    def scan(self,a,b):
        return scan_materialized_overlap(tuple(text_row(x) for x in a),
                                         tuple(text_row(x) for x in b))

    def test_exact_normalized_and_containment(self):
        held="one two three four five six seven eight nine ten eleven twelve thirteen fourteen"
        for value,rel in ((held,"exact"),(held.upper(),"normalized"),
                          ("intro words "+held+" more ending","contained")):
            result=self.scan((value,),(held,))
            self.assertTrue(result.review_required)
            self.assertEqual(result.findings[0].relation,rel)
            self.assertIn(result.findings[0].as_contract().relation,
                          {"exact","derived","near-duplicate"})

    def test_near_duplicate_and_disjoint(self):
        held="one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
        altered=held+" appendix"
        self.assertTrue(self.scan((altered,),(held,)).review_required)
        self.assertFalse(self.scan(("shader pipeline geometry depth raster",),(held,)).review_required)

    def test_raw_digest_is_required(self):
        with self.assertRaises(TrainingContractError):
            MaterializedExample(pin("original"),"changed")

    def test_deterministic_evidence_and_bounded_identity(self):
        a=("alpha beta gamma","other example source")
        b=("ALPHA BETA GAMMA","different source")
        self.assertEqual(self.scan(a,b).evidence_sha256,
                         self.scan(tuple(reversed(a)),tuple(reversed(b))).evidence_sha256)
        with self.assertRaises(TrainingContractError):
            self.scan((a[0],a[0]),b)

    def test_interrupt_cannot_return_partial_evidence(self):
        def stop():
            raise TimeoutError("stop")
        with self.assertRaises(TimeoutError):
            scan_materialized_overlap((text_row("alpha beta"),),(text_row("gamma delta"),),interrupt=stop)


class NativeRetentionEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.a=make_runtime()
        clone=NativeLLMRuntime.restore(self.a.checkpoint())
        clone.model.fit(("alpha beta gamma","renderer mesh"),lr=.01)
        self.b=NativeLLMRuntime(clone.model)
        self.cases=tuple(RetentionCase(str(i),domain,text,pin(text),i==0)
            for i,(domain,text) in enumerate((
                ("coding","code test alpha"),("coding","test local beta"),
                ("gaming","mesh shader delta"),("gaming","renderer world gamma"),
            )))
        self.rights=DatasetRights("heldout-v1","reviewed-evaluation","allowed",
                                 "operator-owned",("evaluation",),pin("rights"))
        self.dataset=DatasetRevision("heldout-v1",0,corpus_digest(self.cases),
                                      self.rights.digest,pin("approved transform"))
        self.train=(text_row("alpha beta gamma"),text_row("renderer mesh"))
        self.policy=RetentionPolicy(max_steps=32,max_case_tokens=24,
                                     max_case_nll_increase_ppm=1000000,
                                     max_capability_nll_increase_ppm=1000000,
                                     max_critical_top1_loss_ppm=1000000,
                                     max_mean_kl_micronats=20000000)

    def run_evaluation(self,**overrides):
        inventory=frozenset(x.content_sha256 for x in self.train)
        options=dict(dataset=self.dataset,rights=self.rights,
                     expected_baseline_sha256=self.a.model_digest,
                     expected_candidate_sha256=self.b.model_digest,
                     training_item_sha256=inventory,training_examples=self.train,
                     expected_training_inventory_sha256=digest_json(sorted(inventory)),
                     policy=self.policy,deadline=time.monotonic()+30)
        options.update(overrides)
        return evaluate_retention(self.a,self.b,self.cases,**options)

    def test_actual_paired_logits_and_no_promotion_authority(self):
        report=self.run_evaluation()
        self.assertEqual(len(report.observations),4)
        self.assertEqual(len(report.axes),2)
        self.assertEqual(len(report.evidence_sha256),64)
        self.assertEqual(len(report.contamination_evidence_sha256),64)
        self.assertFalse(report.promotion_authorized)
        self.a.assert_model_unchanged()
        self.b.assert_model_unchanged()

    def test_token_budget_holds_before_comparison(self):
        with patch.object(self.a,"infer_sequence",side_effect=AssertionError("unexpected inference")):
            with self.assertRaisesRegex(ValueError,"token work"):
                self.run_evaluation(policy=replace(self.policy,max_steps=1))

    def test_lexical_contamination_blocks_before_inference(self):
        self.train=(text_row(self.cases[0].text.upper()),)
        with patch.object(self.a,"infer_sequence",side_effect=AssertionError("unexpected inference")):
            with self.assertRaisesRegex(ValueError,"lexical contamination"):
                self.run_evaluation()

    def test_incomplete_inventory_not_accepted(self):
        with self.assertRaisesRegex(ValueError,"materialized training inventory"):
            self.run_evaluation(training_examples=self.train[:1])

    def test_heldout_rights_and_model_pin_fail_closed(self):
        for opts in (dict(expected_candidate_sha256="0"*64),
                     dict(rights=replace(self.rights,rights_status="denied")),
                     dict(dataset=replace(self.dataset,content_digest="f"*64))):
            with self.subTest(opts=opts),self.assertRaises(ValueError):
                self.run_evaluation(**opts)

    def test_expired_evaluation_never_runs_graph(self):
        with patch.object(self.a,"infer_sequence",side_effect=AssertionError("unexpected inference")):
            with self.assertRaises(TimeoutError):
                self.run_evaluation(deadline=time.monotonic()-1)

if __name__=="__main__":
    unittest.main()
