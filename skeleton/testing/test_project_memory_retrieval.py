import unittest
from skeleton.ai.evidence_memory import GenerationMemoryEvidence, admit_generation_memory
from skeleton.ai.memory_retrieval import MemoryRecallError, compile_project_memory_context
from skeleton.ai.project_memory import ProjectMemory

def ev(text,seed):
    return GenerationMemoryEvidence(
        *("0123456789abcdef"[(i + seed + 10) % 16] * 64 for i in range(7)),
        generated_text=text,
    )

class TestProjectMemoryRetrieval(unittest.TestCase):
    def populated(self):
        m=ProjectMemory("t","p","generated-evidence")
        m,r1=admit_generation_memory(m,ev("first memory",0),tenant_id="t",project_id="p")
        m,r2=admit_generation_memory(m,ev("second memory",1),tenant_id="t",project_id="p")
        return m,r1,r2

    def test_visible_memory_enters_bounded_context_as_optional_data(self):
        m,r1,r2=self.populated()
        b=compile_project_memory_context(
            m,tenant_id="t",project_id="p",trust_class="generated-evidence",
            token_costs={r1.fact_id:2,r2.fact_id:2},token_budget=4,operation_id="op",
        )
        self.assertEqual(b.text,"first memory\n\nsecond memory")
        self.assertTrue(all(x.context_item.kind=="project-memory" for x in b.recalled))
        self.assertTrue(all(not x.context_item.mandatory for x in b.recalled))

    def test_context_budget_bounds_memory_recall(self):
        m,r1,r2=self.populated()
        b=compile_project_memory_context(
            m,tenant_id="t",project_id="p",trust_class="generated-evidence",
            token_costs={r1.fact_id:2,r2.fact_id:2},token_budget=2,operation_id="op",
        )
        self.assertEqual(len(b.compiled.selected_ids),1)

    def test_cross_project_recall_fails_closed(self):
        m,r1,r2=self.populated()
        with self.assertRaises(MemoryRecallError):
            compile_project_memory_context(
                m,tenant_id="t",project_id="other",trust_class="generated-evidence",
                token_costs={},token_budget=2,operation_id="op",
            )

    def test_token_cost_map_must_exactly_cover_visible_memory(self):
        m,r1,r2=self.populated()
        for costs in ({r1.fact_id:2},{r1.fact_id:2,r2.fact_id:2,"extra":1}):
            with self.subTest(costs=costs):
                with self.assertRaises(MemoryRecallError):
                    compile_project_memory_context(
                        m,tenant_id="t",project_id="p",trust_class="generated-evidence",
                        token_costs=costs,token_budget=4,operation_id="op",
                    )

    def test_boolean_and_nonpositive_costs_rejected(self):
        m,r1,r2=self.populated()
        for bad in (True,0,-1):
            with self.subTest(bad=bad):
                with self.assertRaises(MemoryRecallError):
                    compile_project_memory_context(
                        m,tenant_id="t",project_id="p",trust_class="generated-evidence",
                        token_costs={r1.fact_id:bad,r2.fact_id:2},token_budget=4,operation_id="op",
                    )

if __name__=="__main__":
    unittest.main()
