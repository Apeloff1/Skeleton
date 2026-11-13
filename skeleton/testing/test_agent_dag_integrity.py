"""DAG integrity, stable ordering, dependency proof and budget containment."""
import unittest
from skeleton.ai.runtime.operational_ai.agent_fabric.planning.spec import Step,Plan
from skeleton.ai.runtime.operational_ai.agent_fabric.planning.dag import compile_plan,ready
from skeleton.ai.runtime.operational_ai.agent_fabric.planning.critical_path import critical_path
from skeleton.ai.runtime.operational_ai.agent_fabric.planning.impact import ancestors,descendants
from skeleton.ai.runtime.operational_ai.agent_fabric.planning.budget import allocate
from skeleton.ai.runtime.operational_ai.agent_fabric.planning.structural import analyze
from skeleton.ai.runtime.operational_ai.agent_fabric.planning.slices import slice_plan
from skeleton.ai.runtime.operational_ai.agent_fabric.core.errors import Invalid,Exhausted
class DAGTests(unittest.TestCase):
    def graph(self):
        return Plan('p','s',(Step('a','model','research'),Step('b','read','find',('a',)),
               Step('c','model','draft',('a',)),Step('d','review','approve',('b','c'))),'verified work')
    def test_exact_order(self):self.assertEqual(compile_plan(self.graph()),('a','b','c','d'))
    def test_ready_order(self):self.assertEqual(ready(self.graph(),{'a'}),('b','c'))
    def test_dag_longest_path(self):
        c=critical_path(self.graph(),{'a':5,'b':3,'c':7,'d':2})
        self.assertEqual(c['duration_ms'],14);self.assertEqual(c['path'],('a','c','d'))
    def test_impact(self):
        self.assertEqual(descendants(self.graph(),'a'),('b','c','d'))
        self.assertEqual(ancestors(self.graph(),'d'),('a','b','c'))
    def test_token_budget(self):
        a=allocate(self.graph(),100,floor=16);self.assertEqual(sum(a.values()),100)
        with self.assertRaises(Exhausted):allocate(self.graph(),2,floor=16)
    def test_shape(self):
        info=analyze(self.graph());self.assertEqual(info['max_depth'],3)
        self.assertEqual(info['roots'],1);self.assertEqual(info['leaves'],1)
    def test_slices(self):self.assertEqual(slice_plan(self.graph(),limit=2),(('a','b'),('c','d')))
    def test_cycle(self):
        p=Plan('p','s',(Step('a','model','x',('b',)),Step('b','model','y',('a',))),'cycle')
        with self.assertRaises(Invalid):compile_plan(p)
    def test_dangling(self):
        with self.assertRaises(Invalid):compile_plan(Plan('p','s',(Step('x','model','z',('missing',)),),'bad'))
    def test_duplicate_ids(self):
        with self.assertRaises(Invalid):Plan('p','s',(Step('a','model','hello'),Step('a','read','world')),'bad')
if __name__=='__main__':unittest.main()
