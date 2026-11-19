import hashlib, unittest
from skeleton.ai.evidence_memory import GenerationMemoryEvidence, admit_generation_memory
from skeleton.ai.memory_retrieval import compile_project_memory_context
from skeleton.ai.project_memory import ProjectMemory
from skeleton.ai.unified_knowledge import ExternalEvidence, UnifiedKnowledgeError, compile_unified_knowledge

D="a"*64
def mem():
 m=ProjectMemory("t","p","generated-evidence")
 e=GenerationMemoryEvidence(D,"b"*64,"c"*64,"d"*64,"e"*64,"f"*64,"1"*64,"remembered")
 m,r=admit_generation_memory(m,e,tenant_id="t",project_id="p")
 return compile_project_memory_context(m,tenant_id="t",project_id="p",trust_class="generated-evidence",token_costs={r.fact_id:2},token_budget=2,operation_id="memory")
def ext(id,text,cost=2,priority=0):
 return ExternalEvidence(id,text,hashlib.sha256(text.encode()).hexdigest(),"2"*64,cost,priority)

class TestUnifiedKnowledge(unittest.TestCase):
 def test_external_and_memory_share_one_budget_and_preserve_classes(self):
  b=compile_unified_knowledge("op",(ext("web","web evidence",2,10),),mem(),token_budget=4)
  self.assertEqual(b.text,"web evidence\n\nremembered")
  self.assertEqual(b.external_ids,("web",))
  self.assertEqual(len(b.memory_ids),1)
  self.assertTrue(all(not x.mandatory for x in b.compiled.items))
 def test_priority_arbitrates_scarce_budget(self):
  b=compile_unified_knowledge("op",(ext("web","web evidence",2,10),),mem(),token_budget=2)
  self.assertEqual(b.text,"web evidence")
  self.assertEqual(b.memory_ids,())
 def test_tampered_external_content_rejected(self):
  with self.assertRaises(UnifiedKnowledgeError):
   ExternalEvidence("x","value","0"*64,"2"*64,1)
 def test_source_identity_collision_rejected(self):
  m=mem(); collision=m.recalled[0].fact.fact_id
  with self.assertRaises(UnifiedKnowledgeError):
   compile_unified_knowledge("op",(ext(collision,"web"),),m,token_budget=4)
 def test_duplicate_external_identity_rejected(self):
  e=ext("x","same")
  with self.assertRaises(UnifiedKnowledgeError):
   compile_unified_knowledge("op",(e,e),mem(),token_budget=6)
 def test_source_root_is_deterministic_and_content_sensitive(self):
  a=compile_unified_knowledge("op",(ext("x","one"),),mem(),token_budget=4)
  b=compile_unified_knowledge("op",(ext("x","one"),),mem(),token_budget=4)
  c=compile_unified_knowledge("op",(ext("x","two"),),mem(),token_budget=4)
  self.assertEqual(a.source_root_digest,b.source_root_digest)
  self.assertNotEqual(a.source_root_digest,c.source_root_digest)

if __name__=="__main__": unittest.main()
