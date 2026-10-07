import unittest
from skeleton.ai.agents.plan_dag import AgentContractError, PlanDAG, PlanNode
D="a"*64
class TestPlanDAG(unittest.TestCase):
    def test_topological_waves_and_cycles(self):
        dag=PlanDAG((PlanNode("a",D),PlanNode("b",D,("a",)),PlanNode("c",D,("a",))))
        self.assertEqual(dag.waves,(("a",),("b","c")))
        with self.assertRaises(AgentContractError):
            PlanDAG((PlanNode("a",D,("b",)),PlanNode("b",D,("a",))))
if __name__=="__main__": unittest.main()
