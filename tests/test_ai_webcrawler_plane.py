from skeleton.ai.webcrawler import (
    CrawlBudget, CrawlEngine, CrawlPolicy, InMemoryCrawlStore, canonicalize_url,
)
from skeleton.ai.webcrawler.core import FetchResponse


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        value = self.pages[url]
        if isinstance(value, Exception):
            raise value
        status, ctype, body = value
        return FetchResponse(url, status, {"content-type": ctype}, body.encode(), 100.0)


def engine(pages, **kwargs):
    e = CrawlEngine(FakeFetcher(pages), policy=CrawlPolicy(min_host_delay_seconds=0), **kwargs)
    e.install_robots("https://example.com", "User-agent: *\nAllow: /\nDisallow: /private")
    return e


def test_canonicalization_dedupes_tracking_fragment_and_query_order():
    a = canonicalize_url("HTTPS://Example.COM:443/a/../b?z=2&utm_source=x&a=1#frag")
    b = canonicalize_url("https://example.com/b?a=1&z=2")
    assert a == b == "https://example.com/b?a=1&z=2"


def test_policy_rejects_local_and_non_http_destinations():
    p = CrawlPolicy()
    assert not p.admits("http://127.0.0.1/admin")
    assert not p.admits("http://localhost/admin")
    assert not p.admits("file:///etc/passwd")
    assert p.admits("https://example.com/")


def test_robots_is_fail_closed_and_disallow_is_never_fetched():
    f = FakeFetcher({})
    e = CrawlEngine(f, policy=CrawlPolicy(min_host_delay_seconds=0))
    assert e.enqueue("https://example.com/")
    assert e.step(now=1) is None
    # Fail closed still makes a bounded robots request; protected page content
    # must never be fetched until the destination's robots policy is known.
    assert f.calls == ["https://example.com/robots.txt"]

    e = engine({"https://example.com/private": (200, "text/plain", "secret")})
    assert e.enqueue("https://example.com/private")
    assert e.step(now=1) is None
    assert e.fetcher.calls == []


def test_extracts_provenance_discovers_links_and_hands_off_retrieval():
    pages = {
        "https://example.com/": (
            200, "text/html",
            "<title>Root</title><main>Hello world</main>"
            "<a href='/next?utm_source=x'>Next</a><script>ignore me</script>",
        ),
        "https://example.com/next": (200, "text/plain", "Second document"),
    }
    e = engine(pages)
    assert e.enqueue("https://example.com/")
    first = e.step(now=1)
    second = e.step(now=2)
    assert first and first.title == "Root"
    assert "ignore me" not in first.text
    assert second and second.canonical_url == "https://example.com/next"
    batch = e.retrieval_batch()
    assert len(batch) == 2
    assert batch[0]["metadata"]["provenance"]["schema"] == "skeleton.ai.crawl.provenance.v1"


def test_content_hash_dedup_keeps_one_document():
    pages = {
        "https://example.com/a": (200, "text/plain", "same body"),
        "https://example.com/b": (200, "text/plain", "same body"),
    }
    e = engine(pages)
    e.enqueue("https://example.com/a")
    e.enqueue("https://example.com/b")
    assert e.step(now=1) is not None
    assert e.step(now=2) is None
    assert len(e.store.documents) == 1
    assert len(e.store.url_to_hash) == 2


def test_budget_stops_runaway_crawl():
    pages = {
        "https://example.com/": (200, "text/html", "<a href='/a'>a</a> root"),
        "https://example.com/a": (200, "text/plain", "a"),
    }
    e = engine(pages, budget=CrawlBudget(max_requests=1, max_documents=10, max_bytes=1000))
    e.enqueue("https://example.com/")
    assert e.step(now=1) is not None
    assert e.budget.exhausted
    assert e.step(now=2) is None
    assert e.fetcher.calls == ["https://example.com/"]


def test_checkpoint_restores_frontier_seen_and_budget():
    store = InMemoryCrawlStore()
    e = engine({"https://example.com/": (200, "text/plain", "root")}, store=store)
    e.enqueue("https://example.com/")
    e.checkpoint("run")
    restored = engine({"https://example.com/": (200, "text/plain", "root")}, store=store)
    assert restored.restore("run")
    doc = restored.step(now=1)
    assert doc and doc.text == "root"


def test_retry_is_bounded_and_backed_off():
    f = FakeFetcher({"https://example.com/": RuntimeError("network")})
    e = CrawlEngine(f, policy=CrawlPolicy(
        min_host_delay_seconds=0, max_retries=2, retry_base_seconds=2,
    ))
    e.install_robots("https://example.com", "User-agent: *\nAllow: /")
    e.enqueue("https://example.com/")
    assert e.step(now=0) is None
    assert e.step(now=1) is None
    assert e.step(now=2) is None
    assert e.step(now=5) is None
    assert e.step(now=6) is None
    assert len(f.calls) == 3
    # A failed network operation still consumes the global crawl budget;
    # otherwise a repeatedly failing legacy fetcher can evade request caps.
    assert e.budget.requests == 3


def test_robots_bootstrap_is_self_directed_and_budgeted():
    pages = {
        "https://example.com/robots.txt": (200, "text/plain", "User-agent: *\nAllow: /"),
        "https://example.com/": (200, "text/plain", "public"),
    }
    e = CrawlEngine(FakeFetcher(pages), policy=CrawlPolicy(min_host_delay_seconds=0))
    e.enqueue("https://example.com/")
    doc = e.step(now=1)
    assert doc and doc.text == "public"
    assert e.fetcher.calls == [
        "https://example.com/robots.txt",
        "https://example.com/",
    ]
    assert e.budget.requests == 2


def test_robots_server_error_fails_closed():
    pages = {"https://example.com/robots.txt": (503, "text/plain", "unavailable")}
    e = CrawlEngine(FakeFetcher(pages), policy=CrawlPolicy(min_host_delay_seconds=0))
    e.enqueue("https://example.com/")
    assert e.step(now=1) is None
    assert e.fetcher.calls == ["https://example.com/robots.txt"]


def test_http_transport_rejects_private_literal_before_network():
    from skeleton.ai.webcrawler.http import SafeHttpFetcher, UnsafeDestination
    fetcher = SafeHttpFetcher()
    try:
        fetcher.fetch("http://127.0.0.1/", user_agent="test", max_bytes=100)
    except UnsafeDestination:
        pass
    else:
        raise AssertionError("private destination must fail closed")
