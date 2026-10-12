from skeleton.ai.webcrawler.core import CrawlEngine,CrawlPolicy,CrawlBudget,FetchResponse,InMemoryCrawlStore

class Fetcher:
    def __init__(self,responses):
        self.responses=dict(responses);self.calls=[]
    def fetch(self,url,**kwargs):
        self.calls.append(url)
        value=self.responses[url]
        if isinstance(value,list):
            return value.pop(0)
        return value

def response(url,status=200,body=b"ok",headers=None,when=10):
    return FetchResponse(url,status,headers or {"content-type":"text/plain"},body,when)

def engine(fetcher,**policy):
    e=CrawlEngine(fetcher,policy=CrawlPolicy(min_host_delay_seconds=100,**policy),budget=CrawlBudget(max_requests=50))
    e.install_robots("https://a.example","User-agent: *\nAllow: /")
    e.install_robots("https://b.example","User-agent: *\nAllow: /")
    return e

def test_delayed_host_does_not_block_ready_other_host():
    f=Fetcher({"https://a.example/one":response("https://a.example/one"),
               "https://a.example/two":response("https://a.example/two"),
               "https://b.example/one":response("https://b.example/one")})
    e=engine(f);e.enqueue("https://a.example/one");e.enqueue("https://a.example/two");e.enqueue("https://b.example/one")
    assert e.step(now=0)
    assert e.step(now=1)
    assert f.calls[:2]==["https://a.example/one","https://b.example/one"]

def test_retry_after_controls_429_reschedule():
    url="https://a.example/one"
    f=Fetcher({url:[response(url,429,headers={"content-type":"text/plain","retry-after":"30"}),response(url)]})
    e=engine(f,retry_base_seconds=2)
    assert e.step(now=0) is None
    assert e.step(now=29) is None
    assert e.step(now=30)
    assert f.calls==[url,url]

def test_retry_after_is_capped():
    url="https://a.example/one"
    f=Fetcher({url:[response(url,503,headers={"content-type":"text/plain","retry-after":"99999"}),response(url)]})
    e=engine(f,max_retry_delay_seconds=60)
    e.enqueue(url);assert e.step(now=0) is None
    assert e.step(now=59) is None
    assert e.step(now=60)

def test_link_admission_is_bounded():
    links="".join(f'<a href="/{i}">x</a>' for i in range(20)).encode()
    url="https://a.example/"
    f=Fetcher({url:response(url,body=links,headers={"content-type":"text/html"})})
    e=engine(f,max_links_per_document=3);e.enqueue(url);assert e.step(now=0)
    assert len(e._frontier)==3
