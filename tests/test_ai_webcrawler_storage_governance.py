import hashlib,tempfile
from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.storage import SqliteCrawlStore
from skeleton.ai.webcrawler.governance import PromotionGate,HostBudgetController
from skeleton.ai.webcrawler.research import EvidenceSet,ResearchQuery

def doc(url,text,score=.8):
 d=hashlib.sha256(text.encode()).hexdigest()
 return CrawlDocument(url,url,"",text,"text/plain",d,100,score,{"schema":"prov.v1"},())

def test_sqlite_store_survives_reopen_and_dedupes():
 with tempfile.TemporaryDirectory() as d:
  path=d+"/crawl.db";s=SqliteCrawlStore(path);x=doc("https://a.example/","alpha")
  assert s.put(x);assert not s.put(x);s.save_checkpoint("x",{"n":1});s.close()
  s=SqliteCrawlStore(path);assert s.has_url(x.canonical_url);assert s.get(x.content_hash).text=="alpha"
  assert s.load_checkpoint("x")=={"n":1};s.close()

def test_promotion_gate_quarantines_uncorroborated_material():
 x=doc("https://a.example/","crawler evidence")
 e=EvidenceSet(ResearchQuery("crawler evidence",required_sources=2));e.add(x)
 decision=PromotionGate().decide(x,e,now=100)
 assert decision.action=="quarantine"
 assert "insufficient_corroboration" in decision.reasons

def test_promotion_gate_accepts_independent_corroboration():
 a=doc("https://a.example/","crawler evidence")
 b=doc("https://b.example/","crawler evidence")
 e=EvidenceSet(ResearchQuery("crawler evidence",required_sources=2));e.add(a);e.add(b)
 assert PromotionGate().decide(a,e,now=100).action=="promote"

def test_bad_host_health_reduces_allowance():
 c=HostBudgetController(base_requests=20)
 for _ in range(10):c.observe("https://bad.example/x",success=False)
 for _ in range(10):c.observe("https://good.example/x",success=True)
 assert c.allowance("bad.example") < c.allowance("good.example")
