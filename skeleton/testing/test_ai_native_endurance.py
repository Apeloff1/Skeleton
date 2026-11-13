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
        with self.assertRaisesRegex(QualificationHeld, 'native generated receipt rejected'):
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

    def test_subclass_policy_and_hostile_backend_digests_hold_before_native_io(self):
        class HostileDigest(str):
            def __eq__(self, other):
                raise AssertionError('untrusted digest equality executed')
            def __ne__(self, other):
                raise AssertionError('untrusted digest inequality executed')

        class SubclassPolicy(BurnInPolicy):
            pass

        backend = FixtureOnlyBackend()
        with self.assertRaises(QualificationHeld):
            measure(backend, SubclassPolicy(trials=1), clock=self.clock())
        self.assertEqual((backend.admits, backend.calls), (0, 0))
        for attr in ('model_digest', 'tokenizer_digest'):
            backend = FixtureOnlyBackend()
            setattr(backend, attr, HostileDigest(MODEL))
            with self.subTest(attr=attr), self.assertRaises(QualificationHeld):
                measure(backend, self.new_policy(trials=1), clock=self.clock())
            self.assertEqual((backend.admits, backend.calls), (0, 0))

    def test_invalid_monotonic_clocks_hold_without_retry(self):
        class HostileInt(int):
            def __sub__(self, other):
                raise AssertionError('untrusted clock arithmetic executed')

        for reading in (True, 1.5, HostileInt(10), -1):
            backend = FixtureOnlyBackend()
            with self.subTest(reading=reading), self.assertRaises(QualificationHeld):
                measure(backend, self.new_policy(trials=1), clock=lambda: reading)
            self.assertEqual(backend.calls, 0)
        for ending in (True, 1.5, HostileInt(20), 9):
            backend = FixtureOnlyBackend()
            readings = iter((10, ending))
            with self.subTest(ending=ending), self.assertRaises(QualificationHeld):
                measure(backend, self.new_policy(trials=1), clock=lambda: next(readings))
            self.assertEqual(backend.calls, 1)

    def test_forged_native_receipt_fields_rejected_before_hostile_hooks(self):
        class HostileDigest(str):
            def __eq__(self, other):
                raise AssertionError('untrusted receipt equality executed')
            def __ne__(self, other):
                raise AssertionError('untrusted receipt inequality executed')

        class HostileText(str):
            def strip(self, *args, **kwargs):
                raise AssertionError('untrusted receipt strip executed')
            def encode(self, *args, **kwargs):
                raise AssertionError('untrusted receipt encode executed')

        def valid():
            text = 'Synthetic bounded output'
            return Generated(text, 8, 4, sha256(text.encode()).hexdigest(),
                             MODEL, TOKEN, 'stop')

        for field, value in (
            ('model_digest', HostileDigest(MODEL)),
            ('tokenizer_digest', HostileDigest(TOKEN)),
            ('output_digest', HostileDigest('a' * 64)),
            ('text', HostileText('Synthetic bounded output')),
            ('finish_reason', HostileDigest('stop')),
            ('prompt_tokens', 131073),
        ):
            receipt = valid()
            object.__setattr__(receipt, field, value)
            with self.subTest(field=field), self.assertRaises(QualificationHeld):
                trial_record(1, 25_000_000, receipt, MODEL, TOKEN, 48)

        class SubclassGenerated(Generated):
            pass

        with self.assertRaises(QualificationHeld):
            trial_record(1, 25_000_000,
                         SubclassGenerated('safe', 1, 1, sha256(b'safe').hexdigest(),
                                           MODEL, TOKEN, 'stop'), MODEL, TOKEN, 48)

    def test_oversized_exact_integer_clock_holds_without_bigint_arithmetic(self):
        # Native clocks are bounded to signed 64-bit nanoseconds.  A foreign
        # clock can return an exact builtin int with enormous bit length.
        enormous = 1 << 100000
        backend = FixtureOnlyBackend()
        with self.assertRaisesRegex(QualificationHeld, 'invalid monotonic trial clock'):
            measure(backend, self.new_policy(trials=1), clock=lambda: enormous)
        self.assertEqual((backend.admits, backend.calls), (1, 0))

        backend = FixtureOnlyBackend()
        readings = iter((10, enormous))
        with self.assertRaisesRegex(QualificationHeld, 'missed monotonic deadline'):
            measure(backend, self.new_policy(trials=1), clock=lambda: next(readings))
        self.assertEqual(backend.calls, 1)  # never retry a completed native call

    def test_forged_surrogate_receipt_holds_without_unicode_exception_or_retry(self):
        text = 'Synthetic bounded output'
        receipt = Generated(text, 8, 4, sha256(text.encode()).hexdigest(),
                            MODEL, TOKEN, 'stop')
        object.__setattr__(receipt, 'text', '\ud800')
        with self.assertRaisesRegex(QualificationHeld, 'invalid native generated text encoding'):
            trial_record(1, 25_000_000, receipt, MODEL, TOKEN, 48)

        class ForgedTextBackend(FixtureOnlyBackend):
            def generate(self, *args, **kwargs):
                self.calls += 1
                return receipt

        backend = ForgedTextBackend()
        with self.assertRaisesRegex(QualificationHeld, 'invalid native generated text encoding'):
            measure(backend, self.new_policy(trials=1), clock=self.clock())
        self.assertEqual(backend.calls, 1)

    def test_private_report_reconciles_metrics_and_policy_before_publication(self):
        for change in ('summary', 'policy', 'trial', 'digest', 'finish', 'keys', 'rate'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as path:
                root = Path(path) / 'private'
                root.mkdir(mode=0o700)
                report = measure(FixtureOnlyBackend(), self.new_policy(), clock=self.clock())
                if change == 'summary':
                    report['summary']['generated_tokens'] += 1
                elif change == 'rate':
                    report['summary']['generated_tokens_per_second'] = 1 << 10000
                elif change == 'policy':
                    report['policy']['max_output_tokens'] = 0
                elif change == 'trial':
                    report['trials'][0]['prompt_tokens'] = 1 << 10000
                elif change == 'digest':
                    class HostileDigest(str):
                        def __eq__(self, other):
                            raise AssertionError('untrusted digest equality executed')
                    report['model_sha256'] = HostileDigest(MODEL)
                elif change == 'finish':
                    class HostileFinish(str):
                        def __eq__(self, other):
                            raise AssertionError('untrusted finish equality executed')
                    report['trials'][0]['finish_reason'] = HostileFinish('stop')
                else:
                    class ForeignKey:
                        def __hash__(self):
                            return 123456789123456789
                        def __eq__(self, other):
                            raise AssertionError('untrusted mapping equality executed')
                    report['trials'][0][ForeignKey()] = 'forged'
                with self.assertRaises(QualificationHeld):
                    publish_private(root, 'rejected.json', report)
                self.assertEqual(list(root.iterdir()), [])

if __name__=='__main__':unittest.main()
