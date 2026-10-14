import hashlib
from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.governance import PromotionDecision
from skeleton.ai.webcrawler.retrieval_bridge import CanonicalRetrievalBridge
from skeleton.ai.runtime.retrieval.chunking import Chunker
from skeleton.retrieval.index import InvertedIndex
from skeleton.retrieval.provenance import ProvenanceLedger

def test_promoted_document_is_chunked_indexed_and_traced():
    text="alpha beta gamma "*100
    digest=hashlib.sha256(text.encode()).hexdigest()
    doc=CrawlDocument("https://example.org/a","https://example.org/a","",text,"text/plain",digest,1,.9,{"schema":"p"},())
    decision=PromotionDecision("decision",digest,"promote",(),2,.8,"p")
    index=InvertedIndex()
    ledger=ProvenanceLedger()
    receipt=CanonicalRetrievalBridge(index,ledger,Chunker(window=100,overlap=10)).ingest(doc,decision)
    assert receipt.chunks > 1
    assert index.size()==receipt.chunks
    assert index.search("alpha")
    assert len(receipt.provenance_entry_ids)==receipt.chunks
    assert all(ledger.trace(item) for item in receipt.provenance_entry_ids)

def test_retrieval_bridge_rejects_unpromoted_document():
    text="alpha beta"
    digest=hashlib.sha256(text.encode()).hexdigest()
    doc=CrawlDocument("https://example.org/a","https://example.org/a","",text,"text/plain",digest,1,.9,{"schema":"p"},())
    decision=PromotionDecision("decision",digest,"quarantine",(),2,.1,"p")
    bridge=CanonicalRetrievalBridge(InvertedIndex(),ProvenanceLedger(),Chunker())
    try:
        bridge.ingest(doc,decision)
    except ValueError:
        pass
    else:
        raise AssertionError("quarantined document reached retrieval")
