from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.research import EvidenceSet, ResearchQuery, frontier_priority

def doc(url,text,score=.8,when=100.0):
    import hashlib
    digest=hashlib.sha256(text.encode()).hexdigest()
    return CrawlDocument(url,url,"",text,"text/plain",digest,when,score,{},())

def test_research_requires_independent_sources():
    evidence=EvidenceSet(ResearchQuery("agent retrieval provenance",required_sources=2))
    evidence.add(doc("https://a.example/report","agent retrieval provenance improves evidence"))
    assert not evidence.assurance(now=100)["sufficient"]
    evidence.add(doc("https://b.example/study","agent retrieval provenance study evidence"))
    result=evidence.assurance(now=100)
    assert result["distinct_hosts"] == 2
    assert result["sufficient"]

def test_duplicate_host_does_not_fake_source_diversity():
    evidence=EvidenceSet(ResearchQuery("crawler safety",required_sources=2))
    evidence.add(doc("https://a.example/1","crawler safety"))
    evidence.add(doc("https://a.example/2","crawler safety"))
    assert evidence.distinct_hosts == 1
    assert not evidence.assurance(now=100)["sufficient"]

def test_opposing_independent_evidence_is_preserved_not_silenced():
    evidence=EvidenceSet(ResearchQuery("model improves retrieval",required_sources=2))
    evidence.add(doc("https://a.example/a","model improves retrieval according to evaluation"))
    evidence.add(doc("https://b.example/b","model does not improve retrieval according to evaluation"))
    conflicts=evidence.contradictions()
    assert conflicts
    result=evidence.assurance(now=100)
    assert result["contradictions"] == 1

def test_temporal_decay_prefers_fresh_evidence_when_otherwise_equal():
    evidence=EvidenceSet(ResearchQuery("retrieval architecture",required_sources=1,freshness_half_life_seconds=10))
    old=evidence.add(doc("https://old.example/x","retrieval architecture",when=0))
    fresh=evidence.add(doc("https://fresh.example/x","retrieval architecture",when=100))
    ranked=evidence.ranked(now=100)
    assert ranked[0].observation_id == fresh.observation_id

def test_frontier_priority_rewards_query_match_and_cross_host_exploration():
    relevant=frontier_priority("agent memory","https://b.example/agent-memory",same_host=False)
    irrelevant=frontier_priority("agent memory","https://a.example/weather",same_host=True)
    assert relevant > irrelevant
