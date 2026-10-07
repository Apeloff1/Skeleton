"""Crawler-controlled redirect traversal with policy and robots checks at every hop."""
from __future__ import annotations
from urllib.parse import urljoin
from .core import FetchResponse,canonicalize_url
class RedirectPolicyError(ValueError):pass
def fetch_with_policy(engine,url,*,now):
    current=canonicalize_url(url);seen=set()
    for hop in range(engine.policy.max_redirects+1):
        if current in seen:raise RedirectPolicyError("redirect loop")
        seen.add(current)
        if not engine.policy.admits(current):raise RedirectPolicyError("redirect destination rejected by crawl policy")
        if not engine.robots.known(current) and not engine.load_robots(current):
            raise RedirectPolicyError("redirect destination robots unavailable")
        if not engine.robots.allowed(current):
            raise RedirectPolicyError("redirect destination denied by robots")
        fetch_once=getattr(engine.fetcher,"fetch_once",None)
        if fetch_once is None:
            if hop:raise RedirectPolicyError("fetcher cannot expose redirect hops")
            return engine.fetcher.fetch(current,user_agent=engine.policy.user_agent,max_bytes=engine.policy.max_response_bytes)
        response=fetch_once(current,user_agent=engine.policy.user_agent,max_bytes=engine.policy.max_response_bytes)
        if response.status not in {301,302,303,307,308}:return response
        location=response.headers.get("location")
        if not location or hop>=engine.policy.max_redirects:raise RedirectPolicyError("redirect limit or malformed redirect")
        current=canonicalize_url(urljoin(current,location))
    raise RedirectPolicyError("redirect limit exceeded")
