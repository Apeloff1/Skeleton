import unittest
from skeleton.ai.assurance.trace_correlation import AssuranceContractError, TraceEvent, correlate_trace
D="a"*64

class TestTraceCorrelation(unittest.TestCase):
    def test_parent_must_precede_child(self):
        root=TraceEvent("t","root",None,0,D)
        child=TraceEvent("t","child","root",1,D)
        self.assertEqual([x.span_id for x in correlate_trace((child,root))],["root","child"])
        bad=TraceEvent("t","late","child",0,D)
        with self.assertRaises(AssuranceContractError): correlate_trace((bad,child,root))

if __name__=="__main__": unittest.main()
