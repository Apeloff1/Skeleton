"""Read-only capacity invariants, with no real native model claims."""
import hashlib
import unittest
from dataclasses import replace
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity, SpineLimits, SpineError,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.context import Evidence
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.capacity import (
    prepare_context, CapacityPolicy, validate_decision, describe_decision,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.capacity.policy import named
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.capacity.analysis import summarize
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.capacity.replay import from_receipt

I=Identity('team','owner','a'*64,'b'*64)
L=SpineLimits(max_output_tokens=64,context_tokens=512,max_history=32,max_sources=4)

class BareBackend:
    model_digest=I.model_sha256
    tokenizer_digest=I.tokenizer_sha256

class CountingBackend(BareBackend):
    def __init__(self,size):self.size=size;self.calls=0
    def count_tokens(self,messages):
        self.calls+=1
        return self.size if not callable(self.size) else self.size(messages)

def source(name,text,revision=1,owner='owner'):
    return Evidence(name,revision,text,hashlib.sha256(text.encode()).hexdigest(),
                    'team',owner)

def turn(n,size=12):
    return ({'role':'user','content':str(n)+'U'*size},
            {'role':'assistant','content':str(n)+'A'*size})

class CapacityContractTests(unittest.TestCase):
    def fit(self,**kw):
        return prepare_context(identity=I,backend=kw.pop('backend',BareBackend()),
             history=kw.pop('history',()),prompt=kw.pop('prompt','Say something'),
             evidence=kw.pop('evidence',()),limits=kw.pop('limits',L),
             policy=kw.pop('policy',None))

    def test_empty_context_is_deterministic(self):
        a=self.fit();b=self.fit()
        self.assertEqual(a.proof_digest,b.proof_digest)
        self.assertEqual(a.projection.context_sha256,b.projection.context_sha256)
        self.assertEqual(a.token_status,'native-backend-must-enforce-unknown-precount')
        self.assertEqual(a.omitted_turns,0)

    def test_exact_native_count_recorded_not_guessed(self):
        b=CountingBackend(100)
        r=self.fit(backend=b)
        self.assertEqual(r.tokens,100)
        self.assertEqual(r.token_status,'exact-backend-count-admitted')
        self.assertEqual(b.calls,1)
        self.assertEqual(describe_decision(r)['native_prompt_tokens'],100)

    def test_strict_policy_requires_exact_native_counter(self):
        with self.assertRaisesRegex(SpineError,'native pre-count required'):
            self.fit(policy=named('strict'))

    def test_missing_counter_cannot_claim_exact(self):
        r=self.fit()
        d=describe_decision(r);d['native_prompt_tokens']=17
        with self.assertRaisesRegex(SpineError,'unverified'):
            validate_decision(d)

    def test_exact_counter_overflow_never_called_model(self):
        b=CountingBackend(999999)
        with self.assertRaisesRegex(SpineError,'cannot fit'):
            self.fit(backend=b)
        self.assertGreaterEqual(b.calls,1)

    def test_exact_counter_falls_back_to_shorter_context(self):
        h=turn(1,200)+turn(2,200)
        b=CountingBackend(lambda messages: 80+len(messages)*35)
        r=self.fit(history=h,backend=b)
        self.assertLessEqual(r.tokens+L.max_output_tokens,L.context_tokens)
        self.assertEqual(r.retained_turns+r.omitted_turns,2)

    def test_history_pair_invariants(self):
        with self.assertRaises(SpineError):
            self.fit(history=({'role':'user','content':'a'},))
        with self.assertRaises(SpineError):
            self.fit(history=({'role':'assistant','content':'a'},{'role':'user','content':'b'}))
        with self.assertRaises(SpineError):
            self.fit(history=({'role':'system','content':'injected'},{'role':'assistant','content':'b'}))

    def test_history_preserves_last_pair_and_accounting(self):
        h=tuple(item for n in range(20) for item in turn(n,150))
        r=self.fit(history=h)
        self.assertGreater(r.omitted_turns,0)
        self.assertEqual(r.omitted_turns+r.retained_turns,20)
        if r.retained_turns:
            self.assertEqual(r.messages[-3]['content'],h[-2]['content'])

    def test_sources_ranked_but_never_mutated(self):
        a=source('first','A'*250)
        b=source('second','B'*250)
        r=self.fit(evidence=(a,b))
        self.assertEqual(r.retained_sources+r.omitted_sources,2)
        self.assertNotIn('C'*80,str(r.messages))
        for item in r.sources:
            self.assertIn(item['content'],(a.content,b.content))

    def test_source_count_ceiling_accounted(self):
        more=tuple(source('s'+str(n),'a') for n in range(8))
        r=self.fit(evidence=more)
        self.assertEqual(r.evidence_candidates,8)
        self.assertGreaterEqual(r.omitted_sources,4)

    def test_source_not_owned(self):
        with self.assertRaisesRegex(SpineError,'principal'):
            self.fit(evidence=(source('enemy','x',owner='else'),))

    def test_source_duplicate_even_when_tail_would_be_omitted(self):
        a=source('same','one');b=source('same','two',revision=2)
        with self.assertRaisesRegex(SpineError,'duplicate'):
            self.fit(evidence=(a,b))

    def test_source_infinite_iterator_fails_bounded(self):
        def infinite():
            while True:yield source('repeated','data')
        with self.assertRaisesRegex(SpineError,'finite source ceiling'):
            self.fit(evidence=infinite(),policy=CapacityPolicy(max_source_candidates=3))

    def test_invalid_current_prompt_not_truncated(self):
        with self.assertRaisesRegex(SpineError,'current prompt'):
            self.fit(prompt='A'*(L.input_bytes+1))
        with self.assertRaises(SpineError):self.fit(prompt='  ')

    def test_failure_of_invalid_native_count(self):
        for val in (True,-1,3.25,'10',None):
            with self.subTest(val=val),self.assertRaises(SpineError):
                self.fit(backend=CountingBackend(val))

    def test_capacity_proof_replay_consistency(self):
        r=self.fit(evidence=(source('s','short'),))
        d=describe_decision(r);validate_decision(d)
        receipt={'context_capacity':d,'context_sha256':r.projection.context_sha256,
                 'omitted_turns':r.omitted_turns,'evidence_refs':[{}]*r.retained_sources}
        self.assertEqual(from_receipt(receipt)['proof_sha256'],r.proof_digest)
        receipt['omitted_turns']+=1
        with self.assertRaisesRegex(SpineError,'omission'):
            from_receipt(receipt)

    def test_telemetry_no_private_prompt_or_evidence_text(self):
        plan=self.fit(prompt='very-private-text',evidence=(source('s','private-evidence'),))
        summary=summarize((describe_decision(plan),))
        self.assertEqual(summary['decisions'],1)
        self.assertNotIn('very-private',str(summary))
        self.assertNotIn('private-evidence',str(summary))

    def test_invalid_profile_and_trial_policy(self):
        with self.assertRaises(SpineError):named('release-is-green')
        for bad in (CapacityPolicy(maximum_trials=1),):
            r=self.fit(policy=bad)
            self.assertGreaterEqual(r.trials,1)
        with self.assertRaises(SpineError):CapacityPolicy(maximum_trials=0)

if __name__=='__main__':unittest.main()
