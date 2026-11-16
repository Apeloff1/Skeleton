"""Packed codec arithmetic and real paired native graph precision trials."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import math
import struct
import time
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_checkpoint import portable_model_snapshot
from skeleton.ai.training.contamination_scan import MaterializedExample
from skeleton.ai.training.flgb_training_runtime import DatasetRevision,DatasetRights,digest_json
from skeleton.ai.training.native_retention_evaluation import RetentionCase,RetentionPolicy,corpus_digest
from skeleton.ai.training.native_precision_calibration import (
    PackedBlock,pack_block,PrecisionPolicy,calibrate_native_precision,
)
from skeleton.cortex.transformer import TinyTransformer


def pin(text):
    return sha256(text.encode("utf-8")).hexdigest()


class PrecisionCodecTests(unittest.TestCase):
    def test_roundtrip_odd_blocks_and_deterministic_exact_byte_count(self):
        values=[-1.,-.7,-.2,0.,.15,.4,1.]
        for bits in (4,6,8):
            with self.subTest(bits=bits):
                block=pack_block(values,bits)
                self.assertEqual(block,pack_block(values,bits))
                self.assertEqual(block.bytes_used,4+(len(values)*bits+7)//8)
                scale=struct.unpack(">f",block.scale_f32)[0]
                for x,y in zip(values,block.decode()):
                    self.assertLessEqual(abs(x-y),scale/2+1e-7)
                self.assertEqual(block.decode()[3],0.)

    def test_zero_block_and_negative_values(self):
        for bits in (4,6,8):
            self.assertEqual(pack_block([0.]*5,bits).decode(),[0.]*5)
            block=pack_block([-3.,-2.,-1.],bits)
            self.assertTrue(all(x<0 for x in block.decode()))

    def test_noncanonical_padding_reserved_code_and_invalid_scale(self):
        scale=struct.pack(">f",1.)
        for args in ((4,1,scale,bytes([0xf0])),
                     (4,1,scale,bytes([0x0f])),
                     (6,1,scale,bytes([0x3f])),
                     (8,1,scale,bytes([0xff])),
                     (4,1,struct.pack(">f",0.),bytes([0x01])),
                     (4,1,scale,b""),(4,1,scale,b"\0\0")):
            with self.subTest(args=args),self.assertRaises(ValueError):
                PackedBlock(*args)

    def test_nonfinite_and_unrepresentable_scale_rejected(self):
        for values in ([float("nan")],[float("inf")],[1e-300],[1e300],[]):
            with self.subTest(values=values),self.assertRaises(ValueError):
                pack_block(values,4)
        with self.assertRaises(ValueError):
            pack_block([1.],5)


class NativePrecisionCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.base=NativeLLMRuntime(TinyTransformer(
            vocab=("alpha","beta","gamma","delta","mesh","shader","render","code","test","local"),
            dim=8,ctx=24,n_heads=2,n_layers=2,d_ff=8,seed=51))
        self.cases=tuple(RetentionCase("case-"+str(i),"native",text,pin(text),i==0)
            for i,text in enumerate(("code test alpha","mesh shader delta","render local beta")))
        self.rights=DatasetRights("calibration","source-v1","allowed","operator-owned",
                                  ("calibration","evaluation"),pin("rights"))
        self.dataset=DatasetRevision("calibration",0,corpus_digest(self.cases),
                                     self.rights.digest,pin("calibration-transform"))
        self.training=(MaterializedExample(pin("alpha beta gamma"),"alpha beta gamma"),)
        self.inventory=frozenset(x.content_sha256 for x in self.training)
        self.final=frozenset((pin("independent final undisclosed text"),))
        self.precision=PrecisionPolicy(group_size=4,bit_widths=(4,8),max_profiles=5)
        self.retention=RetentionPolicy(max_steps=32,max_case_tokens=24,
            max_case_nll_increase_ppm=1000000,max_capability_nll_increase_ppm=1000000,
            max_critical_top1_loss_ppm=1000000,max_mean_kl_micronats=20000000)

    def run_trials(self,groups=("output","layer-0-attention"),**opts):
        args=dict(expected_base_digest=self.base.model_digest,dataset=self.dataset,
            rights=self.rights,training_examples=self.training,training_item_sha256=self.inventory,
            expected_training_inventory_sha256=digest_json(sorted(self.inventory)),
            final_holdout_sha256=self.final,expected_final_holdout_sha256=digest_json(sorted(self.final)),
            policy=self.precision,retention_policy=self.retention,deadline=time.monotonic()+60)
        args.update(opts)
        return calibrate_native_precision(self.base,groups,self.cases,**args)

    def test_real_isolated_and_combined_graph_measurements(self):
        before=portable_model_snapshot(self.base.model)
        report,candidate=self.run_trials()
        self.assertEqual(len(report.trials),4)
        self.assertTrue(all(len(x.packed_digest)==64 for x in report.trials))
        self.assertTrue(all(x.evaluation_digest for x in report.trials))
        self.assertEqual(dict(report.proposed_bits),{"layer-0-attention":4,"output":4})
        self.assertIsNotNone(candidate)
        self.assertEqual(report.combined_model_digest,candidate.model_digest)
        self.assertIsNotNone(report.combined_evaluation_digest)
        self.assertFalse(report.promotion_authorized)
        self.assertLess(report.combined_codec_bytes,4*report.combined_values)
        after=portable_model_snapshot(candidate.model)
        self.assertEqual(before["E"],after["E"])
        self.assertEqual(before["layers"][1],after["layers"][1])
        self.assertNotEqual(before["Wout"],after["Wout"])
        self.assertNotEqual(before["layers"][0]["Wq"],after["layers"][0]["Wq"])
        self.base.assert_model_unchanged()

    def test_combined_interaction_failure_holds_candidate(self):
        from skeleton.ai.training import native_precision_calibration as module
        original=module.evaluate_retention
        count=0
        def evaluate(*args,**kwargs):
            nonlocal count
            count+=1
            report=original(*args,**kwargs)
            if count==5:
                return replace(report,holds=("interaction-regression",))
            return report
        with patch.object(module,"evaluate_retention",side_effect=evaluate):
            report,candidate=self.run_trials()
        self.assertEqual(count,5)
        self.assertIsNone(candidate)
        self.assertIn("combined:interaction-regression",report.holds)

    def test_reserved_final_holdout_does_not_enter_calibration(self):
        final=frozenset((self.cases[0].content_sha256,))
        with self.assertRaisesRegex(ValueError,"reserved final holdout"):
            self.run_trials(final_holdout_sha256=final,
                            expected_final_holdout_sha256=digest_json(sorted(final)))

    def test_training_and_final_inventory_hashes_are_mandatory(self):
        for overrides in ({"expected_training_inventory_sha256":"0"*64},
                          {"expected_final_holdout_sha256":"0"*64},
                          {"training_examples":()}):
            with self.subTest(overrides=overrides),self.assertRaises(ValueError):
                self.run_trials(**overrides)

    def test_calibration_only_requires_separate_rights_and_bound_dataset(self):
        for overrides in ({"rights":replace(self.rights,allowed_scopes=("evaluation",))},
                          {"dataset":replace(self.dataset,content_digest="0"*64)}):
            with self.subTest(overrides=overrides),self.assertRaises(ValueError):
                self.run_trials(**overrides)

    def test_work_profile_and_model_budgets_are_fail_closed(self):
        for overrides in ({"max_profiles":2},{"max_values":1},
                          {"max_total_values":1},{"max_total_evaluation_steps":1}):
            with self.subTest(overrides=overrides),self.assertRaises(ValueError):
                self.run_trials(policy=replace(self.precision,**overrides))
        with self.assertRaises(ValueError):
            self.run_trials(groups=("output","output"))

    def test_expired_or_interrupted_trials_leave_baseline_unchanged(self):
        with self.assertRaises(TimeoutError):
            self.run_trials(deadline=time.monotonic()-1)
        def stop():
            raise RuntimeError("interactive stop")
        with self.assertRaisesRegex(RuntimeError,"interactive stop"):
            self.run_trials(interrupt=stop)
        self.base.assert_model_unchanged()


if __name__=="__main__":
    unittest.main()
