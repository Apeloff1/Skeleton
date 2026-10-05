from __future__ import annotations
import hashlib
import pytest
from skeleton.ai.research.literature_watch import LiteratureRecord,LiteratureSource,LiteratureTriage,LiteratureWatchError,triage_record

def digest(x): return hashlib.sha256(x.encode()).hexdigest()

def test_literature_watch_triages_matching_topic_to_backlog():
    source=LiteratureSource("src","journal",3,"crossref")
    record=LiteratureRecord("r1","src","Paper","doi:1",digest("paper"),("agents","evaluation"))
    result=triage_record(record=record,source=source,watched_topics=("evaluation",),backlog_prefix="research")
    assert result.accepted is True
    assert result.priority=="high"
    assert result.backlog_key.startswith("research:")
    assert result.external_side_effects is False

def test_record_source_mismatch_fails_closed():
    with pytest.raises(LiteratureWatchError,match="identity mismatch"):
        triage_record(
            record=LiteratureRecord("r","other","Paper","doi:1",digest("x"),("ai",)),
            source=LiteratureSource("src","journal",2,"adapter"),
            watched_topics=("ai",),backlog_prefix="r",
        )

def test_unmatched_record_is_not_silently_backlogged():
    result=triage_record(
        record=LiteratureRecord("r","src","Paper","doi:1",digest("x"),("biology",)),
        source=LiteratureSource("src","preprint",1,"adapter"),
        watched_topics=("ai",),backlog_prefix="r",
    )
    assert result.accepted is False
    assert result.backlog_key is None

def test_triage_cannot_claim_external_side_effects():
    with pytest.raises(LiteratureWatchError,match="cannot mutate"):
        LiteratureTriage(digest("r"),"low",(),None,False,True)
