"""Artificial fixture responses test the harness, never native model quality."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.model.qualification import BurnInPolicy,QualificationHeld,measure
from skeleton.ai.runtime.operational_ai.model.qualification.records import trial_record
from skeleton.ai.runtime.operational_ai.model.qualification.latency import summarize
from skeleton.ai.runtime.operational_ai.model.qualification.storage import publish_private
from skeleton.ai.runtime.operational_ai.model.native import Generated
from skeleton.ai.runtime.operational_ai.authority.canonical import ContractViolation

MODEL='a'*64
TOKEN='b'*64


class FixtureOnlyBackend:
    model_digest=MODEL
    tokenizer_digest=TOKEN
    def __init__(self,mode='normal'):
        self.calls=0;self.admits=0;self.mode=mode

    def admit_before_reservation(self):
        self.admits+=1
        if self.mode=='pressure':raise QualificationHeld('simulated low headroom')
        return {'status':'fixture-only'}

    def generate(self,*args,**kwargs):
        self.calls+=1
        if self.mode=='exception':raise QualificationHeld('simulated native failure')
        text='Synthetic fixture reply. Not a real inference.'
        output=sha256(text.encode()).hexdigest()
        model=MODEL if self.mode!='model-swap' else 'c'*64
        if self.mode=='wrong-output-digest':output='0'*64
        if self.mode=='empty':text=''
        generated=6 if self.mode!='overlimit' else 500
        if self.mode=='bad-finish':finish='tool_calls'
        else:finish='stop'
        return Generated(text,8,generated,output,model,TOKEN,finish)


class EnduranceTests(unittest.TestCase):
    def new_policy(self,trials=3,**kw):
        return BurnInPolicy(trials=trials,**kw)

    def clock(self):
        counter=[0]
        def advance():
            counter[0]+=25_000_000
            return counter[0]
        return advance

    def test_full_simulated_trials_no_plaintext_report(self):
        backend=FixtureOnlyBackend()
        result=measure(backend,self.new_policy(),clock=self.clock())
        self.assertEqual(result['summary']['observations'],3)
        self.assertEqual(backend.admits,3)
        self.assertEqual(backend.calls,3)
        self.assertNotIn('Synthetic fixture reply',json.dumps(result))
        self.assertIn('not-release-certified',result['status'])

    def test_no_fallback_after_native_failure(self):
        b=FixtureOnlyBackend('exception')
        with self.assertRaises(QualificationHeld):measure(b,self.new_policy(),clock=self.clock())
        self.assertEqual(b.calls,1)

    def test_preflight_pressure_blocks_first_native_execution(self):
        b=FixtureOnlyBackend('pressure')
        with self.assertRaises(QualificationHeld):measure(b,self.new_policy(),clock=self.clock())
        self.assertEqual(b.calls,0)

    def test_model_swap_refused(self):
        b=FixtureOnlyBackend('model-swap')
        with self.assertRaises(QualificationHeld):measure(b,self.new_policy(),clock=self.clock())
        self.assertEqual(b.calls,1)

    def test_bad_hash_refused(self):
        with self.assertRaises(QualificationHeld):
            measure(FixtureOnlyBackend('wrong-output-digest'),self.new_policy(),clock=self.clock())

    def test_empty_output_refused(self):
        backend = FixtureOnlyBackend('empty')
        with self.assertRaisesRegex(ContractViolation, 'empty or oversized'):
            measure(backend, self.new_policy(), clock=self.clock())
        self.assertEqual(backend.admits, 1)
        self.assertEqual(backend.calls, 1)  # invalid native receipt is never retried

    def test_native_token_cap_enforced(self):
        with self.assertRaises(QualificationHeld):
            measure(FixtureOnlyBackend('overlimit'),self.new_policy(),clock=self.clock())

    def test_model_tool_call_finish_refused(self):
        with self.assertRaises(QualificationHeld):
            measure(FixtureOnlyBackend('bad-finish'),self.new_policy(),clock=self.clock())

    def test_hard_latency_limit_refuses_simulated_missed_deadline(self):
        def clock():
            clock.tick+=130_000_000_000
            return clock.tick
        clock.tick=0
        with self.assertRaises(QualificationHeld):
            measure(FixtureOnlyBackend(),self.new_policy(),clock=clock)

    def test_no_quality_claim_in_observational_report(self):
        r=measure(FixtureOnlyBackend(),self.new_policy(),clock=self.clock())
        self.assertIn('model-quality',r['claims_excluded'])
        self.assertIn('consumer-install',r['claims_excluded'])

    def test_percentile_metrics_nearest_rank(self):
        x=summarize([1,2,3,4,5],[1,1,1,1,1])
        self.assertEqual(x['p95_ns'],5)
        self.assertEqual(x['max_ns'],5)
        self.assertEqual(x['generated_tokens'],5)

    def test_negative_or_false_token_count_refused(self):
        for bad in (True,-1,1.5):
            with self.subTest(bad=bad),self.assertRaises(QualificationHeld):
                summarize([1],[bad])

    def test_nonpositive_timing_refused(self):
        with self.assertRaises(QualificationHeld):summarize([0],[1])

    def test_policy_rejects_bool_and_excessive_work(self):
        for kw in ({'trials':True},{'trials':257},
                   {'max_output_tokens':0},{'inference_ms':100},
                   {'minimum_generated_tokens':500}):
            with self.subTest(kw=kw),self.assertRaises(QualificationHeld):BurnInPolicy(**kw)

    def test_private_report_no_clobber(self):
        with tempfile.TemporaryDirectory() as path:
            private=Path(path)/'private';private.mkdir(mode=0o700)
            report=measure(FixtureOnlyBackend(),self.new_policy(),clock=self.clock())
            info=publish_private(private,'run1.json',report)
            self.assertEqual(info['status'],'private-report-atomically-created-no-clobber')
            self.assertNotIn('Synthetic fixture reply',(private/'run1.json').read_text())
            with self.assertRaises(FileExistsError):publish_private(private,'run1.json',report)

    def test_report_publication_never_accepts_arbitrary_prompt_or_response(self):
        with tempfile.TemporaryDirectory() as path:
            root=Path(path)/'private';root.mkdir(mode=0o700)
            report=measure(FixtureOnlyBackend(),self.new_policy(),clock=self.clock())
            report['private_prompt']='operator secret'
            with self.assertRaises(QualificationHeld):publish_private(root,'clean.json',report)
            self.assertFalse((root/'clean.json').exists())

    def test_atomic_publisher_refuses_partial_named_reports(self):
        with tempfile.TemporaryDirectory() as path:
            root=Path(path)/'private';root.mkdir(mode=0o700)
            report=measure(FixtureOnlyBackend(),self.new_policy(),clock=self.clock())
            with patch('skeleton.ai.runtime.operational_ai.model.qualification.storage.os.link',
                       side_effect=OSError('simulated publication failure')):
                with self.assertRaises(OSError):publish_private(root,'never.json',report)
            self.assertEqual(list(root.iterdir()),[])

    def test_publish_cannot_overwrite_operator_symlink(self):
        with tempfile.TemporaryDirectory() as path:
            root=Path(path)/'private';root.mkdir(mode=0o700)
            (root/'link.json').symlink_to(root/'target')
            report=measure(FixtureOnlyBackend(),self.new_policy(),clock=self.clock())
            with self.assertRaises(FileExistsError):publish_private(root,'link.json',report)
            self.assertFalse((root/'target').exists())

    def test_report_rejects_directory_traversal(self):
        with tempfile.TemporaryDirectory() as path:
            root=Path(path)/'private';root.mkdir(mode=0o700)
            with self.assertRaises(QualificationHeld):publish_private(root,'../private.json',{'ok':True})

    def test_report_rejects_world_readable_root(self):
        with tempfile.TemporaryDirectory() as path:
            Path(path).chmod(0o755)
            with self.assertRaises(Exception):publish_private(path,'ok.json',{'ok':True})

if __name__=='__main__':unittest.main()
