import hashlib
from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.temporal import TemporalCorpus

def doc(text,when):
    digest=hashlib.sha256(text.encode()).hexdigest()
    return CrawlDocument("https://example.com/x","https://example.com/x","",text,"text/plain",digest,when,.8,{},())

def test_temporal_corpus_preserves_old_version_and_as_of_reads():
    corpus=TemporalCorpus()
    assert corpus.observe(doc("version one",10)) is None
    change=corpus.observe(doc("version two",20))
    assert change and change.previous_hash != change.current_hash
    assert corpus.as_of("https://example.com/x",15).text == "version one"
    assert corpus.as_of("https://example.com/x",25).text == "version two"
    assert len(corpus.history("https://example.com/x")) == 2

def test_identical_recrawl_does_not_create_fake_change():
    corpus=TemporalCorpus()
    corpus.observe(doc("stable",10))
    assert corpus.observe(doc("stable",20)) is None
    assert len(corpus.history("https://example.com/x")) == 1

def test_change_event_contains_bounded_diff_evidence():
    corpus=TemporalCorpus()
    corpus.observe(doc("alpha old statement",10))
    change=corpus.observe(doc("alpha new statement",20))
    assert "new" in change.added_excerpt
    assert "old" in change.removed_excerpt
    assert 0 <= change.similarity <= 1
    assert corpus.changed_urls() == ("https://example.com/x",)
