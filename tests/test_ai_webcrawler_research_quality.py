import hashlib
from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.research import EvidenceSet,ResearchQuery
def doc(url,text,score=.8):
 h=hashlib.sha256(text.encode()).hexdigest()
 return CrawlDocument(url,url,"",text,"text/plain",h,1,score,{"schema":"p"},())
def test_irrelevant_hosts_do_not_fake_corroboration():
 e=EvidenceSet(ResearchQuery("quantum battery",required_sources=2))
 e.add(doc("https://a.example/x","quantum battery improves storage"))
 e.add(doc("https://b.example/x","football weather recipe"))
 a=e.assurance(now=1)
 assert a["distinct_hosts"]==1 and not a["sufficient"]
def test_low_quality_host_does_not_fake_corroboration():
 e=EvidenceSet(ResearchQuery("quantum battery",required_sources=2,min_source_score=.5))
 e.add(doc("https://a.example/x","quantum battery report",.9))
 e.add(doc("https://b.example/x","quantum battery report",.1))
 assert e.assurance(now=1)["distinct_hosts"]==1
def test_configurable_contradiction_penalty_changes_assurance():
 a=EvidenceSet(ResearchQuery("battery safe",contradiction_weight=0))
 b=EvidenceSet(ResearchQuery("battery safe",contradiction_weight=.8))
 for e in (a,b):
  e.add(doc("https://a.example/x","battery safe"))
  e.add(doc("https://b.example/x","battery is not safe"))
 assert a.assurance(now=1)["score"]>b.assurance(now=1)["score"]
