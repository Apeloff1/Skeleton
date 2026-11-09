from skeleton.ai.webcrawler.core import CrawlEngine,CrawlPolicy,InMemoryCrawlStore,FetchResponse
class F:
 def fetch(self,url,**kwargs):return FetchResponse(url,200,{"content-type":"text/plain"},b"ok",1)
 fetch_once=fetch
def test_checkpoint_restore_preserves_frontier_and_budget():
 s=InMemoryCrawlStore();e=CrawlEngine(F(),policy=CrawlPolicy(min_host_delay_seconds=0),store=s)
 e.enqueue("https://a.example/a",priority=2);e.enqueue("https://a.example/b",priority=1)
 e.budget.requests=7;e.checkpoint("run")
 restored=CrawlEngine(F(),policy=CrawlPolicy(min_host_delay_seconds=0),store=s)
 assert restored.restore("run")
 assert [(x.url,x.priority) for x in sorted(restored._frontier)]==[(x.url,x.priority) for x in sorted(e._frontier)]
 assert restored.budget.requests==7
def test_restore_rejects_unknown_checkpoint_schema():
 s=InMemoryCrawlStore();s.save_checkpoint("bad",{"schema":"future.schema"})
 assert not CrawlEngine(F(),store=s).restore("bad")
def test_restore_rejects_duplicate_frontier_urls():
 s=InMemoryCrawlStore();e=CrawlEngine(F(),store=s);e.enqueue("https://a.example/a");e.checkpoint("bad")
 state=s.load_checkpoint("bad");state["frontier"].append(dict(state["frontier"][0],sequence=2));state["queued"]=["https://a.example/a"]
 s.save_checkpoint("bad",state)
 assert not CrawlEngine(F(),store=s).restore("bad")
def test_restore_rejects_frontier_queue_disagreement():
 s=InMemoryCrawlStore();e=CrawlEngine(F(),store=s);e.enqueue("https://a.example/a");e.checkpoint("bad")
 state=s.load_checkpoint("bad");state["queued"]=[];s.save_checkpoint("bad",state)
 assert not CrawlEngine(F(),store=s).restore("bad")
