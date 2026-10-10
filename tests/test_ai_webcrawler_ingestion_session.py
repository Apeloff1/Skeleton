import hashlib
from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.governance import PromotionDecision
from skeleton.ai.webcrawler.ingestion import GovernedIngestor
from skeleton.ai.webcrawler.session import ResearchSession,SessionLimits
from skeleton.ai.webcrawler.research import ResearchQuery

def doc(url="https://a.example/",text="research evidence"):
 d=hashlib.sha256(text.encode()).hexdigest()
 return CrawlDocument(url,url,"",text,"text/plain",d,100,.9,{"schema":"prov.v1"},())
class Sink:
 def __init__(self):self.records=[]
 def upsert(self,r):self.records.append(r)
class Engine:
 def __init__(self,docs):
  self.docs=list(docs);self.budget=type("B",(),{"exhausted":False,"__dict__":{}})()
 def step(self,now=None):return self.docs.pop(0) if self.docs else None

def decision(x,action):
 return PromotionDecision("d",x.content_hash,action,(),100,.9,"prov.v1")

def test_ingestion_refuses_quarantine():
 x=doc();s=Sink();r=GovernedIngestor(s).ingest(x,decision(x,"quarantine"))
 assert not r.accepted and not s.records

def test_ingestion_refuses_receipt_for_different_content():
 x=doc();s=Sink();d=decision(x,"promote")
 d=PromotionDecision(d.decision_id,"wrong",d.action,d.reasons,d.decided_at,d.assurance_score,d.provenance_schema)
 assert not GovernedIngestor(s).ingest(x,d).accepted

def test_ingestion_attaches_promotion_receipt():
 x=doc();s=Sink();r=GovernedIngestor(s).ingest(x,decision(x,"promote"))
 assert r.accepted and s.records[0]["metadata"]["promotion_receipt"]["action"]=="promote"

def test_session_stops_on_independent_evidence_sufficiency():
 a=doc("https://a.example/");b=doc("https://b.example/")
 session=ResearchSession(ResearchQuery("research evidence",required_sources=2),Engine([a,b]),SessionLimits(max_steps=10))
 session.run_step(now=100);assert session.stop_reason is None
 session.run_step(now=100);assert session.stop_reason=="evidence_sufficient"
 assert session.receipt(now=100)["assurance"]["sufficient"]
