"""Reproducible measurement, heldout contamination, independent promotion gates."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.evaluation.benchmarks.dataset import EvalCase,EvalSet,EvalError
from skeleton.ai.runtime.operational_ai.evaluation.benchmarks.metrics import eval_text
from skeleton.ai.runtime.operational_ai.evaluation.benchmarks.runner import BenchmarkRunner
from skeleton.ai.runtime.operational_ai.evaluation.benchmarks.qualification import qualify
from skeleton.ai.runtime.operational_ai.evaluation.benchmarks.contamination import check_contamination
from skeleton.ai.runtime.operational_ai.evaluation.benchmarks.comparison import compare
from skeleton.ai.runtime.operational_ai.evaluation.learning.dataset import TrainingRecord,TrainingDataset,LearningError
from skeleton.ai.runtime.operational_ai.evaluation.learning.gate import training_gate
from skeleton.ai.runtime.operational_ai.evaluation.learning.candidate import CandidateRegistry,CandidateRecord

class DeterministicTestOnly:
    model_digest='a'*64
    def answer(self,prompt,seed,max_tokens):return prompt.upper()

class TestEvaluation(unittest.TestCase):
    def cases(self,n=10):
        return tuple(EvalCase.create(f'id_{i}',f'word {i}',f'WORD {i}','reasoning') for i in range(n))

    def test_benchmark_measures_without_release_attestation(self):
        suite=EvalSet.admitted('benchmark',self.cases(),approved=True)
        result=BenchmarkRunner(DeterministicTestOnly()).run(suite)
        self.assertEqual(result.completed,10)
        self.assertEqual(result.failures,0)
        self.assertFalse(qualify(result,min_cases=10,required_categories=('reasoning',)).eligible)

    def test_heldout_contamination(self):
        train=EvalSet.admitted('a',self.cases(),split='train',approved=True)
        holdout=EvalSet.admitted('b',self.cases(),split='holdout',approved=True)
        report=check_contamination(train,holdout)
        self.assertFalse(report.clean)

    def test_paired_comparison_has_quality_gate(self):
        suite=EvalSet.admitted('set',self.cases(25),approved=True)
        a=BenchmarkRunner(DeterministicTestOnly()).run(suite)
        b=BenchmarkRunner(DeterministicTestOnly()).run(suite)
        self.assertEqual(compare(a,b).unchanged,25)

    def test_metric_f1(self):
        m=eval_text('HELLO WORLD','hello world')
        self.assertEqual(m.normalized_match,1.0)
        self.assertEqual(m.exact_match,0.0)

    def test_training_requires_independent_consent(self):
        with self.assertRaises(LearningError):TrainingRecord.admit('id','hello','world','original','operator')

    def test_training_gate_refuses_unreviewed(self):
        r=TrainingRecord.admit('id','hello','world','original','operator',consent_confirmed=True)
        ds=TrainingDataset.assemble('ds',(r,))
        g=training_gate(ds,allowed_licenses=('original',),allowed_origins=('operator',))
        self.assertFalse(g.permitted)
        self.assertIn('independent-training-approval-missing',g.reasons)

    def test_candidate_always_quarantined(self):
        candidate=CandidateRecord('candidate','a'*64,'b'*64,'c'*64,'d'*64,'e'*64)
        registry=CandidateRegistry()
        self.assertTrue(registry.admit(candidate))
        self.assertFalse(registry.admit(candidate))
        self.assertEqual(registry.get('candidate').status,'quarantined')

if __name__=='__main__':unittest.main()
