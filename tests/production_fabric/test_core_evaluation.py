import unittest
from skeleton.ai.runtime.production_fabric.evaluation.structural import evaluate
from skeleton.ai.runtime.production_fabric.evaluation.quality import qualify
from skeleton.ai.runtime.production_fabric.evaluation.adversarial import run
from skeleton.ai.runtime.production_fabric.evaluation.coverage import report
from skeleton.ai.runtime.production_fabric.evaluation.benchmark import Case, score
from skeleton.ai.runtime.production_fabric.contracts.spec import parse_world
from skeleton.ai.runtime.production_fabric.product.content.worlds.cloudbreak_signal import WORLD

class EvaluationTests(unittest.TestCase):

    def test_both_endings_reachable(self):
        evidence = evaluate(parse_world(WORLD))
        self.assertEqual(evidence['status'], 'pass')
        self.assertFalse(evidence['quality_attested'])

    def test_absent_evidence_holds(self):
        result = qualify({'structural': True})
        self.assertEqual(result['status'], 'hold')
        self.assertFalse(result['release_ready'])

    def test_adversarial_probe_set(self):
        self.assertEqual(run()['status'], 'pass')

    def test_trace_coverage(self):
        world = parse_world(WORLD)
        x = report(world, [{'scene': 'arrival', 'choice': 'visit_commons'}])
        self.assertEqual(x['visited'], 1)
        self.assertLess(x['scene_coverage'], 1.0)

    def test_benchmark_exact(self):
        evidence = score([Case('a', {'x': 1}, {'x': 1}, 'correctness'), Case('b', {'x': 1}, {'x': 2}, 'correctness')])
        self.assertEqual(evidence['percent'], 50.0)
