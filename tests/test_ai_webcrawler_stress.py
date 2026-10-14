import hashlib,tempfile
from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.storage import SqliteCrawlStore
from skeleton.ai.webcrawler.claiming import FrontierClaimer
from skeleton.ai.webcrawler.leases import SqliteLeaseStore

def make_doc(i):
    text=f"document {i}"
    digest=hashlib.sha256(text.encode()).hexdigest()
    url=f"https://example.org/{i}"
    return CrawlDocument(url,url,"",text,"text/plain",digest,float(i),.8,{"schema":"p"},())

def test_repeated_delivery_is_content_idempotent():
    with tempfile.TemporaryDirectory() as d:
        s=SqliteCrawlStore(d+"/crawl.db")
        item=make_doc(1)
        assert s.put(item)
        for _ in range(100):
            assert not s.put(item)
        assert len(list(s.iter_documents()))==1
        s.close()

def test_many_distinct_documents_survive_reopen():
    with tempfile.TemporaryDirectory() as d:
        path=d+"/crawl.db";s=SqliteCrawlStore(path)
        for i in range(250):
            assert s.put(make_doc(i))
        s.close();s=SqliteCrawlStore(path)
        assert len(list(s.iter_documents()))==250
        s.close()

def test_lease_churn_never_allows_stale_completion():
    with tempfile.TemporaryDirectory() as d:
        store=SqliteLeaseStore(d+"/leases.db")
        stale=[]
        for i in range(100):
            a=FrontierClaimer(store,f"a-{i}",ttl=1)
            b=FrontierClaimer(store,f"b-{i}",ttl=1)
            old=a.claim("https://example.org/shared",now=i*3)
            current=b.claim("https://example.org/shared",now=i*3+2)
            assert current
            assert not a.complete(old)
            assert b.complete(current)
