import sqlite3
from skeleton.ai.webcrawler.migrations import migrate,SCHEMA_VERSION
from skeleton.ai.webcrawler.research_state import ResearchStateStore
from skeleton.ai.webcrawler.temporal_retrieval import TemporalFragment
from skeleton.ai.webcrawler.evidence_revision import revision_receipt
from skeleton.ai.webcrawler.source_quality import SourcePosterior
def test_research_state_round_trips_temporal_revision_and_quality():
 db=sqlite3.connect(":memory:");migrate(db);s=ResearchStateStore(db)
 t=TemporalFragment("f","https://x",10,(1980,),"h");s.put_temporal(t);assert s.get_temporal("f")==t
 r=revision_receipt("q",("a",),("b",),reason="resolved",recorded_at=10);s.put_revision(r);s.put_revision(r)
 q=SourcePosterior("x",5,2);s.put_source_quality(q);assert s.get_source_quality("x")==q
 assert SCHEMA_VERSION>=6
