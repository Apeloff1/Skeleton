from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.research import EvidenceSet,ResearchQuery,frontier_priority
import hashlib
def d(url,text,score=.8):
 h=hashlib.sha256(text.encode()).hexdigest();return CrawlDocument(url,url,"",text,"text/plain",h,100,score,{},())
def test_signals_are_bucketed_by_explicit_year_and_independent_hosts():
 e=EvidenceSet(ResearchQuery("agent retrieval",required_sources=1))
 e.add(d("https://a.example/x","agent retrieval improved in 2024 and 2025"))
 e.add(d("https://b.example/x","agent retrieval regressed in 2025"))
 s=e.signals_by_year()
 assert s[2024]["observations"]==1 and s[2024]["distinct_hosts"]==1
 assert s[2025]["observations"]==2 and s[2025]["distinct_hosts"]==2
def test_undercovered_years_exposes_temporal_research_gaps():
 e=EvidenceSet(ResearchQuery("agent retrieval",required_sources=1))
 e.add(d("https://a.example/x","agent retrieval 2024"))
 assert e.undercovered_years(2023,2025)==(2023,2025)
def test_frontier_priority_rewards_requested_year_signal():
 base=frontier_priority("agent retrieval","https://x.example/report",same_host=False,target_years=(2023,))
 hit=frontier_priority("agent retrieval","https://x.example/report-2023",same_host=False,target_years=(2023,))
 assert hit>base
