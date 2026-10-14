from skeleton.ai.webcrawler.core import CrawlBudget,CrawlEngine,CrawlPolicy,FetchResponse
class F:
    def __init__(self,rows):self.rows=rows;self.calls=[]
    def fetch(self,url,**kwargs):
        self.calls.append(url);v=self.rows[url]
        return v.pop(0) if isinstance(v,list) else v
    fetch_once=fetch
def r(url,status=200,body=b"ok",headers=None):
    return FetchResponse(url,status,headers or {"content-type":"text/plain"},body,1)
def test_robots_and_document_both_charge_request_budget():
    rows={"https://a.example/robots.txt":r("https://a.example/robots.txt",body=b"User-agent: *\nAllow: /"),
          "https://a.example/x":r("https://a.example/x")}
    b=CrawlBudget(max_requests=2);e=CrawlEngine(F(rows),policy=CrawlPolicy(min_host_delay_seconds=0),budget=b)
    e.enqueue("https://a.example/x");assert e.step(now=0);assert b.requests==2 and b.exhausted
def test_retry_response_consumes_budget_before_retry():
    url="https://a.example/x";f=F({url:[r(url,503),r(url)]})
    b=CrawlBudget(max_requests=2);e=CrawlEngine(f,policy=CrawlPolicy(min_host_delay_seconds=0),budget=b)
    e.install_robots("https://a.example","User-agent: *\nAllow: /");e.enqueue(url)
    assert e.step(now=0) is None and b.requests==1
    assert e.step(now=2) and b.requests==2
def test_budget_prevents_autonomous_robots_fetch_when_empty():
    f=F({});b=CrawlBudget(max_requests=0);e=CrawlEngine(f,budget=b)
    e.enqueue("https://a.example/x");assert e.step(now=0) is None
    assert f.calls==[]
