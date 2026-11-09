from __future__ import annotations
import unittest
from skeleton.eval.vertical_suite import EvidenceGraph, ResearchQuestion, ScientificResearchFixture, VerticalSuiteError

class VS003ScientificResearcherTests(unittest.TestCase):
    def test_preregistered_reproducible_research_preserves_negative_results(self):
        q=ResearchQuestion("rq-1","Does fixture A improve B?",("accuracy","variance"),("source:a","source:b"),("limit:small-sample",))
        graph=EvidenceGraph("rq-1",(("claim:1","source:a"),("claim:1","source:b")),("outcome:null",),("repro:run-1",))
        result=ScientificResearchFixture().conclude(q,graph,metric_results={"accuracy":0.8,"variance":0.1},conclusion="bounded support")
        self.assertEqual(set(result.metric_results),{"accuracy","variance"})
        self.assertEqual(result.limitations,("limit:small-sample",))

    def test_metric_drift_is_rejected(self):
        q=ResearchQuestion("rq","q",("accuracy",),("source:a",),("limit:x",))
        graph=EvidenceGraph("rq",(("claim","source:a"),),("negative:1",),("repro:1",))
        with self.assertRaisesRegex(VerticalSuiteError,"preregistration"):
            ScientificResearchFixture().conclude(q,graph,metric_results={"other":1.0},conclusion="no")

if __name__=="__main__": unittest.main()
